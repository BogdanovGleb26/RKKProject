"""
CRUD-операции для plastic_settings (справочник «Настройка печати»).

Особенности:
- Нет аудита (created_by / updated_by).
- Нет оптимистичной блокировки (row_version).
- Жёсткое удаление (DELETE, не soft).
- plastic_type уникален (UNIQUE в БД).
"""

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import get_engine

from auth import require_role

logger = logging.getLogger("app.repo.plastic_settings")


# =============================================================================
# Поля
# =============================================================================

FIELD_TO_DB = {
    "plastic_type": "plastic_type",
    "nozzle_temp": "nozzle_temp",
    "bed_temp": "bed_temp",
    "fan_speed": "fan_speed",
    "notes": "notes",
}

EDITABLE_COLS = set(FIELD_TO_DB.keys())


# =============================================================================
# Чтение
# =============================================================================

def get_plastic_settings_by_id(item_id: int) -> Optional[dict]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM plastic_settings WHERE id = :id"),
            {"id": item_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None


# =============================================================================
# Создание
# =============================================================================

def create_plastic_settings(data: dict[str, Any], user: str) -> int:
    """user игнорируется (справочник без аудита)."""
    require_role("editor")
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        raise ValueError("Нет полей для вставки")

    placeholders = [f":{c}" for c in cols]

    sql = text(f"""
        INSERT INTO plastic_settings ({', '.join(cols)})
        VALUES ({', '.join(placeholders)})
        RETURNING id
    """)

    params = {c: data[c] for c in cols}

    try:
        with engine.begin() as conn:
            result = conn.execute(sql, params)
            new_id = result.scalar()
    except IntegrityError as e:
        # Нарушение UNIQUE по plastic_type
        if "plastic_settings_plastic_type_key" in str(e) or "unique" in str(e).lower():
            raise ValueError(
                f"Тип «{data.get('plastic_type', '')}» уже существует. Выберите другой."
            )
        raise

    logger.info("create_plastic_settings: id=%s type=%r", new_id, data.get("plastic_type"))
    return new_id


# =============================================================================
# Обновление
# =============================================================================

def update_plastic_settings(
    item_id: int,
    data: dict[str, Any],
    user: str,
) -> tuple[bool, str]:
    """Обновление без оптимистичной блокировки.
    user игнорируется (справочник без аудита)."""
    require_role("editor")
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        return False, "Нет полей для обновления"

    set_parts = [f"{c} = :{c}" for c in cols]

    sql = text(f"""
        UPDATE plastic_settings
        SET {', '.join(set_parts)}
        WHERE id = :id
    """)

    params = {**{c: data[c] for c in cols}, "id": item_id}

    try:
        with engine.begin() as conn:
            result = conn.execute(sql, params)
            if result.rowcount == 0:
                return False, "Запись не найдена."
    except IntegrityError as e:
        if "plastic_settings_plastic_type_key" in str(e) or "unique" in str(e).lower():
            return False, (
                f"Тип «{data.get('plastic_type', '')}» уже существует. Выберите другой."
            )
        raise

    logger.info("update_plastic_settings: id=%s", item_id)
    return True, "Сохранено"


# =============================================================================
# Удаление (жёсткое)
# =============================================================================

def delete_plastic_settings(item_id: int) -> bool:
    require_role("editor")
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM plastic_settings WHERE id = :id"),
            {"id": item_id},
        )
        ok = result.rowcount > 0

    logger.info("delete_plastic_settings: id=%s ok=%s", item_id, ok)
    return ok