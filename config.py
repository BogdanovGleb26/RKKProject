import os
import streamlit as st
from dotenv import load_dotenv

def load_and_check_config():
    """Загружает переменные окружения и проверяет их наличие."""
    load_dotenv()
    TOKEN = os.getenv("YANDEX_TOKEN")
    DISK_PATH = os.getenv("DISK_PATH")

    LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH")
    DEFAULT_DATA_SOURCE = os.getenv("DATA_SOURCE", "yadisk").lower()

    if not TOKEN or not DISK_PATH or not LOCAL_FILE_PATH or DEFAULT_DATA_SOURCE not in ["yadisk", "local"]:
        st.error("❌ Не найдены переменные YANDEX_TOKEN или DISK_PATH в файле .env!")
        st.stop()
        
    return TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE

# Сразу экспортируем переменные для использования в других файлах
TOKEN, DISK_PATH, LOCAL_FILE_PATH, DEFAULT_DATA_SOURCE = load_and_check_config()