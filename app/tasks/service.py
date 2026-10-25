"""TaskModule: бизнес-логика проектов и задач."""
from .. import events
from ..db import get_db
from ..errors import ApiError
from ..utils import now_iso, parse_date, today
from . import state_machine as sm

TITLE_MAX = 200


def _validate_title(title) -> str:
    """Название: непустая строка не длиннее TITLE_MAX."""
    if not isinstance(title, str) or not title.strip():
        raise ApiError(400, "invalid_title", "Укажите название задачи")
    if len(title.strip()) > TITLE_MAX:
        raise ApiError(400, "invalid_title", f"Название длиннее {TITLE_MAX} символов")
    return title.strip()


def _validate_due_date(value):
    """Срок: пустое значение допустимо; дата не раньше сегодняшней (сегодня — можно)."""
    if value in (None, ""):
        return None
    due = parse_date(value, "due_date")
    if due < today():
        raise ApiError(400, "due_date_in_past", "Срок не может быть в прошлом")
    return due.isoformat()


def _validate_assignee(assignee_id):
    """Исполнитель должен существовать и быть активным."""
    if assignee_id is None:
        return None
    row = get_db().execute("SELECT id FROM users WHERE id = ? AND is_active = 1",
                           (assignee_id,)).fetchone() if isinstance(assignee_id, int) else None
    if row is None:
        raise ApiError(422, "assignee_not_found", "Исполнитель не найден")
    return assignee_id


def task_to_dict(row) -> dict:
    """Представление задачи для API."""
    data = dict(row)
    data["status_label"] = sm.STATUS_LABELS[data["status"]]
    return data


# ---------- проекты ----------

def create_project(user: dict, name, description="") -> dict:
    """Создаёт проект (владелец — текущий пользователь)."""
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, "invalid_name", "Укажите название проекта")
    db = get_db()
    cur = db.execute(
        "INSERT INTO projects (name, description, owner_id, created_at) VALUES (?, ?, ?, ?)",
        (name.strip(), description or "", user["id"], now_iso()))
    db.commit()
    return get_project(cur.lastrowid)


def get_project(project_id: int) -> dict:
    """Проект по id или 404."""
    row = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise ApiError(404, "project_not_found", "Проект не найден")
    return dict(row)


def list_projects() -> list:
    """Все проекты."""
    return [dict(r) for r in get_db().execute("SELECT * FROM projects ORDER BY id")]


# ---------- задачи ----------

def get_task_row(task_id: int):
    """Строка задачи или 404."""
    row = get_db().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    return row


def get_task(user: dict, task_id: int) -> dict:
    """Задача; исполнитель видит только назначенные ему задачи."""
    row = get_task_row(task_id)
    if user["role"] == "executor" and row["assignee_id"] != user["id"]:
        raise ApiError(403, "forbidden", "Нет доступа к задаче")
    return task_to_dict(row)


def create_task(user: dict, data: dict) -> dict:
    """Создаёт задачу в статусе «new» (manager/admin)."""
    title = _validate_title(data.get("title"))
    project = get_project(data.get("project_id")) if isinstance(
        data.get("project_id"), int) else None
    if project is None:
        raise ApiError(400, "invalid_project", "Укажите существующий project_id")
    due = _validate_due_date(data.get("due_date"))
    assignee = _validate_assignee(data.get("assignee_id"))
    now = now_iso()
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (project_id, title, description, status, assignee_id, "
        "creator_id, due_date, created_at, updated_at) VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?)",
        (project["id"], title, data.get("description") or "", assignee,
         user["id"], due, now, now))
    db.commit()
    task = task_to_dict(get_task_row(cur.lastrowid))
    events.publish(events.TASK_CREATED, {"task_id": task["id"], "project_id": project["id"],
                                         "assignee_id": assignee, "by": user["id"]})
    return task


def list_tasks(user: dict, project_id=None, status=None, assignee_id=None) -> list:
    """Список задач с фильтрами; исполнитель всегда видит только свои."""
    if status is not None and status not in sm.STATUSES:
        raise ApiError(400, "invalid_status", "Неизвестный статус задачи")
    if user["role"] == "executor":
        assignee_id = user["id"]
    return [task_to_dict(r) for r in query_tasks(assignee_id=assignee_id,
                                                 project_id=project_id, status=status)]


def update_task(user: dict, task_id: int, data: dict) -> dict:
    """Редактирует название, описание, срок, исполнителя (manager/admin).

    Завершённую задачу менять нельзя (409 task_closed).
    """
    row = get_task_row(task_id)
    if row["status"] == sm.DONE:
        raise ApiError(409, "task_closed", "Завершённую задачу нельзя изменять")
    fields = {}
    if "title" in data:
        fields["title"] = _validate_title(data["title"])
    if "description" in data:
        fields["description"] = data["description"] or ""
    if "due_date" in data:
        fields["due_date"] = _validate_due_date(data["due_date"])
    if "assignee_id" in data:
        fields["assignee_id"] = _validate_assignee(data["assignee_id"])
    if not fields:
        raise ApiError(400, "nothing_to_update", "Нет полей для изменения")
    fields["updated_at"] = now_iso()
    set_sql = ", ".join(f"{name} = ?" for name in fields)   # имена полей — из белого списка
    db = get_db()
    db.execute(f"UPDATE tasks SET {set_sql} WHERE id = ?", (*fields.values(), task_id))
    db.commit()
    events.publish(events.TASK_UPDATED, {"task_id": task_id, "fields": sorted(fields),
                                         "by": user["id"]})
    return task_to_dict(get_task_row(task_id))


def change_status(user: dict, task_id: int, new_status) -> dict:
    """Меняет статус по правилам конечного автомата."""
    row = get_task_row(task_id)
    sm.check_transition(row["status"], new_status, user["role"],
                        row["assignee_id"] == user["id"])
    if new_status == sm.IN_PROGRESS and row["assignee_id"] is None:
        raise ApiError(409, "assignee_required", "Перед началом работы назначьте исполнителя")
    db = get_db()
    db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
               (new_status, now_iso(), task_id))
    db.commit()
    events.publish(events.TASK_STATUS_CHANGED, {"task_id": task_id, "from": row["status"],
                                                "to": new_status, "by": user["id"]})
    return task_to_dict(get_task_row(task_id))


def delete_task(user: dict, task_id: int) -> None:
    """Удаляет задачу (manager/admin); завершённые задачи не удаляются."""
    row = get_task_row(task_id)
    if row["status"] == sm.DONE:
        raise ApiError(409, "task_closed", "Завершённую задачу нельзя удалить")
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    events.publish(events.TASK_DELETED, {"task_id": task_id, "by": user["id"]})


def query_tasks(assignee_id=None, project_id=None, status=None,
                date_from=None, date_to=None) -> list:
    """Выборка задач для API и для ReportModule (внутренний вызов).

    date_from/date_to — строки YYYY-MM-DD, фильтр по дате создания (включительно).
    """
    sql = ["SELECT t.*, u.full_name AS assignee_name, p.name AS project_name "
           "FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
           "JOIN projects p ON p.id = t.project_id WHERE 1 = 1"]
    params = []
    for column, value in (("t.assignee_id", assignee_id), ("t.project_id", project_id),
                          ("t.status", status)):
        if value is not None:
            sql.append(f"AND {column} = ?")
            params.append(value)
    if date_from:
        sql.append("AND substr(t.created_at, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        sql.append("AND substr(t.created_at, 1, 10) <= ?")
        params.append(date_to)
    sql.append("ORDER BY t.id")
    return get_db().execute(" ".join(sql), params).fetchall()
