import importlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import accounts
from werkzeug.security import generate_password_hash


class LoginFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "accounts.db"
        self.accounts_path_patch = patch.object(
            accounts,
            "DATABASE_PATH",
            self.database_path,
        )
        self.accounts_path_patch.start()
        accounts.initialize_database()

        self.app_module = importlib.import_module("app")
        self.app_path_patch = patch.object(
            self.app_module,
            "DATABASE_PATH",
            self.database_path,
        )
        self.app_path_patch.start()
        self.config_patch = patch.dict(
            self.app_module.app.config,
            {
                "SECRET_KEY": "test-only-session-secret",
                "SESSION_COOKIE_SECURE": False,
                "TESTING": True,
            },
        )
        self.config_patch.start()
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        self.config_patch.stop()
        self.app_path_patch.stop()
        self.accounts_path_patch.stop()
        self.temporary_directory.cleanup()

    def create_user(self, email, password, verified):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """INSERT INTO users
                   (username, email, password_hash, email_verified)
                   VALUES (?, ?, ?, ?)""",
                (
                    "login-user",
                    email,
                    generate_password_hash(password),
                    int(verified),
                ),
            )
            connection.commit()

    def login(self, email="user@example.com", password="correct-password"):
        return self.client.post("/login", json={
            "email": email,
            "password": password,
        })

    def test_login_page_is_rendered(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="loginForm"', response.data)
        self.assertIn(b"static/script.js", response.data)

    def test_verified_user_can_login_and_receive_session(self):
        self.create_user("user@example.com", "correct-password", True)

        response = self.login(email="USER@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["message"], "Login successful")
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        with self.client.session_transaction() as user_session:
            self.assertTrue(user_session.permanent)
            self.assertEqual(user_session["user_id"], 1)

    def test_wrong_password_does_not_create_session(self):
        self.create_user("user@example.com", "correct-password", True)

        response = self.login(password="incorrect-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "Invalid email or password")
        with self.client.session_transaction() as user_session:
            self.assertNotIn("user_id", user_session)

    def test_unverified_user_is_rejected_with_generic_error(self):
        self.create_user("user@example.com", "correct-password", False)

        response = self.login()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "Invalid email or password")
        with self.client.session_transaction() as user_session:
            self.assertNotIn("user_id", user_session)

    def test_missing_session_secret_disables_login(self):
        self.create_user("user@example.com", "correct-password", True)
        self.app_module.app.config["SECRET_KEY"] = None

        response = self.login()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json["error"],
            "Login is temporarily unavailable.",
        )

    def test_missing_credentials_are_rejected(self):
        response = self.client.post("/login", json={"email": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json["error"],
            "Email and password are required",
        )

    def test_login_requires_json_credentials(self):
        response = self.client.post(
            "/login",
            data={
                "email": "user@example.com",
                "password": "correct-password",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "Invalid request")


if __name__ == "__main__":
    unittest.main()
