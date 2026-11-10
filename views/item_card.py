"""
Карточка предмета — отображение информации по найденному предмету.

Используется в scanning_view после распознавания QR.
"""

import streamlit as st

from utils import get_item_image_bytes, get_item_qr_bytes


# Маппинг: таблица → набор ключевых полей для отображения
# Формат: (db_column, label, kind)
# kind: "text" | "number" | "money"
KEY_FIELDS = {
    "procurement": [
        ("code", "Код", "text"),
        ("nomenclature", "Номенклатура", "text"),
        ("status", "Статус", "text"),
        ("project", "Проект", "text"),
        ("mto_department", "Отдел МТО", "text"),
        ("mto_curator", "Куратор МТО", "text"),
        ("storage_location", "Место хранения", "text"),
        ("final_amount", "Сумма финальная", "money"),
        ("qr_code", "QR код", "text"),
    ],
    "os_main": [
        ("code", "Код", "text"),
        ("nomenclature", "Номенклатура", "text"),
        ("status", "Статус", "text"),
        ("project", "Проект", "text"),
        ("mto_department", "Отдел МТО", "text"),
        ("mto_curator", "Куратор МТО", "text"),
        ("storage_location", "Место хранения", "text"),
        ("final_amount", "Финальная сумма", "money"),
        ("qr_code", "QR код", "text"),
    ],
    "plastic_spools": [
        ("code", "Код", "text"),
        ("name", "Название", "text"),
        ("type", "Тип", "text"),
        ("color", "Цвет", "text"),
        ("weight", "Вес (г)", "number"),
        ("storage_location", "Место хранения", "text"),
        ("qr_code", "QR код", "text"),
    ],
}

# Все поля для expander — все колонки из таблицы,
# которые есть в data (кроме служебных).
SERVICE_COLUMNS = {
    "id", "is_deleted", "deleted_at", "deleted_by",
    "created_at", "created_by", "updated_at", "updated_by",
    "row_version", "photo_path",
}


def _format_value(value, kind: str) -> str:
    """Форматирует значение для отображения."""
    if value is None or value == "":
        return "—"
    if kind == "money":
        try:
            return f"{float(value):,.2f} ₽".replace(",", " ")
        except (ValueError, TypeError):
            return str(value)
    if kind == "number":
        try:
            return f"{float(value):.2f}".rstrip("0").rstrip(".")
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def render_item_card(item: dict, table: str, *, on_edit_callback=None):
    """Рендерит карточку предмета.

    :param item: dict — запись из БД.
    :param table: str — 'procurement' | 'os_main' | 'plastic_spools'.
    :param on_edit_callback: callable | None — вызывается при нажатии «Редактировать».
    """
    table_label = {
        "procurement": "Закупки",
        "os_main": "ОС Главная",
        "plastic_spools": "Пластик",
    }.get(table, table)

    # Заголовок
    if table == "plastic_spools":
        name = item.get("name") or "Без названия"
    else:
        name = item.get("nomenclature") or "Без названия"

    code = item.get("code") or "—"
    storage = item.get("storage_location") or ""

    loc_tag = f"✅ [{storage}]" if storage else "❓ [Без локации]"

    with st.container(border=True):
        st.caption(f"📁 {table_label}")
        st.markdown(f"### {loc_tag} {name}")
        st.caption(f"Код: **{code}**")

        st.divider()

        # Ключевые поля (две колонки)
        fields = KEY_FIELDS.get(table, [])
        # Разбиваем на две колонки
        mid = (len(fields) + 1) // 2
        col1, col2 = st.columns(2)

        left_fields = fields[:mid]
        right_fields = fields[mid:]

        with col1:
            for db_col, label, kind in left_fields:
                val = _format_value(item.get(db_col), kind)
                st.markdown(f"**{label}:** {val}")

        with col2:
            for db_col, label, kind in right_fields:
                val = _format_value(item.get(db_col), kind)
                st.markdown(f"**{label}:** {val}")

        st.divider()

        # Фото + QR
        code_for_image = str(item.get("code") or "").strip()
        qr_value = str(item.get("qr_code") or "").strip()

        photo_bytes = get_item_image_bytes(code_for_image, "photo")
        qr_bytes = get_item_qr_bytes(code_for_image, qr_value)

        col_photo, col_qr = st.columns(2)
        with col_photo:
            if photo_bytes:
                st.image(photo_bytes, width=400)
            else:
                st.caption("📷 Нет фото")
        with col_qr:
            if qr_bytes:
                st.image(qr_bytes, width=400)
            else:
                st.caption("📱 Нет QR")

        # Expander со всеми полями
        with st.expander("📋 Все поля"):
            for db_col, val in item.items():
                if db_col in SERVICE_COLUMNS:
                    continue
                if val is None or val == "":
                    continue
                st.markdown(f"**{db_col}:** {val}")

        # Кнопки
        col_edit, col_space = st.columns([1, 3])
        with col_edit:
            if on_edit_callback is not None:
                if st.button(
                    "✏️ Редактировать",
                    width="stretch",
                    key=f"scan_edit_{table}_{item.get('id')}",
                ):
                    on_edit_callback(item, table)