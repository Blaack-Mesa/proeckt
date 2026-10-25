"""AuthModule: REST-эндпоинты /api/auth/*."""
from flask import Blueprint, current_app, g, jsonify

from ..security import auth_required
from ..utils import json_body
from . import service

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    """POST /api/auth/register — самостоятельная регистрация (роль executor)."""
    data = json_body()
    user = service.register_user(data.get("email"), data.get("full_name"),
                                 data.get("password"))
    return jsonify(user), 201


@bp.post("/login")
def login():
    """POST /api/auth/login — выдаёт JWT."""
    data = json_body()
    token, user = service.authenticate(data.get("email"), data.get("password"))
    return jsonify({"access_token": token, "token_type": "Bearer", "user": user})


@bp.post("/password-reset/request")
def password_reset_request():
    """POST /api/auth/password-reset/request — запрос на восстановление пароля."""
    token = service.request_password_reset(json_body().get("email"))
    body = {"message": "Если адрес зарегистрирован, инструкция отправлена"}
    if token and current_app.config["EXPOSE_RESET_TOKEN"]:
        body["reset_token"] = token          # только для разработки и тестов
    return jsonify(body)


@bp.post("/password-reset/confirm")
def password_reset_confirm():
    """POST /api/auth/password-reset/confirm — установка нового пароля."""
    data = json_body()
    service.reset_password(data.get("token"), data.get("new_password"))
    return jsonify({"message": "Пароль изменён"})


@bp.get("/me")
@auth_required()
def me():
    """GET /api/auth/me — профиль текущего пользователя."""
    return jsonify(service.get_user(g.current_user["id"]))


@bp.get("/users")
@auth_required("admin")
def users():
    """GET /api/auth/users — список пользователей (admin)."""
    return jsonify(service.list_users())


@bp.patch("/users/<int:user_id>/role")
@auth_required("admin")
def set_role(user_id):
    """PATCH /api/auth/users/<id>/role — назначение роли (admin)."""
    return jsonify(service.change_role(user_id, json_body().get("role")))
