"""
Модуль аутентификации и управления пользователями.

- argon2 для хеширования паролей.
- Аудит (created_by / updated_by) — НЕ здесь (см. session_state.audit_name).
"""

import logging
from typing import Optional
import config

import streamlit as st
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

from db import get_engine

logger = logging.getLogger("app.auth")

_ph = PasswordHasher()


# =============================================================================
# Пароли
# =============================================================================

def hash_password(password: str) -> str:
    """Хеширует пароль через argon2."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша. False при любой ошибке."""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
    except Exception:
        logger.exception("Ошибка проверки пароля")
        return False


# =============================================================================
# Пользователи
# =============================================================================

def get_user_by_username(username: str) -> Optional[dict]:
    """Возвращает пользователя по логину (включая password_hash)."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE username = :u"),
            {"u": username},
        )
        row = result.mappings().first()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None


def list_users() -> list[dict]:
    """Возвращает всех пользователей (без password_hash)."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, username, role, is_active, created_at, updated_at
                FROM users
                ORDER BY id
            """)
        )
        return [dict(r) for r in result.mappings().all()]


def create_user(username: str, password: str, role: str) -> int:
    """Создаёт пользователя. Возвращает id."""
    if role not in ("admin", "editor", "viewer"):
        raise ValueError(f"Неверная роль: {role}")
    if not username.strip():
        raise ValueError("Логин не может быть пустым")
    if len(password) < 4:
        raise ValueError("Пароль слишком короткий (минимум 4 символа)")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    hashed = hash_password(password)

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO users (username, password_hash, role)
                    VALUES (:u, :h, :r)
                    RETURNING id
                """),
                {"u": username.strip(), "h": hashed, "r": role},
            )
            new_id = result.scalar()
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise ValueError(f"Пользователь «{username}» уже существует")
        raise

    logger.info("create_user: id=%s username=%r role=%r", new_id, username, role)
    return new_id


def change_password(user_id: int, new_password: str) -> bool:
    """Меняет пароль пользователя."""
    if len(new_password) < 4:
        raise ValueError("Пароль слишком короткий (минимум 4 символа)")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    hashed = hash_password(new_password)

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE users
                SET password_hash = :h, updated_at = NOW()
                WHERE id = :id
            """),
            {"h": hashed, "id": user_id},
        )
        ok = result.rowcount > 0

    logger.info("change_password: id=%s ok=%s", user_id, ok)
    return ok


def set_active(user_id: int, active: bool) -> bool:
    """Блокирует / разблокирует пользователя."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE users
                SET is_active = :a, updated_at = NOW()
                WHERE id = :id
            """),
            {"a": active, "id": user_id},
        )
        ok = result.rowcount > 0

    logger.info("set_active: id=%s active=%s ok=%s", user_id, active, ok)
    return ok


def update_role(user_id: int, new_role: str) -> bool:
    """Меняет роль пользователя."""
    if new_role not in ("admin", "editor", "viewer"):
        raise ValueError(f"Неверная роль: {new_role}")

    engine = get_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL не сконфигурирован")

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE users
                SET role = :r, updated_at = NOW()
                WHERE id = :id
            """),
            {"r": new_role, "id": user_id},
        )
        ok = result.rowcount > 0

    logger.info("update_role: id=%s role=%r ok=%s", user_id, new_role, ok)
    return ok


# =============================================================================
# Аутентификация
# =============================================================================

def authenticate(username: str, password: str) -> tuple[Optional[dict], str]:
    """Проверяет логин/пароль.

    1. Если БД недоступна — проверяет fallback-креды (из .env).
    2. Иначе — стандартная проверка через users в БД.

    Возвращает (user_dict | None, error_message).
    """
    if not username or not password:
        return None, "Введите логин и пароль"

    username_clean = username.strip()
    password_clean = password.strip()

    # --- Определяем, доступна ли БД ---
    db_available = False
    try:
        engine = get_engine()
        if engine is not None:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_available = True
    except Exception:
        logger.warning("authenticate: БД недоступна, проверяю fallback")

    # --- Fallback (только когда БД недоступна) ---
    if not db_available:
        # Admin
        if (config.FALLBACK_ADMIN_USERNAME
                and config.FALLBACK_ADMIN_PASSWORD
                and username_clean == config.FALLBACK_ADMIN_USERNAME
                and password_clean == config.FALLBACK_ADMIN_PASSWORD):
            logger.warning(
                "authenticate: АВАРИЙНЫЙ ВХОД admin (username=%r, БД недоступна)",
                username_clean,
            )
            return {
                "id": -1,
                "username": config.FALLBACK_ADMIN_USERNAME,
                "role": "admin",
                "is_fallback": True,
            }, ""

        # Viewer
        if (config.FALLBACK_VIEWER_USERNAME
                and config.FALLBACK_VIEWER_PASSWORD
                and username_clean == config.FALLBACK_VIEWER_USERNAME
                and password_clean == config.FALLBACK_VIEWER_PASSWORD):
            logger.warning(
                "authenticate: АВАРИЙНЫЙ ВХОД viewer (username=%r, БД недоступна)",
                username_clean,
            )
            return {
                "id": -2,
                "username": config.FALLBACK_VIEWER_USERNAME,
                "role": "viewer",
                "is_fallback": True,
            }, ""

        return None, (
            "PostgreSQL недоступен. Используйте аварийный вход "
            "(учётные данные у администратора) или обратитесь к админу."
        )

    # --- Стандартная аутентификация через БД ---
    user = get_user_by_username(username_clean)
    if user is None:
        return None, "Неверный логин или пароль"

    if not user["is_active"]:
        return None, "Учётная запись заблокирована"

    if not verify_password(password_clean, user["password_hash"]):
        return None, "Неверный логин или пароль"

    logger.info("authenticate: успешный вход username=%r", user["username"])
    return (
        {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
        "",
    )


# =============================================================================
# Первый админ
# =============================================================================

@st.cache_resource(show_spinner=False)
def ensure_admin_exists() -> None:
    """Если в users нет ни одного админа — создаёт admin / admin123."""
    engine = get_engine()
    if engine is None:
        return  # БД не сконфигурирована — ничего не делаем

    try:
        with engine.begin() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            ).scalar()

            if count == 0:
                hashed = hash_password("admin123")
                conn.execute(
                    text("""
                        INSERT INTO users (username, password_hash, role)
                        VALUES ('admin', :h, 'admin')
                    """),
                    {"h": hashed},
                )
                logger.warning(
                    "Создан первый админ: admin / admin123. "
                    "Смените пароль после первого входа!"
                )
    except OperationalError:
        # БД недоступна — это нормально (приложение работает в fallback-режиме)
        logger.warning(
            "ensure_admin_exists: БД недоступна, проверка/создание админа пропущены"
        )
    except Exception:
        # Таблица users ещё не создана (миграция не применена) — не падаем
        logger.exception("ensure_admin_exists: не удалось проверить/создать админа")


def require_role(min_role: str) -> None:
    """Проверяет, что текущий пользователь имеет нужную роль.

    min_role: 'viewer' | 'editor' | 'admin'
    Роли по возрастанию прав: viewer < editor < admin.
    """
    role_order = {"viewer": 0, "editor": 1, "admin": 2}

    current_user = st.session_state.get("current_user")
    if not current_user:
        raise PermissionError("Не авторизован")

    user_role = current_user.get("role")
    if role_order.get(user_role, -1) < role_order.get(min_role, 999):
        raise PermissionError(
            f"Недостаточно прав: требуется роль «{min_role}» или выше, "
            f"у вас «{user_role}»."
        )