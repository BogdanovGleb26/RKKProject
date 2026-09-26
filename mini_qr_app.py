import streamlit as st
import cv2
import numpy as np
from PIL import Image
import io

# Настройка страницы
st.set_page_config(
    page_title="Сканер QR-кодов",
    page_icon="🔍",
    layout="centered"
)

st.title("🔍 Сканер QR-кодов")
st.write("Загрузите изображение с QR-кодом или сделайте фото через веб-камеру.")

# Инициализируем детектор QR-кодов из OpenCV
qr_detector = cv2.QRCodeDetector()

# Выбор источника изображения
source_option = st.radio(
    "Выберите способ ввода:",
    ("Фотография с телефона", "Фотография с ПК"),
    horizontal=True
)

image_bytes = None

if source_option == "Фотография с телефона":
    uploaded_file = st.file_uploader(
        "Выберите файл изображения...", 
        type=["png", "jpg", "jpeg", "webp"]
    )
    if uploaded_file is not None:
        image_bytes = uploaded_file.read()
else:
    camera_photo = st.camera_input("Сделайте снимок QR-кода")
    if camera_photo is not None:
        image_bytes = camera_photo.getvalue()


# def scan_qr_code(img_np):
#     """
#     Распознавание QR-кодов с помощью OpenCV без использования pyzbar.
#     """
#     # Переводим изображение в оттенки серого для улучшения считывания
#     if len(img_np.shape) == 3 and img_np.shape[2] == 3:
#         gray_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
#     elif len(img_np.shape) == 3 and img_np.shape[2] == 4:
#         # Для PNG с альфа-каналом (RGBA)
#         gray_img = cv2.cvtColor(img_np, cv2.COLOR_RGBA2GRAY)
#     else:
#         gray_img = img_np

#     results = []

#     # Пробуем найти несколько QR-кодов на кадре
#     retval, decoded_info, points, _ = qr_detector.detectAndDecodeMulti(gray_img)

#     if retval:
#         for info in decoded_info:
#             if info.strip():  # Игнорируем пустые распознанные строки
#                 results.append(info)
#     else:
#         # Запасной вариант для одиночного QR-кода (если multi не сработал)
#         data, bbox, _ = qr_detector.detectAndDecode(gray_img)
#         if data and data.strip():
#             results.append(data)

#     return results

def preprocess_image(gray_img):
    """
    Создает несколько вариантов обработанного изображения для повышения шансов считывания.
    """
    variants = []
    
    # 1. Исходное серое изображение
    variants.append(gray_img)

    # 2. Увеличение контраста (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_img)
    variants.append(enhanced)

    # 3. Адаптивный порог (убирает неравномерные тени и блики)
    thresh = cv2.adaptiveThreshold(
        gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(thresh)

    # 4. Простая бинаризация по Отсу (Otsu Thresholding)
    _, otsu = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)

    return variants


def scan_qr_code(img_np):
    """
    Распознавание QR-кодов с многоэтапной обработкой кадров.
    """
    # 1. Переводим в Grayscale
    if len(img_np.shape) == 3 and img_np.shape[2] in (3, 4):
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_np

    # 2. Масштабирование: если картинка небольшая, увеличиваем ее в 1.5 раза
    h, w = gray.shape[:2]
    if max(h, w) < 1200:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    # Получаем варианты обработки изображения
    image_variants = preprocess_image(gray)

    results = set()  # Множество, чтобы убрать дубликаты

    for img_variant in image_variants:
        # Пробуем multi-детекцию
        retval, decoded_info, _, _ = qr_detector.detectAndDecodeMulti(img_variant)
        if retval:
            for info in decoded_info:
                if info and info.strip():
                    results.add(info.strip())

        # Пробуем одиночную детекцию, если multi пропустил
        data, _, _ = qr_detector.detectAndDecode(img_variant)
        if data and data.strip():
            results.add(data.strip())

        # Если уже что-то нашли, останавливаем цикл обработки
        if results:
            break

    return list(results)


# Если изображение передано пользователем
if image_bytes is not None:
    # Открываем изображение через PIL и переводим в numpy array
    pil_image = Image.open(io.BytesIO(image_bytes))
    img_np = np.array(pil_image)

    # Показываем исходную картинку
    st.image(pil_image, caption="Обрабатываемое изображение", use_container_width=True)

    with st.spinner("Распознавание QR-кода..."):
        qr_data_list = scan_qr_code(img_np)

    if qr_data_list:
        st.success(f"Найдено QR-кодов: {len(qr_data_list)}")

        for idx, data in enumerate(qr_data_list, start=1):
            st.subheader(f"Результат #{idx}")
            st.code(data, language="text")

            # Проверяем, является ли распознанная строка URL-ссылкой
            if data.startswith("http://") or data.startswith("https://"):
                st.link_button("🌐 Перейти по ссылке", data, use_container_width=True)
            else:
                st.info("Распознанный текст не является ссылкой.")
    else:
        st.warning(
            "QR-код не обнаружен. Попробуйте сделайть снимок ровнее или с лучшим освещением."
        )