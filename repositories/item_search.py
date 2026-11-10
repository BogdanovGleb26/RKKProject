"""
Поиск предметов по qr_code во всех 3 таблицах.

Поддерживает источники:
- postgres — SELECT в БД.
- local / yadisk — поиск в DataFrame (Excel), с маппингом
  русских колонок → английские.
"""

import logging
from typing import Optional

import pandas as pd
import streamlit as st
from sqlalchemy import text

import config
from db import get_engine, get_sheet_df, SHEET_REVERSE_MAP

logger = logging.getLogger("app.repo.item_search")


# =============================================================================
# Маппинг: английские имена → русские (для отображения в item_card)
# =============================================================================

# SHEET_REVERSE_MAP в db.py уже содержит {sheet_name: {eng: rus}}.
# Строим обратный: {sheet_name: {rus: eng}}.
SHEET_FORWARD_MAP: dict[str, dict[str, str]] = {
    sheet: {rus: eng for eng, rus in mapping.items()}
    for sheet, mapping in SHEET_REVERSE_MAP.items()
}


# =============================================================================
# Описание таблиц
# =============================================================================

# (table_id, table_label, sheet_name)
QR_TABLES = [
    ("procurement", "Закупки", "Закупки"),
    ("os_main", "ОС Главная", "ОС Главная"),
    ("plastic_spools", "Пластик", "Пластик"),
]


# =============================================================================
# Поиск в БД (postgres)
# =============================================================================

def _find_in_db(qr_code: str) -> list[dict]:
    """SELECT в БД."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    results: list[dict] = []

    with engine.connect() as conn:
        for table, label, _sheet in QR_TABLES:
            rows = conn.execute(
                text(f"""
                    SELECT * FROM {table}
                    WHERE qr_code = :qr AND is_deleted = FALSE
                    ORDER BY id
                """),
                {"qr": qr_code},
            ).mappings().all()

            for row in rows:
                results.append({
                    "table": table,
                    "table_label": label,
                    "data": dict(row),
                })

    return results


# =============================================================================
# Поиск в DataFrame (Excel: local / yadisk)
# =============================================================================

def _find_qr_column(df: pd.DataFrame) -> Optional[str]:
    """Ищет колонку с QR-кодом в DataFrame (Excel).

    В Excel это «QR код» (с пробелом и маленькой 'к').
    Но может быть вариация — ищем регистронезависимо.
    """
    for col in df.columns:
        normalized = str(col).strip().lower().replace("ё", "е")
        if normalized in ("qr код", "qr-code", "qr_code", "qrкод"):
            return col
    return None


def _find_in_dataframe(qr_code: str, source: str) -> list[dict]:
    """Поиск в DataFrame через get_sheet_df (Excel: local / yadisk)."""
    results: list[dict] = []

    for table, label, sheet_name in QR_TABLES:
        try:
            df, _ = get_sheet_df(sheet_name, source=source)
        except Exception:
            logger.exception("Не удалось загрузить %r для поиска по QR", sheet_name)
            continue

        if df.empty:
            continue

        qr_col = _find_qr_column(df)
        if qr_col is None:
            logger.warning("В листе %r нет колонки QR код", sheet_name)
            continue

        # Точное совпадение (без регистра и пробелов)
        mask = df[qr_col].astype(str).str.strip().str.lower() == qr_code.lower()
        matched = df[mask]

        if matched.empty:
            continue

        # Маппинг русских колонок → английские (для item_card)
        forward = SHEET_FORWARD_MAP.get(sheet_name, {})

        for idx, row in matched.iterrows():
            data: dict = {}
            for col, val in row.items():
                # Пропускаем служебное _search_corpus
                if col == "_search_corpus":
                    continue
                # Маппинг: русский → английский (если есть)
                eng = forward.get(col, col)
                data[eng] = val
            # id: в Excel его нет — используем индекс строки
            data.setdefault("id", int(idx) if not isinstance(idx, str) else None)

            results.append({
                "table": table,
                "table_label": label,
                "data": data,
            })

    return results


# =============================================================================
# Публичная функция
# =============================================================================

def find_items_by_qr_code(qr_code: str) -> list[dict]:
    """Ищет записи по qr_code во всех 3 таблицах.

    Автоматически определяет источник (из session_state.data_source):
    - postgres → SELECT в БД.
    - local / yadisk → поиск в DataFrame (Excel).

    Возвращает [{table, table_label, data}, ...].
    """
    if not qr_code or not qr_code.strip():
        return []

    qr_code_clean = qr_code.strip()
    source = st.session_state.get("data_source", config.DEFAULT_DATA_SOURCE)

    logger.info(
        "find_items_by_qr_code: qr=%r, source=%r", qr_code_clean, source,
    )

    if source == "postgres":
        results = _find_in_db(qr_code_clean)
    else:
        results = _find_in_dataframe(qr_code_clean, source)

    logger.info("find_items_by_qr_code: найдено %d записей", len(results))
    return results