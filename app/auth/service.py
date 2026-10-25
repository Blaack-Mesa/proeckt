"""AuthModule: бизнес-логика регистрации, входа, восстановления пароля и ролей."""
import re
import sqlite3

from flask import current_app

from .. import events
from ..db import get_db
from ..errors import ApiError
from ..security import (ROLES, create_token, decode_token, hash_password,
                        verify_password)
from ..utils import now_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email) -> str:
    """Нормализует (нижний регистр, без пробелов) и проверяет e-mail."""
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        raise ApiError(400, "invalid_email", "Некорректный e-mail")
    return email.strip().lower()


def validate_password(password) -> str:
    """Пароль: не короче MIN_PASSWORD_LEN, минимум одна буква и одна цифра."""
    min_len = current_app.config["MIN_PASSWORD_LEN"]
    if (not isinstance(password, str) or len(password) < min_len
            or not re.search(r"[A-Za-zА-Яа-я]", password)
            or not re.search(r"\d", password)):
        raise ApiError(400, "weak_password",
                       f"Пароль: минимум {min_len} символов, буквы и цифры")
    return password


def public_user(row) -> dict:
    """Представление пользователя без хеша пароля."""
    return {"id": row["id"], "email": row["email"], "full_name": row["full_name"],
            "role": row["role"], "is_active": bool(row["is_active"])}


def register_user(email, full_name, password, role: str = "executor") -> dict:
    """Регистрирует пользователя. Самостоятельная регистрация даёт роль executor."""
    email = validate_email(email)
    validate_password(password)
    if not isinstance(full_name, str) or not full_name.strip():
        raise ApiError(400, "invalid_name", "Укажите ФИО")
    if role not in ROLES:
        raise ApiError(400, "invalid_role", "Недопустимая роль")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (email, full_name, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (email, full_name.strip(), hash_password(password), role, now_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise ApiError(409, "email_taken", "Пользователь с таким e-mail уже существует") from exc
    user = get_user(cur.lastrowid)
    events.publish(events.USER_REGISTERED, {"user_id": user["id"], "role": user["role"]})
    return user


def get_user(user_id: int) -> dict:
    """Возвращает пользователя или ApiError 404."""
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ApiError(404, "user_not_found", "Пользователь не найден")
    return public_user(row)


def list_users() -> list:
    """Список всех пользователей (для администратора)."""
    rows = get_db().execute("SELECT * FROM users ORDER BY id").fetchall()
    return [public_user(r) for r in rows]


def authenticate(email, password) -> tuple:
    """Проверяет учётные данные; возвращает (jwt, user). Сообщение об ошибке единое."""
    row = None
    if isinstance(email, str) and isinstance(password, str):
        row = get_db().execute("SELECT * FROM users WHERE email = ?",
                               (email.strip().lower(),)).fetchone()
    if (row is None or not row["is_active"]
            or not verify_password(row["password_hash"], password)):
        raise ApiError(401, "invalid_credentials", "Неверный e-mail или пароль")
    events.publish(events.USER_LOGGED_IN, {"user_id": row["id"]})
    return create_token(row["id"], row["role"]), public_user(row)


def _reset_fingerprint(password_hash: str) -> str:
    """Отпечаток текущего хеша: делает токен восстановления одноразовым."""
    return password_hash[-12:]


def request_password_reset(email):
    """Создаёт токен восстановления. Для неизвестного e-mail возвращает None
    (вызывающий код отвечает одинаково, чтобы нельзя было перебирать адреса)."""
    try:
        email = validate_email(email)
    except ApiError:
        return None
    row = get_db().execute("SELECT * FROM users WHERE email = ? AND is_active = 1",
                           (email,)).fetchone()
    if row is None:
        return None
    token = create_token(row["id"], row["role"], purpose="reset",
                         expires_min=current_app.config["RESET_EXPIRES_MIN"],
                         extra={"fp": _reset_fingerprint(row["password_hash"])})
    events.publish(events.PASSWORD_RESET_REQUESTED, {"user_id": row["id"], "token": token})
    return token


def reset_password(token, new_password) -> None:
    """Устанавливает новый пароль по токену восстановления (токен одноразовый)."""
    if not isinstance(token, str):
        raise ApiError(400, "invalid_token", "Не указан токен")
    payload = decode_token(token, purpose="reset")
    validate_password(new_password)
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if row is None or payload.get("fp") != _reset_fingerprint(row["password_hash"]):
        raise ApiError(401, "token_invalid", "Токен уже использован или недействителен")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_password), row["id"]))
    db.commit()
    events.publish(events.PASSWORD_CHANGED, {"user_id": row["id"]})


def change_role(user_id: int, role: str) -> dict:
    """Меняет роль пользователя (операция администратора)."""
    if role not in ROLES:
        raise ApiError(400, "invalid_role", "Недопустимая роль")
    get_user(user_id)
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    events.publish(events.USER_ROLE_CHANGED, {"user_id": user_id, "role": role})
    return get_user(user_id)
