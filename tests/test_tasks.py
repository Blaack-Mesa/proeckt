"""Тесты TaskModule: CRUD, права, валидация, переходы состояний (API-уровень)."""
from datetime import date, timedelta

from app import events
from tests.base import ApiTestCase


class TaskCrudTests(ApiTestCase):
    """Создание, чтение, редактирование, удаление задач."""

    def setUp(self):
        super().setUp()
        self.manager, self.mh = self.make_user("manager")
        self.executor, self.eh = self.make_user("executor")
        self.project = self.make_project(self.mh)

    def test_create_task_defaults_to_new(self):
        task = self.make_task(self.mh, self.project, assignee_id=self.executor["id"])
        self.assertEqual(task["status"], "new")
        self.assertEqual(task["status_label"], "Новая")
        self.assertIn(events.TASK_CREATED, [e for e, _ in events.history()])

    def test_executor_cannot_create_task(self):
        resp = self.client.post("/api/tasks", json={"project_id": self.project, "title": "x"},
                                headers=self.eh)
        self.assertEqual(resp.status_code, 403)

    def test_create_validation(self):
        bad_bodies = [
            {"project_id": self.project, "title": ""},
            {"project_id": self.project, "title": "x" * 201},
            {"title": "Без проекта"},
            {"project_id": self.project, "title": "t", "due_date": "2020-01-01"},
            {"project_id": self.project, "title": "t", "due_date": "31.12.2030"},
            {"project_id": self.project, "title": "t", "assignee_id": 9999},
        ]
        for body in bad_bodies:
            with self.subTest(body=body):
                resp = self.client.post("/api/tasks", json=body, headers=self.mh)
                self.assertIn(resp.status_code, (400, 422))

    def test_title_boundary_200_chars_ok(self):
        task = self.make_task(self.mh, self.project, title="я" * 200)
        self.assertEqual(len(task["title"]), 200)

    def test_due_date_today_ok_yesterday_rejected(self):
        today = date.today()
        self.make_task(self.mh, self.project, due_date=today.isoformat())
        resp = self.client.post("/api/tasks", headers=self.mh, json={
            "project_id": self.project, "title": "t",
            "due_date": (today - timedelta(days=1)).isoformat()})
        self.assertEqual(resp.status_code, 400)

    def test_project_not_found(self):
        resp = self.client.post("/api/tasks", json={"project_id": 999, "title": "t"},
                                headers=self.mh)
        self.assertEqual(resp.status_code, 404)

    def test_update_task(self):
        task = self.make_task(self.mh, self.project)
        resp = self.client.patch(f"/api/tasks/{task['id']}", headers=self.mh, json={
            "title": "Новое", "assignee_id": self.executor["id"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["title"], "Новое")
        self.assertEqual(resp.get_json()["assignee_id"], self.executor["id"])

    def test_update_empty_body_and_unknown_task(self):
        task = self.make_task(self.mh, self.project)
        self.assertEqual(self.client.patch(f"/api/tasks/{task['id']}", json={"x": 1},
                                           headers=self.mh).status_code, 400)
        self.assertEqual(self.client.patch("/api/tasks/999", json={"title": "t"},
                                           headers=self.mh).status_code, 404)

    def test_delete_task(self):
        task = self.make_task(self.mh, self.project)
        self.assertEqual(self.client.delete(f"/api/tasks/{task['id']}",
                                            headers=self.mh).status_code, 204)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}",
                                         headers=self.mh).status_code, 404)

    def test_executor_sees_only_own_tasks(self):
        mine = self.make_task(self.mh, self.project, assignee_id=self.executor["id"])
        other = self.make_task(self.mh, self.project)
        listing = self.client.get("/api/tasks", headers=self.eh).get_json()
        self.assertEqual([t["id"] for t in listing], [mine["id"]])
        self.assertEqual(self.client.get(f"/api/tasks/{other['id']}",
                                         headers=self.eh).status_code, 403)

    def test_list_filter_invalid_status(self):
        resp = self.client.get("/api/tasks?status=bogus", headers=self.mh)
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_access_denied(self):
        self.assertEqual(self.client.get("/api/tasks").status_code, 401)


