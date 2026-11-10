import os
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

def load_and_check_config():
    """Загружает переменные окружения и проверяет их наличие."""
    load_dotenv()
    TOKEN = os.getenv("YANDEX_TOKEN")
    DISK_PATH = os.getenv("DISK_PATH")

    LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH")
    DEFAULT_DATA_SOURCE = os.getenv("DATA_SOURCE", "yadisk").lower()

    # ← НОВОЕ: папка с картинками.
    # Если не задана — "images" рядом с проектом.
    raw_images_dir = (os.getenv("IMAGES_DIR") or "images").strip()
    images_dir = Path(raw_images_dir)
    if not images_dir.is_absolute():
        images_dir = Path(__file__).resolve().parent / images_dir

    # ← НОВОЕ: базовый URL формы для генерации QR-кодов.
    # Может быть пустым — тогда QR-генерация работать не будет,
    # и в карточке покажется плейсхолдер.
    qr_form_url = (os.getenv("QR_FORM_URL") or "").strip()

    # ← НОВОЕ: параметры PostgreSQL (все опциональны).
    # Если DB_ENABLED=true или все ключевые поля заданы — БД доступна как источник.
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_port = (os.getenv("DB_PORT") or "5432").strip()
    db_name = (os.getenv("DB_NAME") or "").strip()
    db_user = (os.getenv("DB_USER") or "").strip()
    db_password = (os.getenv("DB_PASSWORD") or "").strip()
    db_enabled = bool(db_host and db_name and db_user and db_password)

    # --- Аварийный вход (fallback) ---
    fallback_admin_username = (os.getenv("FALLBACK_ADMIN_USERNAME") or "").strip()
    fallback_admin_password = (os.getenv("FALLBACK_ADMIN_PASSWORD") or "").strip()
    fallback_viewer_username = (os.getenv("FALLBACK_VIEWER_USERNAME") or "").strip()
    fallback_viewer_password = (os.getenv("FALLBACK_VIEWER_PASSWORD") or "").strip()

    if not TOKEN or not DISK_PATH or not LOCAL_FILE_PATH or DEFAULT_DATA_SOURCE not in ["yadisk", "local"]:
        st.error("❌ Не найдены нужные переменные в кредах!")
        st.stop()

    return (
        TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE,
        images_dir, qr_form_url,
        db_host, db_port, db_name, db_user, db_password, db_enabled,
        fallback_admin_username, fallback_admin_password,
        fallback_viewer_username, fallback_viewer_password,
    )

# Сразу экспортируем переменные для использования в других файлах
(
    TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE,
    IMAGES_DIR, QR_FORM_URL,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_ENABLED,
    FALLBACK_ADMIN_USERNAME, FALLBACK_ADMIN_PASSWORD,
    FALLBACK_VIEWER_USERNAME, FALLBACK_VIEWER_PASSWORD,
) = load_and_check_config()