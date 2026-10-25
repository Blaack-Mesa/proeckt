"""Интеграционные тесты: сквозные сценарии через все три модуля."""
from app import events
from tests.base import ApiTestCase


class IntegrationTests(ApiTestCase):
    """Auth → Task → Report на единой БД и едином JWT."""

    def test_create_task_appears_in_report(self):
        """Сценарий из задания: пользователь создаёт задачу → она в отчёте."""
        _, admin = self.make_user("admin")
        manager, mh = self.make_user("manager")
        executor, eh = self.make_user("executor")
        project = self.make_project(mh, "ИС «Документооборот»")
        task = self.make_task(mh, project, title="Подготовить ТЗ",
                              assignee_id=executor["id"])

        by_project = self.client.get(f"/api/reports/project?project_id={project}",
                                     headers=mh).get_json()
        self.assertIn(task["id"], [r["id"] for r in by_project["rows"]])
        by_user = self.client.get("/api/reports/assignee", headers=eh).get_json()
        self.assertEqual(by_user["rows"][0]["title"], "Подготовить ТЗ")
        self.assertEqual(self.client.get("/api/auth/users", headers=admin).status_code, 200)

    def test_status_change_reflected_in_report(self):
        manager, mh = self.make_user("manager")
        executor, eh = self.make_user("executor")
        project = self.make_project(mh)
        task = self.make_task(mh, project, assignee_id=executor["id"])
        self.set_status(eh, task["id"], "in_progress")
        self.set_status(eh, task["id"], "review")
        self.set_status(mh, task["id"], "done")
        data = self.client.get(f"/api/reports/project?project_id={project}",
                               headers=mh).get_json()
        self.assertEqual(data["summary"]["by_status"]["done"], 1)
        self.assertEqual(data["rows"][0]["status_label"], "Завершена")

    def test_deleted_task_disappears_from_report(self):
        _, mh = self.make_user("manager")
        project = self.make_project(mh)
        task = self.make_task(mh, project)
        self.client.delete(f"/api/tasks/{task['id']}", headers=mh)
        data = self.client.get(f"/api/reports/project?project_id={project}",
                               headers=mh).get_json()
        self.assertEqual(data["summary"]["total"], 0)

    def test_single_jwt_works_across_all_modules(self):
        _, mh = self.make_user("manager")
        project = self.make_project(mh)
        for url in ("/api/auth/me", "/api/tasks", "/api/projects",
                    f"/api/reports/project?project_id={project}"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, headers=mh).status_code, 200)
                self.assertEqual(self.client.get(url).status_code, 401)

    def test_blocked_user_token_stops_working_everywhere(self):
        user, headers = self.make_user("manager")
        with self.app.app_context():
            from app.db import get_db
            get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (user["id"],))
            get_db().commit()
        self.assertEqual(self.client.get("/api/tasks", headers=headers).status_code, 401)

    def test_event_chain_for_full_scenario(self):
        _, mh = self.make_user("manager")
        project = self.make_project(mh)
        self.make_task(mh, project)
        self.client.get(f"/api/reports/project?project_id={project}", headers=mh)
        names = [e for e, _ in events.history()]
        self.assertIn(events.TASK_CREATED, names)
        self.assertLess(names.index(events.TASK_CREATED), names.index(events.REPORT_GENERATED))

    def test_event_subscriber_receives_payload(self):
        received = []
        events.subscribe(events.TASK_CREATED, received.append)
        _, mh = self.make_user("manager")
        project = self.make_project(mh)
        task = self.make_task(mh, project)
        self.assertEqual(received[0]["task_id"], task["id"])

    def test_database_has_required_tables(self):
        with self.app.app_context():
            from app.db import get_db
            rows = get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")
            names = {r["name"] for r in rows}
        self.assertTrue({"users", "projects", "tasks", "reports"} <= names)

    def test_error_format_is_uniform(self):
        resp = self.client.get("/api/nothing")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("code", resp.get_json()["error"])
