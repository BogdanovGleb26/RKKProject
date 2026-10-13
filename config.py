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

    if not TOKEN or not DISK_PATH or not LOCAL_FILE_PATH or DEFAULT_DATA_SOURCE not in ["yadisk", "local"]:
        st.error("❌ Не найдены необходимые переменные в файле .env!")
        st.stop()

    return TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE, images_dir

# Сразу экспортируем переменные для использования в других файлах
TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE, IMAGES_DIR = load_and_check_config()