class TaskStatusApiTests(ApiTestCase):
    """Тесты переходов статусов через API (метод тестирования переходов состояний)."""

    def setUp(self):
        super().setUp()
        self.manager, self.mh = self.make_user("manager")
        self.executor, self.eh = self.make_user("executor")
        self.other, self.oh = self.make_user("executor")
        self.project = self.make_project(self.mh)
        self.task = self.make_task(self.mh, self.project, assignee_id=self.executor["id"])
        self.tid = self.task["id"]

    def go(self, headers, *path):
        """Последовательно выполняет переходы, проверяя успех каждого."""
        for status in path:
            resp = self.set_status(headers, self.tid, status)
            self.assertEqual(resp.status_code, 200, (status, resp.get_json()))
        return resp

    def test_happy_path_new_to_done(self):
        self.go(self.eh, "in_progress", "review")
        resp = self.go(self.mh, "done")
        self.assertEqual(resp.get_json()["status"], "done")
        statuses = [p["to"] for e, p in events.history() if e == events.TASK_STATUS_CHANGED]
        self.assertEqual(statuses, ["in_progress", "review", "done"])

    def test_t1_new_to_rejected_by_manager(self):
        self.assertEqual(self.go(self.mh, "rejected").get_json()["status"], "rejected")

    def test_t2_rejected_to_new_reopen(self):
        self.go(self.mh, "rejected", "new")

    def test_t3_review_back_to_in_progress(self):
        self.go(self.eh, "in_progress", "review")
        self.go(self.mh, "in_progress")

    def test_t4_review_to_rejected(self):
        self.go(self.eh, "in_progress", "review")
        self.go(self.mh, "rejected")

    def test_forbidden_done_to_new(self):
        self.go(self.eh, "in_progress", "review")
        self.go(self.mh, "done")
        for target in ("new", "in_progress", "review", "rejected"):
            with self.subTest(target=target):
                resp = self.set_status(self.mh, self.tid, target)
                self.assertEqual(resp.status_code, 409)

    def test_forbidden_skip_new_to_done_and_review(self):
        for target in ("done", "review"):
            self.assertEqual(self.set_status(self.mh, self.tid, target).status_code, 409)

    def test_forbidden_same_status(self):
        self.assertEqual(self.set_status(self.mh, self.tid, "new").status_code, 409)

    def test_unknown_status_value(self):
        self.assertEqual(self.set_status(self.mh, self.tid, "archived").status_code, 400)
        resp = self.client.post(f"/api/tasks/{self.tid}/status", json={}, headers=self.mh)
        self.assertEqual(resp.status_code, 400)

    def test_executor_cannot_approve_own_work(self):
        self.go(self.eh, "in_progress", "review")
        self.assertEqual(self.set_status(self.eh, self.tid, "done").status_code, 403)

    def test_foreign_executor_cannot_change_status(self):
        self.assertEqual(self.set_status(self.oh, self.tid, "in_progress").status_code, 403)

    def test_start_without_assignee_rejected(self):
        free = self.make_task(self.mh, self.project)
        resp = self.set_status(self.mh, free["id"], "in_progress")
        self.assertEqual(resp.get_json()["error"]["code"], "assignee_required")

    def test_failed_transition_does_not_change_status(self):
        self.set_status(self.mh, self.tid, "done")
        status = self.client.get(f"/api/tasks/{self.tid}", headers=self.mh).get_json()["status"]
        self.assertEqual(status, "new")

    def test_done_task_cannot_be_edited_or_deleted(self):
        self.go(self.eh, "in_progress", "review")
        self.go(self.mh, "done")
        self.assertEqual(self.client.patch(f"/api/tasks/{self.tid}", json={"title": "x"},
                                           headers=self.mh).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/tasks/{self.tid}",
                                            headers=self.mh).status_code, 409)

    def test_transitions_endpoint_matches_model(self):
        matrix = self.client.get("/api/tasks/transitions", headers=self.mh).get_json()
        self.assertTrue(matrix["new"]["in_progress"])
        self.assertFalse(matrix["done"]["new"])
