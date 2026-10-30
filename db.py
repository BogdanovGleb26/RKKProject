"""
Модуль для работы с PostgreSQL.
"""

import logging
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import config


# --- Логирование ---
# Используем дочерний логгер "app.db". Root "app" настраивается в data_loader.py.
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# На всякий случай, если data_loader ещё не импортирован — настроим root сами.
_root_logger = logging.getLogger("app")
if not _root_logger.handlers:
    _handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    _root_logger.addHandler(_handler)
    _root_logger.setLevel(logging.INFO)

logger = logging.getLogger("app.db")


# =============================================================================
# Engine
# =============================================================================

def _build_db_url() -> str | None:
    if not config.DB_ENABLED:
        return None
    return (
        f"postgresql+psycopg2://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    )


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine | None:
    url = _build_db_url()
    if url is None:
        return None
    try:
        engine = create_engine(
            url,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        logger.info("SQLAlchemy engine создан для %s:%s/%s",
                    config.DB_HOST, config.DB_PORT, config.DB_NAME)
        return engine
    except Exception:
        logger.exception("Не удалось создать SQLAlchemy engine")
        return None


# =============================================================================
# Проверка
# =============================================================================

def check_db_connection() -> tuple[bool, str]:
    if not config.DB_ENABLED:
        return False, "PostgreSQL не сконфигурирован в .env"

    engine = get_engine()
    if engine is None:
        return False, "Ошибка инициализации подключения"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'procurement'"
            ))
            table_exists = result.scalar() > 0
        if not table_exists:
            logger.warning("БД доступна, но таблица procurement отсутствует")
            return False, "БД доступна, но схема не создана (нет таблиц)"
        logger.info("Проверка БД: OK")
        return True, f"PostgreSQL • {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    except Exception as e:
        logger.exception("Ошибка подключения к БД")
        return False, f"Ошибка: {type(e).__name__}"


