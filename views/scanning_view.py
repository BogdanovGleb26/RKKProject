import io
import cv2
import numpy as np
from PIL import Image
import streamlit as st


MAX_PREVIEW = 1200
MAX_DETECT = 3000


def _maybe_resize(pil_image: Image.Image, max_size: int) -> tuple[Image.Image, bool]:
    """Уменьшает изображение, если оно больше max_size по большей стороне."""
    w, h = pil_image.size
    if max(w, h) <= max_size:
        return pil_image, False
    scale = max_size / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return pil_image.resize(new_size, Image.LANCZOS), True


def preprocess_image(gray_img):
    """Создает несколько вариантов обработанного изображения."""
    variants = [
        gray_img,
        cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_img),
        cv2.adaptiveThreshold(
            gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        ),
    ]
    _, otsu = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)
    return variants


def scan_qr_code(img_np):
    """Распознавание QR-кодов с многоэтапной обработкой кадров."""
    # Локальный детектор — thread-safe при параллельных сессиях Streamlit
    qr_detector = cv2.QRCodeDetector()

    if len(img_np.shape) == 3:
        if img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_np

    h, w = gray.shape[:2]
    if max(h, w) < 1200:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    image_variants = preprocess_image(gray)
    results = set()

    for img_variant in image_variants:
        retval, decoded_info, _, _ = qr_detector.detectAndDecodeMulti(img_variant)
        if retval:
            for info in decoded_info:
                if info and info.strip():
                    results.add(info.strip())

        data, _, _ = qr_detector.detectAndDecode(img_variant)
        if data and data.strip():
            results.add(data.strip())

        if results:
            break

    return list(results)


def render():
    st.title("📷 Сканер QR-кодов")
    st.write("Загрузите изображение с QR-кодом или сделайте фото через веб-камеру.")

    source_option = st.segmented_control(
        "Выберите способ ввода:",
        options=["Фотография с телефона", "Фотография с ПК"],
        default="Фотография с телефона",
        selection_mode="single",
        key="scan_source_option",
    ) or "Фотография с телефона"

    image_bytes = None

    if source_option == "Фотография с телефона":
        uploaded_files = st.file_uploader(
            "Выберите файл изображения...",
            type=["png", "jpg", "jpeg", "webp"],
            key="qr_file_uploader",
            accept_multiple_files=True,
        )
        if uploaded_files:
            image_bytes = uploaded_files[0].read()
            if len(uploaded_files) > 1:
                st.info(
                    f"Загружено файлов: {len(uploaded_files)}. "
                    f"Обрабатывается первый: **{uploaded_files[0].name}**."
                )
    else:
        camera_photo = st.camera_input("Сделайте снимок QR-кода", key="qr_camera_input")
        if camera_photo is not None:
            image_bytes = camera_photo.getvalue()

    if image_bytes is not None:
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            pil_image.load()
        except Exception as e:
            st.error(
                f"Не удалось открыть изображение: {type(e).__name__}. "
                f"Убедитесь, что это корректный файл PNG/JPG."
            )
            st.stop()

        if pil_image.mode not in ("RGB", "L"):
            pil_image = pil_image.convert("RGB")

        original_size = pil_image.size
        preview_image, resized_preview = _maybe_resize(pil_image, MAX_PREVIEW)
        detect_image, resized_detect = _maybe_resize(pil_image, MAX_DETECT)

        st.image(preview_image, caption="Обрабатываемое изображение", width="stretch")

        if resized_preview or resized_detect:
            msg = f"Изображение уменьшено: {original_size[0]}×{original_size[1]}"
            if resized_detect:
                msg += f" → {detect_image.size[0]}×{detect_image.size[1]} для распознавания"
            st.caption(msg)

        img_np = np.array(detect_image)

        with st.spinner("Распознавание QR-кода..."):
            qr_data_list = scan_qr_code(img_np)

        if qr_data_list:
            st.success(f"🎉 Найдено QR-кодов: {len(qr_data_list)}")

            for idx, data in enumerate(qr_data_list, start=1):
                st.subheader(f"Результат #{idx}")
                st.code(data, language="text")

                if data.lower().startswith(("http://", "https://")):
                    st.link_button("🌐 Перейти по ссылке", data, width="stretch")
                else:
                    st.info("Распознанный текст не является веб-ссылкой.")
        else:
            st.warning(
                "QR-код не обнаружен. Попробуйте сделать снимок ровнее, ближе "
                "или с лучшим освещением."
            )
            if st.button("🔄 Попробовать снова"):
                st.rerun()