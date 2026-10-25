"""Единый механизм аутентификации и авторизации (JWT) для всех модулей."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .errors import ApiError

ROLES = ("admin", "manager", "executor")


def hash_password(password: str) -> str:
    """Хеш пароля (с солью, алгоритм по умолчанию werkzeug)."""
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Проверка пароля по хешу."""
    return check_password_hash(password_hash, password)


def create_token(user_id: int, role: str, purpose: str = "access",
                 expires_min: int = None, extra: dict = None) -> str:
    """Создаёт подписанный JWT. purpose: 'access' или 'reset'."""
    if expires_min is None:
        expires_min = current_app.config["JWT_EXPIRES_MIN"]
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),      # по RFC 7519 sub — строка
        "role": role,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(minutes=expires_min),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(token: str, purpose: str = "access") -> dict:
    """Проверяет подпись, срок и назначение токена; возвращает payload."""
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "token_expired", "Срок действия токена истёк") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, "token_invalid", "Недействительный токен") from exc
    if payload.get("purpose") != purpose:
        raise ApiError(401, "token_invalid", "Токен не подходит для этой операции")
    return payload


def auth_required(*roles):
    """Декоратор: требует Bearer-токен и (опционально) одну из ролей.

    Пользователь загружается из БД при каждом запросе, поэтому смена роли
    или блокировка вступают в силу сразу. Результат кладётся в g.current_user.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                raise ApiError(401, "auth_required", "Требуется авторизация")
            payload = decode_token(header[7:].strip())
            row = get_db().execute(
                "SELECT id, email, full_name, role, is_active FROM users WHERE id = ?",
                (int(payload["sub"]),),
            ).fetchone()
            if row is None or not row["is_active"]:
                raise ApiError(401, "auth_required", "Пользователь не найден или заблокирован")
            if roles and row["role"] not in roles:
                raise ApiError(403, "forbidden", "Недостаточно прав для операции")
            g.current_user = dict(row)
            return func(*args, **kwargs)
        return wrapper
    return decorator
