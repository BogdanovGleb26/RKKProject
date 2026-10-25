"""
Импорт данных из Excel в PostgreSQL.

Читает листы «Закупки», «ОС Главная», «Пластик», «Настройка печати»
из текущего источника (local / yadisk) и заменяет данные в БД (TRUNCATE + INSERT).

Использование:
    from import_excel import get_excel_preview, run_full_import

    # Шаг 1: проверить, что будет импортировано
    preview = get_excel_preview(source="local")

    # Шаг 2: выполнить импорт
    result = run_full_import(source="local")
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text

import config
from db import get_engine
from data_loader import load_data

logger = logging.getLogger("app.import")


# =============================================================================
# Маппинг: {db_column: [варианты имени в Excel]}
# Все имена в нижнем регистре, ё → е. При сравнении нормализуем колонку Excel.
# =============================================================================

PROCUREMENT_MAPPING: dict[str, list[str]] = {
    "code":                        ["код"],
    "okpd2":                       ["код окпд2"],
    "nomenclature":                ["номенклатура"],
    "qr_code":                     ["qr код"],
    "status":                      ["статус"],
    "project":                     ["проект"],
    "mto_service":                 ["мто/услуга", "мто / услуга"],
    "price":                       ["цена"],
    "quantity":                    ["кол-во", "количество"],
    "amount":                      ["сумма"],
    "packaging":                   ["упаковка"],
    "unit":                        ["ед. изм.", "ед.изм.", "ед изм"],
    "plan_line":                   ["строка плана закупки"],
    "need_plan":                   ["план потребности"],
    "mtr_plan":                    ["план мтр"],
    "mto_department":              ["отдел мто"],
    "mto_curator":                 ["куратор мто"],
    "supplier_invoice_approved":   ["счет поставщика согласован", "счёт поставщика согласован"],
    "final_price":                 ["цена финальная"],
    "final_amount":                ["сумма финальная"],
    "purchase_request":            ["заявка на закупку"],
    "payment_request":             ["заявка на оплату"],
    "receipt_order":               ["приходный ордер"],
    "paid":                        ["оплачено"],
    "received_to_warehouse":       ["получено со склада"],
    "cancelled":                   ["отменено"],
    "link":                        ["ссылка"],
    "remainder":                   ["остаток"],
    "storage_location":            ["место хранения"],
    "written_off":                 ["списано"],
}

OS_MAIN_MAPPING: dict[str, list[str]] = {
    "code":                        ["код"],
    "okpd2":                       ["код окпд2"],
    "nomenclature":                ["номенклатура"],
    "qr_code":                     ["qr код"],
    "status":                      ["статус"],
    "project":                     ["проект"],
    "mto_service":                 ["мто/услуга", "мто / услуга"],
    "price":                       ["цена"],
    "quantity":                    ["кол-во", "количество"],
    "amount":                      ["сумма"],
    "packaging":                   ["упаковка"],
    "unit":                        ["ед. изм.", "ед.изм.", "ед изм"],
    "plan_line":                   ["строка плана закупки"],
    "need_plan":                   ["план потребности"],
    "mtr_plan":                    ["план мтр"],
    "mto_department":              ["отдел мто"],
    "mto_curator":                 ["куратор мто"],
    "supplier_invoice_approved":   ["счет поставщика согласован", "счёт поставщика согласован"],
    "final_price":                 ["цена финальная"],
    "final_amount":                ["финальная сумма", "сумма финальная"],
    "purchase_request":            ["заявка на закупку"],
    "payment_request":             ["заявка на оплату"],
    "receipt_order":               ["приходный ордер"],
    "paid":                        ["оплачено"],
    "received_to_warehouse":       ["получено со склада"],
    "link":                        ["ссылка"],
    "remainder":                   ["остаток"],
    "storage_location":            ["место хранения"],
    # cancelled, written_off — нет в листе «ОС Главная», будут NULL
}

PLASTIC_MAPPING: dict[str, list[str]] = {
    "name":              ["название"],
    "type":              ["тип"],
    "color":             ["цвет"],
    "weight":            ["вес"],
    "qr_code":           ["qr код"],
    "code":              ["код"],
    "storage_location":  ["место хранения"],
}

SETTINGS_MAPPING: dict[str, list[str]] = {
    "plastic_type":  ["тип пластика"],
    "nozzle_temp":   ["сопло (°c)", "сопло (°с)", "сопло"],
    "bed_temp":      ["стол (°c)", "стол (°с)", "стол"],
    "fan_speed":     ["обдув, %", "обдув,%", "обдув"],
    "notes":         ["особенности и рекомендации"],
}


# =============================================================================
# Типы полей (для парсинга)
# =============================================================================

PROCUREMENT_NUMERIC = {
    "price", "quantity", "amount", "final_price", "final_amount", "remainder",
}
OS_MAIN_NUMERIC = PROCUREMENT_NUMERIC
PLASTIC_NUMERIC = {"weight"}
SETTINGS_NUMERIC = set()


# =============================================================================
# Хелперы
# =============================================================================

def _normalize_column_name(name: str) -> str:
    """Приводит имя колонки Excel к единому виду для сравнения."""
    s = str(name).strip().lower().replace("ё", "е")
    # Схлопываем множественные пробелы
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    # Если в строке есть разделитель диапазона (–, —, -), не парсим как одно число
    if re.search(r"[––—-]", raw) and re.search(r"\d", raw):
        # Это может быть диапазон, дата или отрицательное число.
        # Пытаемся распарсить только явно отрицательное число: -123.45
        if re.fullmatch(r"\s*-\s*\d+([.,]\d+)?\s*", raw):
            raw = raw.replace(" ", "")
        else:
            # Похоже на диапазон — не парсим
            return None

    clean = re.sub(r"[^\d.,-]", "", raw)
    if not clean:
        return None

    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    else:
        clean = clean.replace(",", ".")

    try:
        return float(clean)
    except ValueError:
        return None


def _parse_percent(value: Any) -> Optional[str]:
    """Парсит процент: 1.0 → '100%', 0.3 → '30%', '30 – 60%' → '30 – 60%'.
    Excel хранит проценты как 0..1, поэтому умножаем на 100.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return f"{round(float(value) * 100)}%"
    raw = str(value).strip()
    if not raw:
        return None
    if "%" in raw:
        return raw  # уже с процентом
    try:
        return f"{round(float(raw) * 100)}%"
    except ValueError:
        return raw


