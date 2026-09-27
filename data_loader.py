import io
import datetime
import pandas as pd
import streamlit as st
import yadisk
from config import TOKEN, DISK_PATH

@st.cache_data(ttl=300)
def load_data(sheet_name: str) -> tuple[pd.DataFrame, str]:
    """Загружает конкретный лист из Excel-файла на Яндекс.Диске."""
    y = yadisk.YaDisk(token=TOKEN)
    if not y.check_token():
        raise Exception("Неверный токен Яндекс.Диска")

    meta = y.get_meta(DISK_PATH)
    raw_modified = getattr(meta, "modified", None)

    if raw_modified:
        msk_time = raw_modified + datetime.timedelta(hours=3)
        formatted_modified = msk_time.strftime("%d.%m.%Y в %H:%M")
    else:
        formatted_modified = "Неизвестно"

    buffer = io.BytesIO()
    y.download(DISK_PATH, buffer)
    buffer.seek(0)

    excel_file = pd.ExcelFile(buffer, engine="calamine")

    if sheet_name not in excel_file.sheet_names:
        return pd.DataFrame(), formatted_modified

    df = excel_file.parse(sheet_name=sheet_name)

    if df.empty:
        return df, formatted_modified

    df = df.fillna("")

    if "Код" in df.columns:
        df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

    search_columns = [
        "Номенклатура", "Код", "Место хранения", "Проект",
        "Куратор МТО", "Отдел МТО", "QR Код", "Название", "Тип", "Цвет"
    ]
    available_search_cols = [col for col in search_columns if col in df.columns]

    if available_search_cols:
        df["_search_corpus"] = (
            df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
        )
    else:
        df["_search_corpus"] = ""

    return df, formatted_modified