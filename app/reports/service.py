"""ReportModule: формирование отчётов по задачам.

Данные берутся у TaskModule внутренним вызовом tasks.service.query_tasks().
"""
import json

from .. import events
from ..db import get_db
from ..errors import ApiError
from ..tasks import service as task_service
from ..tasks import state_machine as sm
from ..utils import now_iso, parse_date, today

REPORT_TYPES = ("assignee", "project", "period")
REPORT_TITLES = {
    "assignee": "Отчёт по исполнителю",
    "project": "Отчёт по проекту",
    "period": "Отчёт за период",
}


def _int_param(value, name: str) -> int:
    """Обязательный целочисленный параметр."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "missing_param", f"Параметр {name} обязателен") from exc


def build_report(user: dict, report_type: str, params: dict) -> dict:
    """Формирует отчёт, сохраняет запись в таблицу reports, публикует событие.

    Права: manager/admin — любые отчёты; executor — только по себе.
    """
    if report_type not in REPORT_TYPES:
        raise ApiError(404, "unknown_report", "Неизвестный тип отчёта")
    if user["role"] == "executor" and report_type != "assignee":
        raise ApiError(403, "forbidden", "Исполнителю доступен только отчёт по себе")

    filters = {}
    if report_type == "assignee":
        if user["role"] == "executor":
            filters["assignee_id"] = user["id"]
        else:
            filters["assignee_id"] = _int_param(params.get("assignee_id"), "assignee_id")
        if user["role"] == "executor" and params.get("assignee_id") not in (
                None, str(user["id"])):
            raise ApiError(403, "forbidden", "Можно получить отчёт только по себе")
    elif report_type == "project":
        filters["project_id"] = _int_param(params.get("project_id"), "project_id")
        task_service.get_project(filters["project_id"])      # 404, если проекта нет
    else:
        date_from = parse_date(params.get("date_from"), "date_from")
        date_to = parse_date(params.get("date_to"), "date_to")
        if date_from > date_to:
            raise ApiError(400, "invalid_period", "date_from позже date_to")
        filters["date_from"] = date_from.isoformat()
        filters["date_to"] = date_to.isoformat()

    rows = [dict(r) for r in task_service.query_tasks(**filters)]
    current = today().isoformat()
    by_status = {status: 0 for status in sm.STATUSES}
    overdue = 0
    for row in rows:
        by_status[row["status"]] += 1
        row["status_label"] = sm.STATUS_LABELS[row["status"]]
        if (row["due_date"] and row["due_date"] < current
                and row["status"] not in (sm.DONE, sm.REJECTED)):
            overdue += 1

    db = get_db()
    cur = db.execute(
        "INSERT INTO reports (report_type, params, rows_count, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (report_type, json.dumps(filters, ensure_ascii=False), len(rows), user["id"], now_iso()))
    db.commit()
    report = {
        "report_id": cur.lastrowid,
        "type": report_type,
        "title": REPORT_TITLES[report_type],
        "filters": filters,
        "generated_at": now_iso(),
        "summary": {"total": len(rows), "by_status": by_status, "overdue": overdue},
        "rows": rows,
    }
    events.publish(events.REPORT_GENERATED, {"report_id": report["report_id"],
                                             "type": report_type, "by": user["id"]})
    return report


def list_reports() -> list:
    """История сформированных отчётов."""
    rows = get_db().execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]
