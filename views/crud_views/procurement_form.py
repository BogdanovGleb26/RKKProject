"""
Формы для CRUD-операций над procurement.

Используется со страницы «Редактирование» (edit_view.py).
"""

import streamlit as st

from db import fetch_df
from repositories.procurement_repo import (
    create_procurement,
    update_procurement,
    get_procurement_by_id,
    delete_procurement,
)


# =============================================================================
# Определение полей: (db_column, label, kind, group)
# kind: "text" | "number"
# group: одна из GROUPS
# =============================================================================

FIELDS = [
    # Идентификация
    ("code", "Код", "text", "Идентификация"),
    ("okpd2", "Код ОКПД2", "text", "Идентификация"),
    ("nomenclature", "Номенклатура", "text", "Идентификация"),
    ("qr_code", "QR код", "text", "Идентификация"),

    # Статус и принадлежность
    ("status", "Статус", "text", "Статус и принадлежность"),
    ("project", "Проект", "text", "Статус и принадлежность"),
    ("mto_service", "МТО/Услуга", "text", "Статус и принадлежность"),

    # Финансы
    ("price", "Цена", "number", "Финансы"),
    ("quantity", "Кол-во", "number", "Финансы"),
    ("amount", "Сумма", "number", "Финансы"),
    ("final_price", "Цена финальная", "number", "Финансы"),
    ("final_amount", "Сумма финальная", "number", "Финансы"),
    ("packaging", "Упаковка", "text", "Финансы"),
    ("unit", "Ед. изм.", "text", "Финансы"),

    # План
    ("plan_line", "Строка плана закупки", "text", "План"),
    ("need_plan", "План потребности", "text", "План"),
    ("mtr_plan", "План МТР", "text", "План"),

    # Ответственные
    ("mto_department", "Отдел МТО", "text", "Ответственные"),
    ("mto_curator", "Куратор МТО", "text", "Ответственные"),

    # Документы
    ("supplier_invoice_approved", "Счет поставщика согласован", "text", "Документы"),
    ("purchase_request", "Заявка на закупку", "text", "Документы"),
    ("payment_request", "Заявка на оплату", "text", "Документы"),
    ("receipt_order", "Приходный ордер", "text", "Документы"),
    ("paid", "Оплачено", "text", "Документы"),
    ("received_to_warehouse", "Получено со склада", "text", "Документы"),
    ("cancelled", "Отменено", "text", "Документы"),
    ("link", "Ссылка", "text", "Документы"),

    # Склад
    ("remainder", "Остаток", "number", "Склад"),
    ("storage_location", "Место хранения", "text", "Склад"),
    ("written_off", "Списано", "text", "Склад"),
]

GROUPS = [
    "Идентификация",
    "Статус и принадлежность",
    "Финансы",
    "План",
    "Ответственные",
    "Документы",
    "Склад",
]


# =============================================================================
# Хелперы
# =============================================================================

def _to_float(raw: str) -> float | None:
    """Парсит число из строки ввода. None, если пусто/не парсится."""
    s = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _render_field(field_def, current_value, key_prefix: str) -> tuple[str, object]:
    """Рендерит одно поле. Возвращает (db_column, value)."""
    db_col, label, kind, _ = field_def

    if kind == "number":
        # Приводим текущее значение к строке
        if current_value is None or current_value == "":
            default = ""
        else:
            default = str(current_value)

        val = st.text_input(
            label,
            value=default,
            key=f"{key_prefix}_{db_col}",
            help="Число (можно с точкой или запятой). Пусто → NULL.",
        )
        return db_col, _to_float(val)

    # text
    default = "" if current_value is None else str(current_value)
    val = st.text_input(label, value=default, key=f"{key_prefix}_{db_col}")
    return db_col, (val.strip() or None)


def _render_form_fields(current: dict, key_prefix: str) -> dict:
    """Рендерит все группы полей. Возвращает {db_column: value}."""
    data: dict = {}
    for group in GROUPS:
        with st.expander(group, expanded=(group == "Идентификация")):
            for field_def in FIELDS:
                if field_def[3] != group:
                    continue
                db_col, value = _render_field(
                    field_def, current.get(field_def[0]), key_prefix
                )
                data[db_col] = value
    return data


# =============================================================================
# Create
# =============================================================================

def render_create_form(user: str) -> None:
    """Форма создания новой позиции."""
    st.subheader("➕ Новая позиция (Закупки)")

    with st.form("procurement_create_form"):
        data = _render_form_fields({}, key_prefix="create")

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button(
                "💾 Сохранить", type="primary", width="stretch"
            )
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop("edit_action", None)
        st.rerun()

    if submitted:
        if not data.get("code"):
            st.error("Поле «Код» обязательно.")
            return

        try:
            new_id = create_procurement(data, user)
            st.success(f"Создано (id={new_id})")
            fetch_df.clear()
            st.session_state.pop("edit_action", None)
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка создания: {e}")


# =============================================================================
# Edit
# =============================================================================

def render_edit_form(item_id: int, user: str) -> None:
    """Форма редактирования существующей позиции."""
    current = get_procurement_by_id(item_id)
    if current is None:
        st.error("Позиция не найдена или удалена.")
        if st.button("← Назад к списку"):
            st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("✏️ Редактировать позицию (Закупки)")
    st.caption(
        f"id={item_id} · версия {current.get('row_version')} · "
        f"последнее изменение: {current.get('updated_by') or '—'}"
    )

    expected_version = current.get("row_version", 1)

    with st.form(f"procurement_edit_form_{item_id}"):
        data = _render_form_fields(current, key_prefix=f"edit_{item_id}")

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button(
                "💾 Сохранить", type="primary", width="stretch"
            )
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop("edit_action", None)
        st.rerun()

    if submitted:
        if not data.get("code"):
            st.error("Поле «Код» обязательно.")
            return

        try:
            ok, msg = update_procurement(item_id, data, expected_version, user)
            if ok:
                st.success("Сохранено")
                fetch_df.clear()
                st.session_state.pop("edit_action", None)
                st.rerun()
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"Ошибка сохранения: {e}")


# =============================================================================
# Delete
# =============================================================================

def render_delete_confirm(item_id: int, user: str) -> None:
    """Подтверждение удаления."""
    current = get_procurement_by_id(item_id)
    if current is None:
        st.error("Позиция не найдена или уже удалена.")
        if st.button("← Назад к списку"):
            st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("🗑️ Удалить позицию?")
    st.write(f"**Код:** {current.get('code')}")
    st.write(f"**Номенклатура:** {current.get('nomenclature') or '—'}")
    st.warning(
        "Позиция будет помечена как удалённая и скрыта из поиска. "
        "Восстановить можно через БД (is_deleted = FALSE)."
    )

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Да, удалить", type="primary", width="stretch"):
            if delete_procurement(item_id, user):
                st.success("Удалено")
                fetch_df.clear()
                st.session_state.pop("edit_action", None)
                st.rerun()
            else:
                st.error("Не удалось удалить (возможно, уже удалена).")
    with col_no:
        if st.button("✖ Отмена", width="stretch"):
            st.session_state.pop("edit_action", None)
            st.rerun()