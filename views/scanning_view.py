import io
import cv2
import numpy as np
from PIL import Image
import streamlit as st

from utils import extract_qr_code_from_url
from repositories.item_search import find_items_by_qr_code
from views.item_card import render_item_card

from views.crud_views import (
    procurement_form,
    os_main_form,
    plastic_form,
    plastic_settings_form,
)

# Маппинг: table_id → form-модуль
TABLE_TO_FORM = {
    "procurement": procurement_form,
    "os_main": os_main_form,
    "plastic_spools": plastic_form,
    "plastic_settings": plastic_settings_form,
}


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


def _can_edit() -> bool:
    """Редактирование доступно только editor/admin и только в postgres."""
    user = st.session_state.get("current_user")
    if not user:
        return False
    if user.get("role") not in ("editor", "admin"):
        return False
    source = st.session_state.get("data_source", "postgres")
    if source != "postgres":
        return False
    return True


def _on_edit(item_data: dict, table: str) -> None:
    """Callback из карточки — открыть форму редактирования."""
    st.session_state.scan_edit_action = {
        "table": table,
        "item_id": item_data.get("id"),
        "qr_code": item_data.get("qr_code", ""),
    }
    st.rerun()


def _render_scan_edit(action: dict) -> None:
    """Форма редактирования вместо сканера."""
    table = action.get("table")
    item_id = action.get("item_id")
    qr_code = action.get("qr_code", "")

    user = st.session_state.get("audit_name") or st.session_state.get("current_user", {}).get("username", "—")

    form_module = TABLE_TO_FORM.get(table)
    if form_module is None:
        st.error(f"Неизвестная таблица: {table}")
        if st.button("← Назад к результатам сканирования"):
            st.session_state.pop("scan_edit_action", None)
            st.rerun()
        return

    # Кнопка «Назад» над формой
    if st.button("← Назад к результатам сканирования"):
        st.session_state.pop("scan_edit_action", None)
        st.rerun()

    def _on_success():
        st.session_state.pop("scan_edit_action", None)
        # Запоминаем qr_code, чтобы перечитать карточку после rerun
        st.session_state["_scan_refresh_qr"] = qr_code

    def _on_cancel():
        st.session_state.pop("scan_edit_action", None)

    form_module.render_edit_form(
        item_id,
        user,
        on_success=_on_success,
        on_cancel=_on_cancel,
    )


def render():
    st.title("📷 Сканер QR-кодов")

def render():
    st.title("📷 Сканер QR-кодов")

    # --- 1. Активное редактирование из сканера ---
    scan_edit = st.session_state.get("scan_edit_action")
    if scan_edit:
        _render_scan_edit(scan_edit)
        return

    # --- 2. Refresh после успешного сохранения ---
    refresh_qr = st.session_state.pop("_scan_refresh_qr", None)
    if refresh_qr:
        st.info(f"🔄 Карточка обновлена (QR: **{refresh_qr}**)")
        try:
            found = find_items_by_qr_code(refresh_qr)
        except Exception as e:
            st.error(f"Ошибка загрузки: {e}")
            found = []

        if not found:
            st.warning(f"Предмет с QR **«{refresh_qr}»** не найден после обновления.")
        else:
            for item_res in found:
                render_item_card(
                    item_res["data"],
                    item_res["table"],
                    on_edit_callback=_on_edit if _can_edit() else None,
                )

        if st.button("📷 Сканировать новый QR"):
            st.rerun()
        return

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
                # 1. Извлекаем qr_code из распознанного текста
                qr_code = extract_qr_code_from_url(data)

                if not qr_code:
                    st.warning(
                        f"QR #{idx}: не удалось извлечь код из распознанного текста."
                    )
                    with st.expander("Показать распознанный текст"):
                        st.code(data, language="text")

                    # Если распознанный текст — URL, предложить перейти по ссылке
                    if data.strip().lower().startswith(("http://", "https://")):
                        st.link_button(
                            "🌐 Перейти по ссылке",
                            data.strip(),
                            width="stretch",
                        )

                    continue

                # 2. Ищем в БД
                with st.spinner(f"Поиск по QR «{qr_code}»..."):
                    try:
                        found = find_items_by_qr_code(qr_code)
                    except Exception as e:
                        st.error(f"Ошибка поиска: {e}")
                        continue

                # 3. Показываем результат
                if not found:
                    st.warning(
                        f"❌ Предмет с QR-кодом **«{qr_code}»** не найден в базе."
                    )
                    if st.button(
                        "🔍 Поискать в базе по другим параметрам",
                        key=f"search_fallback_{idx}",
                    ):
                        st.session_state["_pending_search_query"] = qr_code
                        st.session_state["_pending_app_mode"] = "Поиск"
                        st.rerun()
                    continue

                if len(found) == 1:
                    render_item_card(
                        found[0]["data"],
                        found[0]["table"],
                        on_edit_callback=_on_edit if _can_edit() else None,
                    )
                else:
                    # Несколько предметов — список с пометкой таблицы
                    st.info(
                        f"🔎 Найдено несколько предметов с QR **«{qr_code}»**:"
                    )
                    for item_res in found:
                        st.markdown(
                            f"**{item_res['table_label']}** · "
                            f"id={item_res['data'].get('id')}"
                        )
                        render_item_card(
                            item_res["data"],
                            item_res["table"],
                            on_edit_callback=_on_edit if _can_edit() else None,
                        )
        else:
            st.warning(
                "QR-код не обнаружен. Попробуйте сделать снимок ровнее, ближе "
                "или с лучшим освещением."
            )
            if st.button("🔄 Попробовать снова"):
                st.rerun()