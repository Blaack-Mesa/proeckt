"""ProjectFlow — фабрика приложения: подключает модули Auth, Task, Report."""
import click
from flask import Flask, jsonify

from . import db
from .auth import routes as auth_routes
from .auth import service as auth_service
from .config import Config
from .errors import ApiError
from .reports import routes as report_routes
from .tasks import routes as task_routes


def create_app(config: dict = None) -> Flask:
    """Создаёт и настраивает приложение; config переопределяет Config."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()

    # Маршрутизация между модулями: каждый модуль — отдельный Blueprint.
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(task_routes.bp)
    app.register_blueprint(report_routes.bp)

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": {"code": "not_found", "message": "Ресурс не найден"}}), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({"error": {"code": "method_not_allowed",
                                  "message": "Метод не поддерживается"}}), 405

    @app.get("/api/health")
    def health():
        """Проверка работоспособности."""
        return jsonify({"status": "ok"})

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("full_name")
    @click.password_option()
    def create_admin(email, full_name, password):
        """Создаёт администратора: flask --app app create-admin EMAIL "ФИО"."""
        user = auth_service.register_user(email, full_name, password, role="admin")
        click.echo(f"Администратор создан: id={user['id']}")

    return app
