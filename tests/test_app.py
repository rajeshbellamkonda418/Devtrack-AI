import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ["DB_BACKEND"] = "sqlite"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from app import app, initialize_mysql_auth_schema


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        os.environ["SQLITE_PATH"] = str(Path(self.database_dir.name) / "test.sqlite3")
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()

    def tearDown(self):
        self.database_dir.cleanup()

    def test_mysql_initialization_creates_applications_before_migrating_it(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        connection = Mock()
        connection.cursor.return_value = cursor

        import app as app_module

        initialized = app_module._mysql_auth_schema_initialized
        app_module._mysql_auth_schema_initialized = False
        try:
            initialize_mysql_auth_schema(connection)
        finally:
            app_module._mysql_auth_schema_initialized = initialized

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        create_applications = next(
            index
            for index, statement in enumerate(statements)
            if "CREATE TABLE IF NOT EXISTS applications" in statement
        )
        migrate_applications = statements.index(
            "SHOW COLUMNS FROM applications LIKE 'user_id'"
        )
        self.assertLess(create_applications, migrate_applications)
        connection.commit.assert_called_once()

    def test_landing_page_has_inline_account_access(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="auth-form"', response.data)
        self.assertNotIn(b"Sign in | DevTrack AI", response.data)
        self.assertNotIn(b'id="jobs-list"', response.data)
        self.assertIn(b"favicon.svg", response.data)

        favicon = self.client.get("/static/favicon.svg")
        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon.mimetype, "image/svg+xml")
        favicon.close()

        for asset in (
            "css/style.css",
            "css/dashboard.css",
            "js/auth.js",
            "js/script.js",
            "js/dashboard.js",
        ):
            with self.subTest(asset=asset):
                response = self.client.get(f"/static/{asset}")
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_login_route_redirects_to_landing_page(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/#account-access")

    def test_account_can_access_dashboard_and_manage_applications(self):
        response = self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)

        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        response = self.client.post(
            "/api/jobs",
            json={
                "company": "Example Co",
                "role": "Engineer",
                "status": "Applied",
                "skills": "Python",
            },
        )
        self.assertEqual(response.status_code, 201)

        jobs = self.client.get("/api/jobs").get_json()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example Co")

    def test_login_uses_sqlite_when_database_backend_is_not_configured(self):
        configured_backend = os.environ.pop("DB_BACKEND", None)
        try:
            response = self.client.post(
                "/api/auth/register",
                json={"name": "Default DB User", "password": "password123"},
            )
            self.assertEqual(response.status_code, 201)
        finally:
            if configured_backend is not None:
                os.environ["DB_BACKEND"] = configured_backend

    def test_login_rejects_invalid_credentials_and_accepts_valid_credentials(self):
        response = self.client.post(
            "/api/auth/login",
            json={"name": "Unknown User", "password": "password123"},
        )
        self.assertEqual(response.status_code, 401)

        self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        self.client.post("/logout")

        response = self.client.post(
            "/api/auth/login",
            json={"name": "Test User", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

        response = self.client.post(
            "/api/auth/login",
            json={"name": "  test user  ", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["redirect"], "/dashboard")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_registration_rejects_invalid_and_duplicate_accounts(self):
        for payload in (
            {},
            {"name": "A", "password": "password123"},
            {"name": "Test User", "password": "short"},
            {"name": "   ", "password": "password123"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/register", json=payload)
                self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)
        self.client.post("/logout")

        response = self.client.post(
            "/api/auth/register",
            json={"name": "test user", "password": "password456"},
        )
        self.assertEqual(response.status_code, 409)

    def test_logout_clears_session(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )

        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/#account-access")
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/api/jobs").status_code, 401)

    def test_application_data_is_isolated_between_users(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "First User", "password": "password123"},
        )
        response = self.client.post(
            "/api/jobs",
            json={"company": "Private Co", "role": "Engineer"},
        )
        self.assertEqual(response.status_code, 201)
        self.client.post("/logout")

        self.client.post(
            "/api/auth/register",
            json={"name": "Second User", "password": "password123"},
        )
        self.assertEqual(self.client.get("/api/jobs").get_json(), [])

    def test_protected_routes_stay_protected(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/#account-access")
        response = self.client.get("/api/jobs")
        self.assertEqual(response.status_code, 401)

    def test_malformed_api_fields_return_validation_errors(self):
        response = self.client.post("/api/auth/login", json=["not", "an", "object"])
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/auth/register",
            json={"name": ["not", "text"], "password": "password123"},
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/api/recommend", json={"skills": 42})
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/analyze-resume",
            json={"role": 42, "resume_text": "Resume"},
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/search-jobs",
            json={"role": ["Engineer"]},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
