"""TaskModule: REST-эндпоинты /api/projects/* и /api/tasks/*."""
from flask import Blueprint, g, jsonify, request

from ..security import auth_required
from ..utils import json_body
from . import service, state_machine

bp = Blueprint("tasks", __name__, url_prefix="/api")


@bp.post("/projects")
@auth_required("admin", "manager")
def create_project():
    """POST /api/projects — создать проект."""
    data = json_body()
    project = service.create_project(g.current_user, data.get("name"), data.get("description"))
    return jsonify(project), 201


@bp.get("/projects")
@auth_required()
def list_projects():
    """GET /api/projects — список проектов."""
    return jsonify(service.list_projects())


@bp.get("/projects/<int:project_id>")
@auth_required()
def get_project(project_id):
    """GET /api/projects/<id>."""
    return jsonify(service.get_project(project_id))


@bp.post("/tasks")
@auth_required("admin", "manager")
def create_task():
    """POST /api/tasks — создать задачу."""
    return jsonify(service.create_task(g.current_user, json_body())), 201


@bp.get("/tasks")
@auth_required()
def list_tasks():
    """GET /api/tasks?project_id=&status=&assignee_id= — список задач."""
    args = request.args
    project_id = args.get("project_id", type=int)
    assignee_id = args.get("assignee_id", type=int)
    return jsonify(service.list_tasks(g.current_user, project_id, args.get("status"),
                                      assignee_id))


@bp.get("/tasks/transitions")
@auth_required()
def transitions():
    """GET /api/tasks/transitions — матрица допустимых переходов статусов."""
    return jsonify(state_machine.transition_matrix())


@bp.get("/tasks/<int:task_id>")
@auth_required()
def get_task(task_id):
    """GET /api/tasks/<id>."""
    return jsonify(service.get_task(g.current_user, task_id))


@bp.patch("/tasks/<int:task_id>")
@auth_required("admin", "manager")
def update_task(task_id):
    """PATCH /api/tasks/<id> — редактирование."""
    return jsonify(service.update_task(g.current_user, task_id, json_body()))


@bp.post("/tasks/<int:task_id>/status")
@auth_required()
def change_status(task_id):
    """POST /api/tasks/<id>/status {"status": "..."} — смена статуса."""
    return jsonify(service.change_status(g.current_user, task_id, json_body().get("status")))


@bp.delete("/tasks/<int:task_id>")
@auth_required("admin", "manager")
def delete_task(task_id):
    """DELETE /api/tasks/<id>."""
    service.delete_task(g.current_user, task_id)
    return "", 204
