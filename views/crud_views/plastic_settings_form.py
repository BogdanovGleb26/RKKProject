"""
Формы CRUD для plastic_settings (справочник).

Особенности:
- Нет аудита, нет оптимистичной блокировки.
- Жёсткое удаление.
"""

import time

import streamlit as st

from db import fetch_df
from repositories.plastic_settings_repo import (
    create_plastic_settings,
    update_plastic_settings,
    get_plastic_settings_by_id,
    delete_plastic_settings,
)


FIELDS = [
    ("plastic_type", "Тип пластика", "text"),
    ("nozzle_temp", "Сопло (°C)", "text"),
    ("bed_temp", "Стол (°C)", "text"),
    ("fan_speed", "Обдув, %", "text"),
    ("notes", "Особенности и рекомендации", "text"),
]


def _render_field(field_def, current_value, key_prefix: str) -> tuple[str, object]:
    db_col, label, kind = field_def
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
    """user игнорируется (справочник без аудита)."""
    st.subheader("➕ Новый тип пластика (справочник)")

    with st.form("plastic_settings_create_form"):
        data = _render_form_fields({}, key_prefix="create_ps")

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
        if not data.get("plastic_type"):
            st.error("Поле «Тип пластика» обязательно.")
            return
        try:
            new_id = create_plastic_settings(data, user)
            st.success(f"✅ Создано (id={new_id})")
            fetch_df.clear()
            st.session_state.pop("edit_action", None)
            time.sleep(1.5)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Ошибка создания: {e}")


# =============================================================================
# Edit
# =============================================================================

def render_edit_form(
    item_id: int,
    user: str,
    on_success=None,
    on_cancel=None,
) -> None:
    current = get_plastic_settings_by_id(item_id)
    if current is None:
        st.error("Запись не найдена.")
        if st.button("← Назад"):
            if on_cancel is not None:
                on_cancel()
            else:
                st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("✏️ Редактировать тип пластика (справочник)")

    with st.form(f"plastic_settings_edit_form_{item_id}"):
        data = _render_form_fields(current, key_prefix=f"edit_ps_{item_id}")

        st.divider()
        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button("💾 Сохранить", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("✖ Отмена", width="stretch")

    if cancelled:
        if on_cancel is not None:
            on_cancel()
        else:
            st.session_state.pop("edit_action", None)
        st.rerun()

    if submitted:
        if not data.get("plastic_type"):
            st.error("Поле «Тип пластика» обязательно.")
            return
        try:
            ok, msg = update_plastic_settings(item_id, data, user)
            if ok:
                st.success("✅ Сохранено")
                fetch_df.clear()
                if on_success is not None:
                    on_success()
                else:
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
    """user игнорируется (справочник без аудита)."""
    current = get_plastic_settings_by_id(item_id)
    if current is None:
        st.error("Запись не найдена.")
        if st.button("← Назад к списку"):
            st.session_state.pop("edit_action", None)
            st.rerun()
        return

    st.subheader("🗑️ Удалить тип пластика?")
    st.write(f"**Тип пластика:** {current.get('plastic_type') or '—'}")
    st.write(f"**Сопло:** {current.get('nozzle_temp') or '—'}")
    st.write(f"**Стол:** {current.get('bed_temp') or '—'}")
    st.warning(
        "⚠️ Это **жёсткое удаление**: запись будет удалена из БД **навсегда**. "
        "Восстановить не получится."
    )

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Да, удалить навсегда", type="primary", width="stretch"):
            if delete_plastic_settings(item_id):
                st.success("✅ Удалено")
                fetch_df.clear()
                st.session_state.pop("edit_action", None)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("Не удалось удалить.")
    with col_no:
        if st.button("✖ Отмена", width="stretch"):
            st.session_state.pop("edit_action", None)
            st.rerun()