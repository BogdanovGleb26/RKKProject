"""
CRUD-операции для таблицы plastic_spools (Пластик).
"""

import logging
from typing import Any, Optional

from sqlalchemy import text

from db import get_engine

logger = logging.getLogger("app.repo.plastic")


# =============================================================================
# Поля
# =============================================================================

FIELD_TO_DB = {
    "name": "name",
    "type": "type",
    "color": "color",
    "weight": "weight",
    "qr_code": "qr_code",
    "code": "code",
    "storage_location": "storage_location",
}

EDITABLE_COLS = set(FIELD_TO_DB.keys())


# =============================================================================
# Чтение
# =============================================================================

def get_plastic_by_id(item_id: int) -> Optional[dict]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM plastic_spools WHERE id = :id AND is_deleted = FALSE"),
            {"id": item_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None


# =============================================================================
# Создание
# =============================================================================

def create_plastic(data: dict[str, Any], user: str) -> int:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        raise ValueError("Нет полей для вставки")

    placeholders = [f":{c}" for c in cols] + [":created_by", ":updated_by"]
    all_cols = cols + ["created_by", "updated_by"]

    sql = text(f"""
        INSERT INTO plastic_spools ({', '.join(all_cols)})
        VALUES ({', '.join(placeholders)})
        RETURNING id
    """)

    params = {**{c: data[c] for c in cols}, "created_by": user, "updated_by": user}

    with engine.begin() as conn:
        result = conn.execute(sql, params)
        new_id = result.scalar()

    logger.info("create_plastic: id=%s code=%r user=%r", new_id, data.get("code"), user)
    return new_id


# =============================================================================
# Обновление
# =============================================================================

def update_plastic(
    item_id: int,
    data: dict[str, Any],
    expected_version: int,
    user: str,
) -> tuple[bool, str]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        return False, "Нет полей для обновления"

    set_parts = [f"{c} = :{c}" for c in cols]
    set_parts.append("updated_by = :updated_by")

    sql = text(f"""
        UPDATE plastic_spools
        SET {', '.join(set_parts)}
        WHERE id = :id
          AND row_version = :expected_version
          AND is_deleted = FALSE
    """)

    params = {
        **{c: data[c] for c in cols},
        "id": item_id,
        "expected_version": expected_version,
        "updated_by": user,
    }

    with engine.begin() as conn:
        result = conn.execute(sql, params)
        if result.rowcount == 0:
            exists = conn.execute(
                text("SELECT 1 FROM plastic_spools WHERE id = :id AND is_deleted = FALSE"),
                {"id": item_id},
            ).scalar()
            if not exists:
                return False, "Позиция не найдена или уже удалена."
            return False, (
                "Позиция изменена другим пользователем с момента открытия формы. "
                "Закройте форму, обновите страницу и попробуйте снова."
            )

    logger.info("update_plastic: id=%s user=%r", item_id, user)
    return True, "Сохранено"


# =============================================================================
# Удаление (мягкое)
# =============================================================================

def delete_plastic(item_id: int, user: str) -> bool:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE plastic_spools
                SET is_deleted = TRUE,
                    deleted_at = NOW(),
                    deleted_by = :user
                WHERE id = :id AND is_deleted = FALSE
            """),
            {"id": item_id, "user": user},
        )
        ok = result.rowcount > 0

    logger.info("delete_plastic: id=%s ok=%s user=%r", item_id, ok, user)
    return ok