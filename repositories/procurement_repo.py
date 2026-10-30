"""
CRUD-операции для таблицы procurement.

Все функции используют get_engine() из db.py.
Для UPDATE — optimistic locking по row_version.
"""

import logging
from typing import Any, Optional

from sqlalchemy import text

from db import get_engine

logger = logging.getLogger("app.repo.procurement")


# =============================================================================
# Маппинг: поля формы (англ. имя) ↔ колонки БД (совпадают)
# =============================================================================

FIELD_TO_DB = {
    "code": "code",
    "okpd2": "okpd2",
    "nomenclature": "nomenclature",
    "qr_code": "qr_code",
    "status": "status",
    "project": "project",
    "mto_service": "mto_service",
    "price": "price",
    "quantity": "quantity",
    "amount": "amount",
    "packaging": "packaging",
    "unit": "unit",
    "plan_line": "plan_line",
    "need_plan": "need_plan",
    "mtr_plan": "mtr_plan",
    "mto_department": "mto_department",
    "mto_curator": "mto_curator",
    "supplier_invoice_approved": "supplier_invoice_approved",
    "final_price": "final_price",
    "final_amount": "final_amount",
    "purchase_request": "purchase_request",
    "payment_request": "payment_request",
    "receipt_order": "receipt_order",
    "paid": "paid",
    "received_to_warehouse": "received_to_warehouse",
    "cancelled": "cancelled",
    "link": "link",
    "remainder": "remainder",
    "storage_location": "storage_location",
    "written_off": "written_off",
}

# Колонки, которые редактируются через CRUD (не служебные)
EDITABLE_COLS = set(FIELD_TO_DB.keys())


# =============================================================================
# Чтение
# =============================================================================

def get_procurement_by_id(item_id: int) -> Optional[dict]:
    """Возвращает запись по id (для формы редактирования). None если нет/удалена."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM procurement WHERE id = :id AND is_deleted = FALSE"),
            {"id": item_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None


# =============================================================================
# Создание
# =============================================================================

def create_procurement(data: dict[str, Any], user: str) -> int:
    """Создаёт новую позицию. Возвращает id.

    :param data: {db_column: value}. Ключи — из FIELD_TO_DB.
                 Пустые значения (None, "") — сохраняются как NULL.
    :param user: имя пользователя (created_by / updated_by)
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        raise ValueError("Нет полей для вставки")

    placeholders = [f":{c}" for c in cols] + [":created_by", ":updated_by"]
    all_cols = cols + ["created_by", "updated_by"]

    sql = text(f"""
        INSERT INTO procurement ({', '.join(all_cols)})
        VALUES ({', '.join(placeholders)})
        RETURNING id
    """)

    params = {**{c: data[c] for c in cols}, "created_by": user, "updated_by": user}

    with engine.begin() as conn:
        result = conn.execute(sql, params)
        new_id = result.scalar()

    logger.info("create_procurement: id=%s code=%r user=%r", new_id, data.get("code"), user)
    return new_id


# =============================================================================
# Обновление
# =============================================================================

def update_procurement(
    item_id: int,
    data: dict[str, Any],
    expected_version: int,
    user: str,
) -> tuple[bool, str]:
    """Обновляет запись с optimistic locking.

    :param expected_version: текущая row_version (для проверки конфликта)
    :return: (ok, message)
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    cols = [c for c in data.keys() if c in EDITABLE_COLS]
    if not cols:
        return False, "Нет полей для обновления"

    set_parts = [f"{c} = :{c}" for c in cols]
    set_parts.append("row_version = row_version + 1")
    set_parts.append("updated_at = NOW()")
    set_parts.append("updated_by = :updated_by")

    sql = text(f"""
        UPDATE procurement
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
            # Либо запись не существует/удалена, либо конфликт версий
            exists = conn.execute(
                text("SELECT 1 FROM procurement WHERE id = :id AND is_deleted = FALSE"),
                {"id": item_id},
            ).scalar()
            if not exists:
                return False, "Позиция не найдена или уже удалена."
            return False, (
                "Позиция изменена другим пользователем с момента открытия формы. "
                "Закройте форму, обновите страницу и попробуйте снова."
            )

    logger.info("update_procurement: id=%s user=%r", item_id, user)
    return True, "Сохранено"


# =============================================================================
# Удаление (мягкое)
# =============================================================================

def delete_procurement(item_id: int, user: str) -> bool:
    """Мягкое удаление: is_deleted = TRUE. Возвращает True если запись обновлена."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE procurement
                SET is_deleted = TRUE,
                    deleted_at = NOW(),
                    deleted_by = :user,
                    row_version = row_version + 1
                WHERE id = :id AND is_deleted = FALSE
            """),
            {"id": item_id, "user": user},
        )
        ok = result.rowcount > 0

    logger.info("delete_procurement: id=%s ok=%s user=%r", item_id, ok, user)
    return ok