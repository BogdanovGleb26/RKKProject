import os
import streamlit as st
from dotenv import load_dotenv

def load_and_check_config():
    """Загружает переменные окружения и проверяет их наличие."""
    load_dotenv()
    TOKEN = os.getenv("YANDEX_TOKEN")
    DISK_PATH = os.getenv("DISK_PATH")

    if not TOKEN or not DISK_PATH:
        st.error("❌ Не найдены переменные YANDEX_TOKEN или DISK_PATH в файле .env!")
        st.stop()
        
    return TOKEN, DISK_PATH

# Сразу экспортируем переменные для использования в других файлах
TOKEN, DISK_PATH = load_and_check_config()