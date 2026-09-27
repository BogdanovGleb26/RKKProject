import streamlit as st

# Настройка страницы всегда должна быть самым первым вызовом Streamlit!
st.set_page_config(
    page_title="Инвентаризация 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="expanded", # Сайдбар по умолчанию открыт
)

# Импортируем модули после настройки страницы
import config
from views import search_view, analytics_view, scanning_view

# Инициализируем состояние выбранного раздела в session_state
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Поиск"

# --- Боковое меню (Сайдбар) ---
st.sidebar.title("🎛️ Меню")

# Радио-кнопка для переключения между разделами
app_mode = st.sidebar.radio(
    "Выберите раздел:",
    options=["Поиск", "Аналитика", "Сканирование"],
    index=0
)

st.sidebar.divider()

st.sidebar.link_button(
    "💻 Исходный код на GitHub",
    "https://github.com/BogdanovGleb26/RKKProject",
    use_container_width=True,
)

st.sidebar.caption("© 2026 Инвентаризация v1.0.0")

# --- Маршрутизация (Роутинг) ---
if app_mode == "Поиск":
    search_view.render()
elif app_mode == "Аналитика":
    analytics_view.render()
elif app_mode == "Сканирование":
    scanning_view.render()