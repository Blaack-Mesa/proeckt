"""Конечный автомат статусов задачи (модель — диаграмма состояний, документ §3).

Статусы: new → in_progress → review → done; review → rejected / in_progress;
rejected → new; new → rejected. Статус done — конечный.
"""
from ..errors import ApiError

NEW = "new"
IN_PROGRESS = "in_progress"
REVIEW = "review"
DONE = "done"
REJECTED = "rejected"

STATUSES = (NEW, IN_PROGRESS, REVIEW, DONE, REJECTED)

STATUS_LABELS = {
    NEW: "Новая",
    IN_PROGRESS: "В работе",
    REVIEW: "На проверке",
    DONE: "Завершена",
    REJECTED: "Отклонена",
}

# Разрешённые переходы модели: текущий статус -> множество допустимых следующих.
ALLOWED = {
    NEW: {IN_PROGRESS, REJECTED},
    IN_PROGRESS: {REVIEW},
    REVIEW: {DONE, REJECTED, IN_PROGRESS},
    DONE: set(),
    REJECTED: {NEW},
}

# Переходы, которые вправе выполнять исполнитель (только по своей задаче).
EXECUTOR_TRANSITIONS = {(NEW, IN_PROGRESS), (IN_PROGRESS, REVIEW)}


def transition_matrix() -> dict:
    """Матрица переходов {из: {в: True/False}} для всех пар статусов."""
    return {a: {b: b in ALLOWED[a] for b in STATUSES} for a in STATUSES}


def check_transition(current: str, target: str, role: str, is_assignee: bool) -> None:
    """Проверяет допустимость перехода и права; при нарушении — ApiError.

    400 invalid_status — неизвестный статус; 409 transition_not_allowed — переход
    запрещён моделью (в т.ч. «в тот же статус»); 403 forbidden — нет прав.
    """
    if target not in STATUSES:
        raise ApiError(400, "invalid_status", "Неизвестный статус задачи")
    if target not in ALLOWED.get(current, set()):
        raise ApiError(409, "transition_not_allowed",
                       f"Переход {current} → {target} запрещён")
    if role in ("admin", "manager"):
        return
    if role == "executor" and is_assignee and (current, target) in EXECUTOR_TRANSITIONS:
        return
    raise ApiError(403, "forbidden", "Недостаточно прав для смены статуса")
