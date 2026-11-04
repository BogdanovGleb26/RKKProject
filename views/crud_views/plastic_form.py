"""
Формы CRUD для plastic_spools (Пластик).
"""

import time

import streamlit as st

from db import fetch_df
from repositories.plastic_repo import (
    create_plastic,
    update_plastic,
    get_plastic_by_id,
    delete_plastic,
)


# =============================================================================
# Поля: (db_column, label, kind)
# =============================================================================

FIELDS = [
    ("code", "Код", "text"),
    ("name", "Название", "text"),
    ("type", "Тип", "text"),           # PLA, PETG, ABS, ...
    ("color", "Цвет", "text"),
    ("weight", "Вес (г)", "number"),
    ("qr_code", "QR код", "text"),
    ("storage_location", "Место хранения", "text"),
]


def _to_float(raw: str) -> float | None:
    s = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _render_field(field_def, current_value, key_prefix: str) -> tuple[str, object]:
    db_col, label, kind = field_def

    if kind == "number":
        default = "" if current_value is None or current_value == "" else str(current_value)
        val = st.text_input(label, value=default, key=f"{key_prefix}_{db_col}",
                            help="Число в граммах. Пусто → NULL.")
        return db_col, _to_float(val)

    default = "" if current_value is None else str(current_value)
    val = st.text_input(label, value=default, key=f"{key_prefix}_{db_col}")
    return db_col, (val.strip() or None)


def _render_form_fields(current: dict, key_prefix: str) -> dict:
    data: dict = {}
    for field_def in FIELDS:
        db_col, value = _render_field(field_def, current.get(field_def[0]), key_prefix)
        data[db_col] = value
    return data


# =============================================================================
# Create
# =============================================================================

def render_create_form(user: str) -> None:
    st.subheader("➕ Новая катушка (Пластик)")

    with st.form("plastic_create_form"):
        data = _render_form_fields({}, key_prefix="create_plastic")

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Сохранить", type="primary", width="stretch")
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
            new_id = create_plastic(data, user)
            st.success(f"✅ Создано (id={new_id})")
            fetch_df.clear()
            st.session_state.pop("edit_action", None)
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка создания: {e}")


# =============================================================================
# Edit
# =============================================================================

def render_edit_form(item_id: int, user: str) -> None:
    current = get_plastic_by_id(item_id)
    if current is None:
        st.error("Позиция не найдена или удалена.")
        if st.button("← Назад к списку"):
            st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("✏️ Редактировать катушку (Пластик)")
    st.caption(
        f"id={item_id} · версия {current.get('row_version')} · "
        f"последнее изменение: {current.get('updated_by') or '—'}"
    )

    # ← Фиксируем expected_version при первом открытии формы
    version_key = f"_edit_expected_version_{item_id}"
    if version_key not in st.session_state:
        st.session_state[version_key] = current.get("row_version", 1)
    expected_version = st.session_state[version_key]

    with st.form(f"plastic_edit_form_{item_id}"):
        data = _render_form_fields(current, key_prefix=f"edit_plastic_{item_id}")

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Сохранить", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        st.session_state.pop(version_key, None)
        st.session_state.pop("edit_action", None)
        st.rerun()

    if submitted:
        if not data.get("code"):
            st.error("Поле «Код» обязательно.")
            return
        try:
            ok, msg = update_plastic(item_id, data, expected_version, user)
            if ok:
                st.success("✅ Сохранено")
                fetch_df.clear()
                st.session_state.pop(version_key, None)
                st.session_state.pop("edit_action", None)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"Ошибка сохранения: {e}")


# =============================================================================
# Delete
# =============================================================================

def render_delete_confirm(item_id: int, user: str) -> None:
    current = get_plastic_by_id(item_id)
    if current is None:
        st.error("Позиция не найдена или уже удалена.")
        if st.button("← Назад к списку"):
            st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("🗑️ Удалить катушку? (Пластик)")
    st.write(f"**Код:** {current.get('code')}")
    st.write(f"**Название:** {current.get('name') or '—'}")
    st.write(f"**Тип:** {current.get('type') or '—'}")
    st.write(f"**Цвет:** {current.get('color') or '—'}")
    st.warning(
        "Позиция будет помечена как удалённая и скрыта из поиска. "
        "Восстановить можно через БД (is_deleted = FALSE)."
    )

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Да, удалить", type="primary", width="stretch"):
            if delete_plastic(item_id, user):
                st.success("✅ Удалено")
                fetch_df.clear()
                st.session_state.pop("edit_action", None)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("Не удалось удалить (возможно, уже удалена).")
    with col_no:
        if st.button("✖ Отмена", width="stretch"):
            st.session_state.pop("edit_action", None)
            st.rerun()