import io
import socket
import qrcode
import streamlit as st

st.set_page_config(
    page_title="Инвентаризация 📦",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="expanded",
)

import config
from data_loader import check_source, load_data, SourceStatus
from views import analytics_view, scanning_view, search_view

from auth import ensure_admin_exists
ensure_admin_exists()

if "current_user" not in st.session_state:
    from views import login_view
    login_view.render()
    st.stop()

current_user = st.session_state.current_user

# =============================================================================
# Проверка входа
# =============================================================================
if "current_user" not in st.session_state:
    from views import login_view
    login_view.render()
    st.stop()

current_user = st.session_state.current_user

# --- Вспомогательные функции ---
def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_qr_code(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@st.dialog("📱 Подключение с мобильного")
def show_qr_modal(app_url: str):
    st.write("Отсканируйте QR-код камерой телефона для входа в приложение:")
    st.image(generate_qr_code(app_url), use_container_width=True)
    st.caption("Прямая ссылка на приложение:")
    st.code(app_url, language="text")
    st.info(
        "📌 **Важно:** Телефон и ПК должны быть подключены к одной Wi-Fi /"
        " локальной сети."
    )


# --- Инициализация состояния ---
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Поиск"

if "data_source" not in st.session_state:
    st.session_state.data_source = config.DEFAULT_DATA_SOURCE

# Статусы источников: {source: SourceStatus}
if "source_statuses" not in st.session_state:
    st.session_state.source_statuses = {}


def refresh_source_statuses():
    """Обновляет статусы всех источников."""
    statuses = {
        "yadisk": check_source("yadisk"),
        "local": check_source("local"),
    }
    # PostgreSQL — только если сконфигурирован
    if config.DB_ENABLED:
        from db import check_db_connection
        ok, msg = check_db_connection()
        statuses["postgres"] = SourceStatus("postgres", ok, msg)
    st.session_state.source_statuses = statuses


def format_source_option(source: str) -> str:
    """Человекочитаемая метка для селекта с индикатором статуса."""
    labels = {
        "yadisk": "Яндекс.Диск",
        "local": "Локальный ПК",
        "postgres": "PostgreSQL",
    }
    status = st.session_state.source_statuses.get(source)
    if status is None:
        return labels.get(source, source)  # ← get на всякий случай
    icon = "✅" if status.available else "⚠️"
    return f"{icon} {labels.get(source, source)}"


# При первом запуске — проверим статусы
if not st.session_state.source_statuses:
    refresh_source_statuses()

# Роль текущего пользователя
user_role = current_user["role"]
role_labels = {
    "admin": "Администратор",
    "editor": "Редактор",
    "viewer": "Наблюдатель",
}

# --- Боковое меню (Сайдбар) ---
st.sidebar.title("🎛️ Меню")

# Роли и доступные режимы
user_role = current_user["role"]  # из проверки входа

modes = ["Поиск", "Аналитика", "Сканирование"]
if user_role in ("editor", "admin"):
    modes.append("Редактирование")
if user_role == "admin":
    modes.append("Администрирование")

# Применяем "pending" переход (если какой-то view хочет сменить режим)
pending_mode = st.session_state.pop("_pending_app_mode", None)
if pending_mode and pending_mode in modes:
    st.session_state.app_mode = pending_mode

if st.session_state.get("app_mode") and st.session_state.app_mode not in modes:
    st.session_state.app_mode = "Поиск"

app_mode = st.sidebar.radio(
    "Выберите раздел:",
    options=modes,
    key="app_mode",
)

st.sidebar.divider()

# 📁 Переключатель источника данных (динамический)
source_options = {"yadisk": "Яндекс.Диск", "local": "Локальный ПК"}
if config.DB_ENABLED:
    source_options["postgres"] = "PostgreSQL"
source_keys = list(source_options.keys())

# Формируем лейблы с индикаторами
source_labels = {k: format_source_option(k) for k in source_keys}

try:
    current_idx = source_keys.index(st.session_state.data_source)
except ValueError:
    current_idx = 0

selected_label = st.sidebar.selectbox(
    "📁 Источник данных:",
    options=[source_labels[k] for k in source_keys],
    index=current_idx,
    help="Данные читаются из выбранного источника. Кеш сбрасывается при смене.",
)

# Обратный маппинг: label → source key
selected_source = next(
    (k for k in source_keys if source_labels[k] == selected_label),
    st.session_state.data_source,
)

# Смена источника — сбрасываем кеш данных
if selected_source != st.session_state.data_source:
    load_data.clear()
    from db import fetch_df
    fetch_df.clear()  # ← сброс кеша БД
    st.session_state.data_source = selected_source
    st.rerun()

# Показываем статус активного источника
active_status = st.session_state.source_statuses.get(st.session_state.data_source)
if active_status is not None:
    if active_status.available:
        date_part = f" • {active_status.modified}" if active_status.modified else ""
        st.sidebar.caption(f"🕒 {active_status.message}{date_part}")
    else:
        st.sidebar.error(f"⚠️ {active_status.message}")

# Кнопка проверки статусов
if st.sidebar.button("🔄 Проверить источники", use_container_width=True):
    with st.spinner("Проверяю источники..."):
        refresh_source_statuses()
    st.rerun()

# 👤 Текущий пользователь (только для редактирования)
if st.session_state.get("user_name"):
    col_user, col_btn = st.sidebar.columns([3, 1])
    with col_user:
        st.caption(f"👤 {st.session_state.user_name}")
    with col_btn:
        if st.button("✖", key="logout_user", help="Сменить пользователя"):
            st.session_state.user_name = ""
            st.rerun()

st.sidebar.divider()

# Кнопка QR-кода
local_ip = get_local_ip()
app_url = f"http://{local_ip}:8501"

if st.sidebar.button(
    "📲 Открыть на телефоне", use_container_width=True, type="primary"
):
    show_qr_modal(app_url)

# st.sidebar.link_button(
#     "💻 Исходный код на GitHub",
#     "https://github.com/BogdanovGleb26/RKKProject",
#     use_container_width=True,
# )


st.sidebar.divider()

st.sidebar.caption(
    f"👤 **{current_user['username']}** · "
    f"{role_labels.get(user_role, user_role)}"
)

if st.sidebar.button("🚪 Выйти", use_container_width=True, key="logout_btn"):
    st.session_state.pop("current_user", None)
    st.session_state.pop("audit_name", None)
    st.session_state.pop("app_mode", None)
    st.session_state.pop("edit_action", None)
    st.session_state.pop("selected_sheet_search", None)
    st.session_state.pop("selected_sheet_analytics", None)
    st.session_state.pop("edit_sheet", None)
    st.rerun()

st.sidebar.caption("© 2026 Инвентаризация v3.0.0")

# --- Маршрутизация с защитой по роли ---
if app_mode == "Поиск":
    search_view.render()
elif app_mode == "Аналитика":
    analytics_view.render()
elif app_mode == "Сканирование":
    scanning_view.render()
elif app_mode == "Редактирование":
    if user_role not in ("editor", "admin"):
        st.error("⛔ Недостаточно прав для доступа к этому разделу.")
        st.stop()
    from views import edit_view
    edit_view.render()
elif app_mode == "Администрирование":
    if user_role != "admin":
        st.error("⛔ Недостаточно прав для доступа к этому разделу.")
        st.stop()
    from views import admin_view
    admin_view.render()