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


# --- Боковое меню (Сайдбар) ---
st.sidebar.title("🎛️ Меню")

app_mode = st.sidebar.radio(
    "Выберите раздел:",
    options=["Поиск", "Аналитика", "Сканирование", "Редактирование", "Администрирование"],
    index=0,
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

# # --- DEBUG: проверка CRUD-репозитория (временно) ---
# with st.sidebar.expander("🔧 DEBUG CRUD", expanded=False):
#     if st.button("Test create (procurement)", key="debug_create_procurement"):
#         try:
#             from repositories.procurement_repo import (
#                 create_procurement, get_procurement_by_id, update_procurement,
#                 delete_procurement,
#             )
#             new_id = create_procurement(
#                 {"code": "TEST_PY_001", "nomenclature": "Из Python (DEBUG)", "status": "Тест"},
#                 user="debug_user",
#             )
#             st.success(f"✅ create: id={new_id}")
            
#             item = get_procurement_by_id(new_id)
#             st.write("**get by id:**")
#             st.write({
#                 "id": item.get("id"),
#                 "code": item.get("code"),
#                 "nomenclature": item.get("nomenclature"),
#                 "row_version": item.get("row_version"),
#                 "created_by": item.get("created_by"),
#             })
            
#             ok, msg = update_procurement(
#                 new_id,
#                 {"nomenclature": "Обновлено из Python"},
#                 expected_version=item.get("row_version"),
#                 user="debug_user",
#             )
#             st.write(f"**update:** ok={ok}, msg={msg!r}")
            
#             item2 = get_procurement_by_id(new_id)
#             st.write({
#                 "nomenclature": item2.get("nomenclature"),
#                 "row_version": item2.get("row_version"),
#                 "updated_by": item2.get("updated_by"),
#             })
            
#             # Конфликт версий: пробуем обновить с устаревшей version
#             ok2, msg2 = update_procurement(
#                 new_id,
#                 {"nomenclature": "Конфликт"},
#                 expected_version=item.get("row_version"),  # старая!
#                 user="debug_user",
#             )
#             st.write(f"**update (конфликт):** ok={ok2}, msg={msg2!r}")
            
#             ok_del = delete_procurement(new_id, "debug_user")
#             st.write(f"**delete:** ok={ok_del}")
            
#             item3 = get_procurement_by_id(new_id)
#             st.write(f"**after delete:** item={item3}")
            
#         except Exception as e:
#             st.error(f"{type(e).__name__}: {e}")
#             import traceback
#             st.code(traceback.format_exc())
    
#     if st.button("Очистить TEST_* из procurement", key="debug_clean_procurement"):
#         from db import get_engine
#         from sqlalchemy import text
#         engine = get_engine()
#         with engine.begin() as conn:
#             res = conn.execute(text("DELETE FROM procurement WHERE code LIKE 'TEST_%'"))
#             st.success(f"Удалено: {res.rowcount}")

st.sidebar.caption("© 2026 Инвентаризация v1.0.3")

# # --- DEBUG: проверка БД (временно) ---
# import config as _cfg
# from db import check_db_connection
# with st.sidebar:
#     st.caption("--- DEBUG DB ---")
#     _db_ok, _db_msg = check_db_connection()
#     if _db_ok:
#         st.success(f"✅ {_db_msg}")
#     else:
#         st.warning(f"⚠️ {_db_msg}")
#     st.caption(f"DB_ENABLED: {_cfg.DB_ENABLED}")
#     st.caption(f"DB_NAME: {_cfg.DB_NAME or '(пусто)'}")
# # --- /DEBUG ---

# --- Маршрутизация (Роутинг) ---
if app_mode == "Поиск":
    search_view.render()
elif app_mode == "Аналитика":
    analytics_view.render()
elif app_mode == "Сканирование":
    scanning_view.render()
elif app_mode == "Редактирование":
    from views import edit_view
    edit_view.render()
elif app_mode == "Администрирование":
    from views import admin_view
    admin_view.render()