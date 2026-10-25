"""Вспомогательные функции общего назначения."""
from datetime import date, datetime, timezone

from flask import request

from .errors import ApiError


def now_iso() -> str:
    """Текущее время UTC в формате ISO 8601 (секунды)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> date:
    """Текущая дата (UTC)."""
    return datetime.now(timezone.utc).date()


def parse_date(value, field: str) -> date:
    """Разбирает строку YYYY-MM-DD; при ошибке выбрасывает ApiError 400."""
    if not isinstance(value, str):
        raise ApiError(400, "invalid_date", f"Поле {field}: ожидается дата YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(400, "invalid_date", f"Поле {field}: неверная дата") from exc


def json_body() -> dict:
    """Возвращает JSON-тело запроса; требует, чтобы это был объект."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Тело запроса должно быть JSON-объектом")
    return data
