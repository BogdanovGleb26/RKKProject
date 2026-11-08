"""
Страница входа.
"""

import streamlit as st

from auth import authenticate


def render():
    st.title("🔐 Вход в систему")
    st.caption("Введите логин и пароль. Если у вас нет учётной записи — обратитесь к администратору.")

    with st.form("login_form"):
        username = st.text_input("Логин", key="login_username")
        password = st.text_input("Пароль", type="password", key="login_password")
        submitted = st.form_submit_button("Войти", type="primary", width="stretch")

    if submitted:
        user, err = authenticate(username, password)
        if user is None:
            st.error(f"❌ {err}")
            return

        st.session_state.current_user = user
        st.rerun()