def _parse_text(value: Any) -> Optional[str]:
    """Парсит текстовое значение. None, если пусто."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def _parse_code(value: Any) -> Optional[str]:
    """Парсит код: убирает .0 в конце (Excel-артефакт), сохраняет ведущие нули."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        # Если int — вернуть как строку без .0
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    s = str(value).strip()
    if not s:
        return None
    # Excel может добавить .0 к числовым кодам, введённым как числа
    s = re.sub(r"\.0+$", "", s)
    return s


def _map_columns(df: pd.DataFrame, mapping: dict[str, list[str]]) -> dict[str, str]:
    """Возвращает {db_column: excel_column} для найденных колонок.

    Если для db_column нет соответствия в Excel — колонка отсутствует в словаре.
    """
    normalized_excel = {_normalize_column_name(c): c for c in df.columns}
    result: dict[str, str] = {}
    for db_col, variants in mapping.items():
        for v in variants:
            if v in normalized_excel:
                result[db_col] = normalized_excel[v]
                break
    return result


@dataclass
class ImportStats:
    """Статистика импорта одной таблицы."""
    table: str
    rows_in_excel: int = 0
    rows_inserted: int = 0
    rows_with_errors: int = 0
    missing_columns: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)


# =============================================================================
# Публичные функции
# =============================================================================

@dataclass
class PreviewResult:
    """Результат предварительной проверки — что будет импортировано."""
    source: str
    db_counts: dict[str, int]
    excel_counts: dict[str, int]


