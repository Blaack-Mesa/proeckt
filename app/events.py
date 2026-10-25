"""Простая шина событий (in-process) для слабой связанности модулей.

Модули публикуют события (publish), другие модули или тесты подписываются (subscribe).
Журнал событий хранится в памяти и используется для аудита и проверки в тестах.
"""
from collections import defaultdict
from typing import Callable

# Имена событий системы (см. раздел «Взаимодействие модулей» документа требований).
USER_REGISTERED = "user.registered"
USER_LOGGED_IN = "user.logged_in"
PASSWORD_RESET_REQUESTED = "user.password_reset_requested"
PASSWORD_CHANGED = "user.password_changed"
USER_ROLE_CHANGED = "user.role_changed"
TASK_CREATED = "task.created"
TASK_UPDATED = "task.updated"
TASK_STATUS_CHANGED = "task.status_changed"
TASK_DELETED = "task.deleted"
REPORT_GENERATED = "report.generated"

_subscribers = defaultdict(list)
_log: list = []


def subscribe(event: str, handler: Callable[[dict], None]) -> None:
    """Подписывает обработчик на событие."""
    _subscribers[event].append(handler)


def publish(event: str, payload: dict) -> None:
    """Публикует событие: пишет в журнал и вызывает подписчиков."""
    _log.append((event, dict(payload)))
    for handler in list(_subscribers[event]):
        handler(payload)


def history() -> list:
    """Копия журнала событий [(имя, данные), ...]."""
    return list(_log)


def clear() -> None:
    """Очищает журнал и подписчиков (используется в тестах)."""
    _log.clear()
    _subscribers.clear()
