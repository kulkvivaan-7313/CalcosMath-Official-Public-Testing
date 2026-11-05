import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import accounts
from mailer import VerificationEmailError
from werkzeug.security import check_password_hash, generate_password_hash


class SignupFlowTests(unittest.TestCase):
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
        self.app_module.app.config.update(TESTING=True)

        self.sent_codes = []

        def send_email(email, code):
            self.sent_codes.append((email, code))
            return True

        self.mail_patch = patch.object(
            self.app_module,
            "send_verification_email",
            send_email,
        )
        self.mail_patch.start()
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        self.mail_patch.stop()
        self.app_path_patch.stop()
        self.accounts_path_patch.stop()
        self.temporary_directory.cleanup()

    def signup(self, username="new-user", email="new@example.com"):
        return self.client.post("/signup", json={
            "username": username,
            "email": email,
            "password": "a-secure-password",
        })

    def rows(self, query, parameters=()):
        with sqlite3.connect(self.database_path) as connection:
            return connection.execute(query, parameters).fetchall()

    def verify(self, code, email="new@example.com"):
        return self.client.post("/verify-email", json={
            "email": email,
            "code": code,
        })

    def test_signup_creates_user_only_after_code_verification(self):
        response = self.signup()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.rows("SELECT id FROM users"), [])
        pending = self.rows(
            """SELECT password_hash, verification_code_hash, delivery_confirmed
               FROM pending_registrations"""
        )[0]
        self.assertTrue(check_password_hash(pending[0], "a-secure-password"))
        self.assertNotEqual(pending[0], "a-secure-password")
        self.assertNotEqual(pending[1], self.sent_codes[0][1])
        self.assertEqual(pending[2], 1)

        verified = self.verify(self.sent_codes[0][1])

        self.assertEqual(verified.status_code, 200)
        self.assertEqual(
            self.rows("SELECT username, email, email_verified FROM users"),
            [("new-user", "new@example.com", 1)],
        )
        self.assertEqual(
            self.rows("SELECT id FROM pending_registrations"),
            [],
        )

    def test_incorrect_codes_are_limited_without_creating_a_user(self):
        self.assertEqual(self.signup().status_code, 201)
        incorrect_code = (
            "000000" if self.sent_codes[0][1] != "000000" else "000001"
        )

        for _ in range(accounts.MAX_VERIFICATION_ATTEMPTS):
            response = self.verify(incorrect_code)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Too many incorrect attempts", response.json["error"])
        locked = self.verify(self.sent_codes[0][1])
        self.assertEqual(locked.status_code, 400)
        self.assertIn("Too many incorrect attempts", locked.json["error"])
        self.assertEqual(self.rows("SELECT id FROM users"), [])
        self.assertEqual(
            self.rows("SELECT attempts FROM pending_registrations"),
            [(accounts.MAX_VERIFICATION_ATTEMPTS,)],
        )

    def test_expired_code_does_not_create_user(self):
        self.assertEqual(self.signup().status_code, 201)

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE pending_registrations SET expires_at = ?",
                ("2000-01-01T00:00:00+00:00",),
            )

        response = self.verify(self.sent_codes[0][1])

        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.json["error"])
        self.assertEqual(self.rows("SELECT id FROM users"), [])

    def test_email_delivery_failure_removes_pending_without_creating_user(self):
        def fail_delivery(email, code):
            raise VerificationEmailError("delivery failed")

        with patch.object(
            self.app_module,
            "send_verification_email",
            fail_delivery,
        ):
            response = self.signup()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("account_created", response.json)
        self.assertEqual(self.rows("SELECT id FROM users"), [])
        self.assertEqual(
            self.rows("SELECT id FROM pending_registrations"),
            [],
        )

    def test_signup_rejects_duplicate_pending_usernames_and_emails(self):
        self.assertEqual(self.signup().status_code, 201)

        for username, email in (
            ("NEW-USER", "different@example.com"),
            ("different-user", "NEW@example.com"),
        ):
            with self.subTest(username=username, email=email):
                response = self.signup(username=username, email=email)
                self.assertEqual(response.status_code, 409)

        self.assertEqual(self.rows("SELECT id FROM users"), [])
        self.assertEqual(
            self.rows("SELECT COUNT(*) FROM pending_registrations"),
            [(1,)],
        )

    def test_existing_users_are_preserved_and_block_duplicate_signup(self):
        password_hash = generate_password_hash("an-existing-password")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """INSERT INTO users
                   (username, email, password_hash, email_verified)
                   VALUES (?, ?, ?, 1)""",
                ("existing-user", "Existing@example.com", password_hash),
            )

        duplicate_username = self.signup(
            username="EXISTING-USER",
            email="another@example.com",
        )
        duplicate_email = self.signup(
            username="another-user",
            email="EXISTING@example.com",
        )

        self.assertEqual(duplicate_username.status_code, 409)
        self.assertEqual(duplicate_email.status_code, 409)
        self.assertEqual(
            self.rows(
                "SELECT username, email, password_hash, email_verified FROM users"
            ),
            [(
                "existing-user",
                "Existing@example.com",
                password_hash,
                1,
            )],
        )

    def test_resend_replaces_code_and_allows_verification(self):
        self.assertEqual(self.signup().status_code, 201)

        resent = self.client.post(
            "/resend-verification",
            json={"email": "new@example.com"},
        )

        self.assertEqual(resent.status_code, 200)
        self.assertEqual(len(self.sent_codes), 2)

        verified = self.verify(self.sent_codes[1][1])

        self.assertEqual(verified.status_code, 200)
        self.assertEqual(
            self.rows("SELECT email_verified FROM users"),
            [(1,)],
        )

    def test_only_the_delivered_code_generation_can_be_verified(self):
        with sqlite3.connect(self.database_path) as connection:
            pending_id, _, original_generation = (
                accounts.create_pending_registration(
                    connection,
                    "generation-user",
                    "generation@example.com",
                    "a-secure-password",
                )
            )
            self.assertTrue(
                accounts.confirm_pending_registration_delivery(
                    connection,
                    pending_id,
                    original_generation,
                )
            )

            pending_id, resent_code, resent_generation = (
                accounts.resend_pending_verification(
                    connection,
                    "generation@example.com",
                )
            )
            self.assertFalse(
                accounts.confirm_pending_registration_delivery(
                    connection,
                    pending_id,
                    original_generation,
                )
            )
            self.assertEqual(
                accounts.verify_pending_registration(
                    connection,
                    "generation@example.com",
                    resent_code,
                ),
                "delivery_pending",
            )
            self.assertTrue(
                accounts.confirm_pending_registration_delivery(
                    connection,
                    pending_id,
                    resent_generation,
                )
            )
            self.assertEqual(
                accounts.verify_pending_registration(
                    connection,
                    "generation@example.com",
                    resent_code,
                ),
                "verified",
            )

    def test_failed_resend_cannot_verify_or_create_user(self):
        self.assertEqual(self.signup().status_code, 201)

        def fail_delivery(email, code):
            raise VerificationEmailError("delivery failed")

        with patch.object(
            self.app_module,
            "send_verification_email",
            fail_delivery,
        ):
            response = self.client.post(
                "/resend-verification",
                json={"email": "new@example.com"},
            )

        self.assertEqual(response.status_code, 503)
        verification = self.verify(self.sent_codes[0][1])
        self.assertEqual(verification.status_code, 503)
        self.assertEqual(self.rows("SELECT id FROM users"), [])


if __name__ == "__main__":
    unittest.main()