def get_excel_preview(source: str) -> PreviewResult:
    """Считает строки в Excel и в БД для всех 4 таблиц.

    Используется в UI для показа «до импорта».
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    # Считаем строки в БД
    db_counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table in ("procurement", "os_main", "plastic_spools", "plastic_settings"):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            db_counts[table] = int(count or 0)

    # Считаем строки в Excel
    excel_counts: dict[str, int] = {}
    sheet_map = {
        "procurement": "Закупки",
        "os_main": "ОС Главная",
        "plastic_spools": "Пластик",
        "plastic_settings": "Настройка печати",
    }
    for table, sheet_name in sheet_map.items():
        try:
            df, _ = load_data(sheet_name, source=source)
            excel_counts[table] = len(df)
        except Exception as e:
            logger.exception("Не удалось прочитать лист %r для preview", sheet_name)
            excel_counts[table] = -1  # -1 = ошибка

    return PreviewResult(
        source=source,
        db_counts=db_counts,
        excel_counts=excel_counts,
    )


def _import_one_table(
    df: pd.DataFrame,
    table: str,
    mapping: dict[str, list[str]],
    numeric_cols: set[str],
    code_cols: set[str],
    percent_cols: set[str] = frozenset(),
) -> ImportStats:
    """Импортирует один лист в одну таблицу. TRUNCATE + INSERT."""
    stats = ImportStats(table=table, rows_in_excel=len(df))

    if df.empty:
        logger.warning("Лист для %r пуст — TRUNCATE без вставки", table)
        # Всё равно очищаем таблицу
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY"))
        return stats

    # Маппинг колонок
    col_map = _map_columns(df, mapping)
    mapped_db_cols = set(col_map.keys())
    all_db_cols = set(mapping.keys())
    stats.missing_columns = sorted(all_db_cols - mapped_db_cols)

    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    inserted = 0
    errors = 0

    with engine.begin() as conn:
        # TRUNCATE
        conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY"))

        # INSERT по одной строке (позволит отслеживать ошибки)
        db_columns = list(col_map.keys())
        placeholders = ", ".join(f":{c}" for c in db_columns)
        insert_sql = text(
            f"INSERT INTO {table} ({', '.join(db_columns)}) VALUES ({placeholders})"
        )

        for idx, row in df.iterrows():
            params: dict[str, Any] = {}
            has_error = False
            for db_col in db_columns:
                excel_col = col_map[db_col]
                raw = row[excel_col]

                if db_col in code_cols:
                    parsed = _parse_code(raw)
                elif db_col in percent_cols:
                    parsed = _parse_percent(raw)
                elif db_col in numeric_cols:
                    parsed = _parse_number(raw)
                elif db_col in numeric_cols:
                    parsed = _parse_number(raw)
                    if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                        if str(raw).strip() and parsed is None:
                            has_error = True
                            if len(stats.error_messages) < 5:
                                stats.error_messages.append(
                                    f"Строка {idx + 2}, поле «{db_col}»: "
                                    f"не удалось распарсить {raw!r} → NULL"
                                )
                else:
                    parsed = _parse_text(raw)

                params[db_col] = parsed

            try:
                conn.execute(insert_sql, params)
                inserted += 1
                if has_error:
                    errors += 1
            except Exception as e:
                errors += 1
                logger.exception("Ошибка INSERT в %r, строка %d", table, idx + 2)
                if len(stats.error_messages) < 5:
                    stats.error_messages.append(f"Строка {idx + 2}: {e}")

    stats.rows_inserted = inserted
    stats.rows_with_errors = errors
    logger.info(
        "Импорт %r: в Excel %d, вставлено %d, с ошибками %d, отсутствуют колонки: %s",
        table, stats.rows_in_excel, inserted, errors, stats.missing_columns,
    )
    return stats


def run_full_import(source: str) -> list[ImportStats]:
    """Импортирует все 4 листа в БД. TRUNCATE + INSERT.

    :return: список ImportStats — по одной на таблицу.
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    logger.info("=== Начат полный импорт из источника %r ===", source)

    results: list[ImportStats] = []

    # 1. procurement
    df, _ = load_data("Закупки", source=source)
    results.append(_import_one_table(
        df, "procurement", PROCUREMENT_MAPPING,
        numeric_cols=PROCUREMENT_NUMERIC,
        code_cols={"code"},
    ))

    # 2. os_main
    df, _ = load_data("ОС Главная", source=source)
    results.append(_import_one_table(
        df, "os_main", OS_MAIN_MAPPING,
        numeric_cols=OS_MAIN_NUMERIC,
        code_cols={"code"},
    ))

    # 3. plastic_spools
    df, _ = load_data("Пластик", source=source)
    results.append(_import_one_table(
        df, "plastic_spools", PLASTIC_MAPPING,
        numeric_cols=PLASTIC_NUMERIC,
        code_cols={"code"},
    ))

    # 4. plastic_settings
    df, _ = load_data("Настройка печати", source=source)
    results.append(_import_one_table(
        df, "plastic_settings", SETTINGS_MAPPING,
        numeric_cols=SETTINGS_NUMERIC,
        code_cols=set(),
        percent_cols={"fan_speed"},
    ))

    logger.info("=== Полный импорт завершён ===")
    return results