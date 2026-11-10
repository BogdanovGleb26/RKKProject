"""
Страница входа.
"""

import streamlit as st

from auth import authenticate
from db import check_db_connection


def render():
    st.title("🔐 Вход в систему")

    # Статус БД — проверяем ОДИН раз за сессию (кеш в session_state).
    # Не дёргаем check_db_connection на каждом рендере.
    if "login_db_status" not in st.session_state:
        try:
            db_ok, _ = check_db_connection()
        except Exception:
            db_ok = False
        st.session_state["login_db_status"] = db_ok

    db_ok = st.session_state["login_db_status"]

    if not db_ok:
        st.error(
            "⚠️ **PostgreSQL недоступен.** "
            "Обычный вход не работает. "
            "Используйте **аварийный вход** (учётные данные у администратора)."
        )

    st.caption(
        "Введите логин и пароль. Если у вас нет учётной записи — "
        "обратитесь к администратору."
    )

    with st.form("login_form"):
        username = st.text_input("Логин", key="login_username")
        password = st.text_input("Пароль", type="password", key="login_password")
        submitted = st.form_submit_button("Войти", type="primary", width="stretch")

    if submitted:
        user, err = authenticate(username, password)
        if user is None:
            st.error(f"❌ {err}")
            return

        # Сбрасываем кеш статуса — при следующем логине перепроверим
        st.session_state.pop("login_db_status", None)
        st.session_state.current_user = user
        st.rerun()