# =============================================================================
# SELECT → DataFrame
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_df(query: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    logger.debug("fetch_df: %s | params=%s", query.strip()[:80], params)
    with engine.connect() as conn:
        if params:
            return pd.read_sql(text(query), conn, params=params)
        return pd.read_sql(text(query), conn)


# =============================================================================
# Чтение данных для вьюх (единый интерфейс с load_data)
# =============================================================================

# Маппинг: имя листа (как в Excel) → имя таблицы в БД
SHEET_TO_TABLE = {
    "Закупки": "procurement",
    "ОС Главная": "os_main",
    "Пластик": "plastic_spools",
    "Настройка печати": "plastic_settings",
}

# Для каждого листа — какие поля переименовываем обратно в «русские»,
# чтобы вьюхи работали с теми же названиями колонок, что и в Excel.
# ВАЖНО: это ключ к тому, чтобы search_view не переписывать целиком.

PROCUREMENT_REVERSE = {
    "code": "Код",
    "okpd2": "Код ОКПД2",
    "nomenclature": "Номенклатура",
    "qr_code": "QR код",
    "status": "Статус",
    "project": "Проект",
    "mto_service": "МТО/Услуга",
    "price": "Цена",
    "quantity": "Кол-во",
    "amount": "Сумма",
    "packaging": "Упаковка",
    "unit": "Ед. изм.",
    "plan_line": "Строка плана закупки",
    "need_plan": "План потребности",
    "mtr_plan": "План МТР",
    "mto_department": "Отдел МТО",
    "mto_curator": "Куратор МТО",
    "supplier_invoice_approved": "Счет поставщика согласован",
    "final_price": "Цена финальная",
    "final_amount": "Сумма финальная",
    "purchase_request": "Заявка на закупку",
    "payment_request": "Заявка на оплату",
    "receipt_order": "Приходный ордер",
    "paid": "Оплачено",
    "received_to_warehouse": "Получено со склада",
    "cancelled": "Отменено",
    "link": "Ссылка",
    "remainder": "Остаток",
    "storage_location": "Место хранения",
    "written_off": "Списано",
    "photo_path": "photo_path",
}

OS_MAIN_REVERSE = {
    "code": "Код",
    "okpd2": "Код ОКПД2",
    "nomenclature": "Номенклатура",
    "qr_code": "QR код",
    "status": "Статус",
    "project": "Проект",
    "mto_service": "МТО/Услуга",
    "price": "Цена",
    "quantity": "Кол-во",
    "amount": "Сумма",
    "packaging": "Упаковка",
    "unit": "Ед. изм.",
    "plan_line": "Строка плана закупки",
    "need_plan": "План потребности",
    "mtr_plan": "План МТР",
    "mto_department": "Отдел МТО",
    "mto_curator": "Куратор МТО",
    "supplier_invoice_approved": "Счет поставщика согласован",
    "final_price": "Цена финальная",
    "final_amount": "Финальная сумма",
    "purchase_request": "Заявка на закупку",
    "payment_request": "Заявка на оплату",
    "receipt_order": "Приходный ордер",
    "paid": "Оплачено",
    "received_to_warehouse": "Получено со склада",
    "link": "Ссылка",
    "remainder": "Остаток",
    "storage_location": "Место хранения",
    "photo_path": "photo_path",
}

PLASTIC_REVERSE = {
    "name": "Название",
    "type": "Тип",
    "color": "Цвет",
    "weight": "Вес",
    "qr_code": "QR код",
    "code": "Код",
    "storage_location": "Место хранения",
    "photo_path": "photo_path",
}

SETTINGS_REVERSE = {
    "plastic_type": "Тип пластика",
    "nozzle_temp": "Сопло (°C)",
    "bed_temp": "Стол (°C)",
    "fan_speed": "Обдув, %",
    "notes": "Особенности и рекомендации",
}

SHEET_REVERSE_MAP = {
    "Закупки": PROCUREMENT_REVERSE,
    "ОС Главная": OS_MAIN_REVERSE,
    "Пластик": PLASTIC_REVERSE,
    "Настройка печати": SETTINGS_REVERSE,
}


def _get_sheet_from_db(sheet_name: str) -> tuple[pd.DataFrame, str]:
    """Читает данные из БД и возвращает (DataFrame, last_updated).
    
    DataFrame — с русскими именами колонок (как в Excel),
    чтобы вьюхи работали без изменений.
    """
    table = SHEET_TO_TABLE.get(sheet_name)
    if table is None:
        raise ValueError(f"Неизвестный лист: {sheet_name!r}")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    # Для всех таблиц, кроме plastic_settings, фильтруем удалённые
    if table == "plastic_settings":
        query = f"SELECT * FROM {table} ORDER BY id"
    else:
        query = f"SELECT * FROM {table} WHERE is_deleted = FALSE ORDER BY id"

    df = fetch_df(query)

    if df.empty:
        return df, "—"

    # Переименовываем колонки в «русские»
    reverse_map = SHEET_REVERSE_MAP.get(sheet_name, {})
    df = df.rename(columns={k: v for k, v in reverse_map.items() if k in df.columns})

    # last_updated — пока updated_at ещё Timestamp
    if "updated_at" in df.columns:
        last = df["updated_at"].max()
        if pd.notna(last):
            last_str = pd.to_datetime(last).strftime("%d.%m.%Y в %H:%M (PostgreSQL)")
        else:
            last_str = "—"
    else:
        last_str = "—"

    # Убираем служебные колонки (уже не нужны)
    # id оставляем — он нужен для кнопок «Редактировать» / «Удалить».
    service_cols = [
        "is_deleted", "deleted_at", "deleted_by",
        "created_at", "created_by", "updated_at", "updated_by",
        "row_version",
    ]
    df = df.drop(columns=[c for c in service_cols if c in df.columns])

    # Заменяем NULL (NaN) на пустые строки — как в data_loader
    df = df.fillna("")

    # Формируем _search_corpus
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
    available = [c for c in search_columns if c in df.columns]
    if available:
        df["_search_corpus"] = (
            df[available]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
    else:
        df["_search_corpus"] = ""

    return df, last_str


def get_sheet_df(sheet_name: str, source: str) -> tuple[pd.DataFrame, str]:
    """Единая точка чтения: Excel (local/yadisk) или PostgreSQL (postgres).
    
    Возвращает (DataFrame, last_updated_str) — тот же формат, что load_data.
    """
    if source == "postgres":
        return _get_sheet_from_db(sheet_name)
    # Импорт внутри функции — чтобы избежать циклического импорта
    from data_loader import load_data
    return load_data(sheet_name, source=source)