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