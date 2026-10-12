import datetime
import io
import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import yadisk
from dataclasses import dataclass
from config import DEFAULT_DATA_SOURCE, DISK_PATH, LOCAL_FILE_PATH, TOKEN

# --- Логирование ---
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("data_loader")
if not logger.handlers:
    handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def _parse_and_prepare_df(
    excel_source, sheet_name: str, formatted_modified: str
) -> tuple[pd.DataFrame, str]:
  """Вспомогательная функция для парсинга и обработки структуры DataFrame."""
  excel_file = pd.ExcelFile(excel_source, engine="calamine")

  if sheet_name not in excel_file.sheet_names:
    return pd.DataFrame(), formatted_modified

  df = excel_file.parse(sheet_name=sheet_name)

  if df.empty:
    return df, formatted_modified

  df = df.fillna("")

  if "Код" in df.columns:
    df["Код"] = df["Код"].astype(str).str.replace(r"\.0$", "", regex=True)

  search_columns = [
      "Номенклатура",
      "Код",
      "Место хранения",
      "Проект",
      "Куратор МТО",
      "Отдел МТО",
      "QR код",
      "Название",
      "Тип",
      "Цвет",
  ]
  available_search_cols = [col for col in search_columns if col in df.columns]

  if available_search_cols:
    df["_search_corpus"] = (
        df[available_search_cols].astype(str).agg(" ".join, axis=1).str.lower()
    )
  else:
    df["_search_corpus"] = ""

  return df, formatted_modified


@st.cache_data(ttl=300)
def load_data(sheet_name: str, source: str = DEFAULT_DATA_SOURCE) -> tuple[pd.DataFrame, str]:
    logger.info("load_data start: sheet=%r source=%r", sheet_name, source)

    if source == "local":
        if not os.path.exists(LOCAL_FILE_PATH):
            logger.error("local file not found: %s", LOCAL_FILE_PATH)
            raise FileNotFoundError(
                f"Локальный файл не найден по пути: {LOCAL_FILE_PATH}"
            )
        try:
            mtime = os.path.getmtime(LOCAL_FILE_PATH)
        except OSError as e:
            logger.exception("local file access error")
            raise
        mod_time = datetime.datetime.fromtimestamp(mtime)
        formatted_modified = mod_time.strftime("%d.%m.%Y в %H:%M (ПК)")
        logger.info("local file mtime=%s", formatted_modified)

        df, _ = _parse_and_prepare_df(LOCAL_FILE_PATH, sheet_name, formatted_modified)
        logger.info("load_data done: sheet=%r rows=%d", sheet_name, len(df))
        return df, formatted_modified

    else:  # yadisk
        try:
            y = yadisk.YaDisk(token=TOKEN)
            if not y.check_token():
                logger.error("yadisk token invalid")
                raise Exception("Неверный токен Яндекс.Диска")

            meta = y.get_meta(DISK_PATH)
            raw_modified = getattr(meta, "modified", None)
            if raw_modified:
                msk_time = raw_modified + datetime.timedelta(hours=3)
                formatted_modified = msk_time.strftime("%d.%m.%Y в %H:%M (Я.Диск)")
            else:
                formatted_modified = "Неизвестно"

            buffer = io.BytesIO()
            y.download(DISK_PATH, buffer)
            buffer.seek(0)
            logger.info("yadisk downloaded: sheet=%r modified=%s", sheet_name, formatted_modified)
        except Exception:
            logger.exception("yadisk load failed: sheet=%r", sheet_name)
            raise

        df, _ = _parse_and_prepare_df(buffer, sheet_name, formatted_modified)
        logger.info("load_data done: sheet=%r rows=%d", sheet_name, len(df))
        return df, formatted_modified

@dataclass(frozen=True)
class SourceStatus:
    """Статус источника данных для UI."""
    source: str               # "yadisk" | "local"
    available: bool
    message: str              # короткое описание: дата, размер, ошибка
    modified: str | None = None  # форматированная дата модификации


def check_source(source: str) -> SourceStatus:
    """Быстрая проверка доступности источника без полной загрузки файла."""
    if source == "local":
        if not os.path.exists(LOCAL_FILE_PATH):
            return SourceStatus("local", False, "Файл не найден")
        try:
            mtime = os.path.getmtime(LOCAL_FILE_PATH)
            mod_time = datetime.datetime.fromtimestamp(mtime)
            formatted = mod_time.strftime("%d.%m.%Y %H:%M")
            size_mb = os.path.getsize(LOCAL_FILE_PATH) / (1024 * 1024)
            return SourceStatus(
                "local", True,
                f"Локальный файл • {size_mb:.1f} МБ",
                formatted,
            )
        except OSError as e:
            return SourceStatus("local", False, f"Ошибка доступа: {e}")

    # yadisk
    try:
        y = yadisk.YaDisk(token=TOKEN)
        if not y.check_token():
            return SourceStatus("yadisk", False, "Неверный токен")
        meta = y.get_meta(DISK_PATH)
        raw_modified = getattr(meta, "modified", None)
        if raw_modified:
            msk_time = raw_modified + datetime.timedelta(hours=3)
            formatted = msk_time.strftime("%d.%m.%Y %H:%M")
        else:
            formatted = None
        size = getattr(meta, "size", None)
        size_str = f" • {size / (1024 * 1024):.1f} МБ" if size else ""
        return SourceStatus("yadisk", True, f"Яндекс.Диск{size_str}", formatted)
    except Exception as e:
        return SourceStatus("yadisk", False, f"Ошибка: {type(e).__name__}")