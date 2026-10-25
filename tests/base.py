"""Общая основа тестов: временная БД, клиент Flask, вспомогательные функции."""
import os
import tempfile
import unittest

from app import create_app, events
from app.auth import service as auth_service


class ApiTestCase(unittest.TestCase):
    """Базовый класс: для каждого теста — чистая БД и чистый журнал событий."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path,
                               "SECRET_KEY": "test-secret", "EXPOSE_RESET_TOKEN": True})
        self.client = self.app.test_client()
        events.clear()

    def tearDown(self):
        os.remove(self.db_path)

    def make_user(self, role="executor", email=None, password="Passw0rd1"):
        """Создаёт пользователя напрямую через сервис; возвращает (user, headers)."""
        email = email or f"{role}{len(events.history())}{os.urandom(2).hex()}@example.com"
        with self.app.app_context():
            user = auth_service.register_user(email, f"Тест {role}", password, role=role)
        resp = self.client.post("/api/auth/login", json={"email": email, "password": password})
        return user, {"Authorization": "Bearer " + resp.get_json()["access_token"]}

    def make_project(self, headers, name="Проект"):
        """Создаёт проект, возвращает его id."""
        resp = self.client.post("/api/projects", json={"name": name}, headers=headers)
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["id"]

    def make_task(self, headers, project_id, **fields):
        """Создаёт задачу, возвращает JSON задачи."""
        body = {"project_id": project_id, "title": "Задача"}
        body.update(fields)
        resp = self.client.post("/api/tasks", json=body, headers=headers)
        self.assertEqual(resp.status_code, 201, resp.get_json())
        return resp.get_json()

    def set_status(self, headers, task_id, status):
        """Запрос смены статуса; возвращает response."""
        return self.client.post(f"/api/tasks/{task_id}/status", json={"status": status},
                                headers=headers)
