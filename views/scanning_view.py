import io
import cv2
import numpy as np
from PIL import Image
import streamlit as st

# Инициализируем детектор QR-кодов из OpenCV
qr_detector = cv2.QRCodeDetector()


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
    # Конвертация в полутоновое изображение
    if len(img_np.shape) == 3:
        if img_np.shape[2] == 4:  # RGBA
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_np

    # Масштабирование: если картинка небольшая, увеличиваем ее в 2 раза
    h, w = gray.shape[:2]
    if max(h, w) < 1200:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    image_variants = preprocess_image(gray)
    results = set()

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

        if results:
            break

    return list(results)


def render():
    st.title("📷 Сканер QR-кодов")
    st.write("Загрузите изображение с QR-кодом или сделайте фото через веб-камеру.")

    # Выбор источника изображения
    source_option = st.radio(
        "Выберите способ ввода:",
        ("Фотография с телефона", "Фотография с ПК"),
        horizontal=True,
    )

    image_bytes = None

    if source_option == "Фотография с телефона":
        uploaded_file = st.file_uploader(
            "Выберите файл изображения...",
            type=["png", "jpg", "jpeg", "webp"],
            key="qr_file_uploader",
        )
        if uploaded_file is not None:
            image_bytes = uploaded_file.read()
    else:
        camera_photo = st.camera_input("Сделайте снимок QR-кода", key="qr_camera_input")
        if camera_photo is not None:
            image_bytes = camera_photo.getvalue()

    # Если изображение передано пользователем
    if image_bytes is not None:
        pil_image = Image.open(io.BytesIO(image_bytes))
        img_np = np.array(pil_image)

        st.image(pil_image, caption="Обрабатываемое изображение", use_container_width=True)

        with st.spinner("Распознавание QR-кода..."):
            qr_data_list = scan_qr_code(img_np)

        if qr_data_list:
            st.success(f"🎉 Найдено QR-кодов: {len(qr_data_list)}")

            for idx, data in enumerate(qr_data_list, start=1):
                st.subheader(f"Результат #{idx}")
                st.code(data, language="text")

                # Проверяем, является ли распознанная строка URL-ссылкой
                if data.startswith("http://") or data.startswith("https://"):
                    st.link_button("🌐 Перейти по ссылке", data, use_container_width=True)
                else:
                    st.info("Распознанный текст не является веб-ссылкой.")
        else:
            st.warning(
                "QR-код не обнаружен. Попробуйте сделать снимок ровнее, ближе или с лучшим освещением."
            )