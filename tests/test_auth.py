"""Тесты AuthModule: регистрация, вход, восстановление пароля, роли."""
from datetime import datetime, timedelta, timezone

import jwt

from app import events
from tests.base import ApiTestCase


class AuthTests(ApiTestCase):
    """Модульные и API-тесты авторизации."""

    def register(self, **over):
        body = {"email": "ivanov@example.com", "full_name": "Иванов И.И.",
                "password": "Passw0rd1"}
        body.update(over)
        return self.client.post("/api/auth/register", json=body)

    def test_register_ok_default_role_executor(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data["role"], "executor")
        self.assertNotIn("password_hash", data)
        self.assertIn(events.USER_REGISTERED, [e for e, _ in events.history()])

    def test_register_cannot_choose_role(self):
        resp = self.register(role="admin")
        self.assertEqual(resp.get_json()["role"], "executor")

    def test_register_duplicate_email(self):
        self.register()
        resp = self.register(email="IVANOV@example.com")
        self.assertEqual(resp.status_code, 409)

    def test_register_invalid_email(self):
        self.assertEqual(self.register(email="not-an-email").status_code, 400)

    def test_register_weak_passwords(self):
        for password in ("short1", "onlyletters", "12345678", None):
            with self.subTest(password=password):
                self.assertEqual(self.register(password=password).status_code, 400)

    def test_register_empty_name(self):
        self.assertEqual(self.register(full_name="  ").status_code, 400)

    def test_register_non_json_body(self):
        resp = self.client.post("/api/auth/register", data="x")
        self.assertEqual(resp.status_code, 400)

    def test_login_ok_returns_valid_jwt(self):
        self.register()
        resp = self.client.post("/api/auth/login", json={"email": "ivanov@example.com",
                                                          "password": "Passw0rd1"})
        self.assertEqual(resp.status_code, 200)
        token = resp.get_json()["access_token"]
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        self.assertEqual(payload["role"], "executor")
        self.assertEqual(payload["purpose"], "access")

    def test_login_wrong_password_and_unknown_user_same_error(self):
        self.register()
        bad = self.client.post("/api/auth/login", json={"email": "ivanov@example.com",
                                                         "password": "wrong"})
        unknown = self.client.post("/api/auth/login", json={"email": "no@example.com",
                                                             "password": "Passw0rd1"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.get_json(), unknown.get_json())

    def test_me_requires_token(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_me_with_token(self):
        user, headers = self.make_user("manager")
        resp = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(resp.get_json()["id"], user["id"])

    def test_garbage_and_expired_token_rejected(self):
        self.assertEqual(self.client.get("/api/auth/me", headers={
            "Authorization": "Bearer garbage"}).status_code, 401)
        expired = jwt.encode({"sub": "1", "purpose": "access",
                              "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                             "test-secret", algorithm="HS256")
        resp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
        self.assertEqual(resp.get_json()["error"]["code"], "token_expired")

    def test_reset_token_cannot_be_used_as_access_token(self):
        self.register()
        reset = self.client.post("/api/auth/password-reset/request",
                                 json={"email": "ivanov@example.com"}).get_json()["reset_token"]
        resp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {reset}"})
        self.assertEqual(resp.status_code, 401)

    def test_password_reset_flow_and_single_use(self):
        self.register()
        token = self.client.post("/api/auth/password-reset/request",
                                 json={"email": "ivanov@example.com"}).get_json()["reset_token"]
        ok = self.client.post("/api/auth/password-reset/confirm",
                              json={"token": token, "new_password": "NewPassw0rd2"})
        self.assertEqual(ok.status_code, 200)
        login = self.client.post("/api/auth/login", json={"email": "ivanov@example.com",
                                                           "password": "NewPassw0rd2"})
        self.assertEqual(login.status_code, 200)
        # токен одноразовый: повторное использование отклоняется
        again = self.client.post("/api/auth/password-reset/confirm",
                                 json={"token": token, "new_password": "Another3Pass"})
        self.assertEqual(again.status_code, 401)

    def test_password_reset_unknown_email_gives_same_response(self):
        self.register()
        known = self.client.post("/api/auth/password-reset/request",
                                 json={"email": "ivanov@example.com"})
        unknown = self.client.post("/api/auth/password-reset/request",
                                   json={"email": "ghost@example.com"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.get_json()["message"], unknown.get_json()["message"])
        self.assertNotIn("reset_token", unknown.get_json())

    def test_password_reset_weak_new_password(self):
        self.register()
        token = self.client.post("/api/auth/password-reset/request",
                                 json={"email": "ivanov@example.com"}).get_json()["reset_token"]
        resp = self.client.post("/api/auth/password-reset/confirm",
                                json={"token": token, "new_password": "weak"})
        self.assertEqual(resp.status_code, 400)

    def test_roles_admin_only_endpoints(self):
        _, manager = self.make_user("manager")
        _, admin = self.make_user("admin")
        self.assertEqual(self.client.get("/api/auth/users", headers=manager).status_code, 403)
        self.assertEqual(self.client.get("/api/auth/users", headers=admin).status_code, 200)

    def test_admin_changes_role_effective_immediately(self):
        executor, exec_headers = self.make_user("executor")
        _, admin = self.make_user("admin")
        self.assertEqual(self.client.post("/api/projects", json={"name": "P"},
                                          headers=exec_headers).status_code, 403)
        resp = self.client.patch(f"/api/auth/users/{executor['id']}/role",
                                 json={"role": "manager"}, headers=admin)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.post("/api/projects", json={"name": "P"},
                                          headers=exec_headers).status_code, 201)

    def test_change_role_invalid(self):
        executor, _ = self.make_user("executor")
        _, admin = self.make_user("admin")
        resp = self.client.patch(f"/api/auth/users/{executor['id']}/role",
                                 json={"role": "boss"}, headers=admin)
        self.assertEqual(resp.status_code, 400)
        missing = self.client.patch("/api/auth/users/999/role", json={"role": "manager"},
                                    headers=admin)
        self.assertEqual(missing.status_code, 404)
