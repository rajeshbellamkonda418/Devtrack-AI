import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mongomock
from bson import ObjectId
from pymongo.errors import ConfigurationError, PyMongoError

os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["MONGODB_DB_NAME"] = "devtrack_test"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from app import app, get_db
from migrate_to_mongodb import migrate_rows, read_sql_rows
from ml.dsa_questions import DSA_LEVELS, DSA_TOPICS
from ml.interview_questions import INTERVIEW_QUESTIONS, LEVELS
from ml.model import JOB_PROFILES
from ml.resume_analyzer import extract_text_from_file


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        import app as app_module

        self.mongo = mongomock.MongoClient()
        self.mongo_factory = patch("app.MongoClient", return_value=self.mongo)
        self.mongo_factory.start()
        app_module._mongo_client = None
        app_module._mongo_database = None
        app_module._mongo_settings = None
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()

    def tearDown(self):
        import app as app_module

        self.mongo_factory.stop()
        self.mongo.close()
        app_module._mongo_client = None
        app_module._mongo_database = None
        app_module._mongo_settings = None
        self.database_dir.cleanup()

    def test_sqlite_migration_preserves_records_and_can_be_repeated(self):
        database_path = Path(self.database_dir.name) / "legacy.sqlite3"
        source = sqlite3.connect(database_path)
        source.row_factory = sqlite3.Row
        source.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP
            );
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                skills TEXT,
                applied_date TIMESTAMP
            );
            INSERT INTO users VALUES (7, 'Legacy User', 'hashed-password', '2024-01-02 03:04:05');
            INSERT INTO applications VALUES
                (11, 7, 'Example Co', 'Engineer', 'Interview', 'Python', '2024-02-03 04:05:06');
        """)
        users, applications = read_sql_rows(source, "sqlite")
        source.close()

        database = self.mongo["migration_test"]
        counts = migrate_rows(database, users, applications, "sqlite:test")
        migrate_rows(database, users, applications, "sqlite:test")

        self.assertEqual(counts, (1, 1))
        migrated_user = database.users.find_one({"name": "Legacy User"})
        migrated_application = database.applications.find_one({"company": "Example Co"})
        self.assertEqual(migrated_user["password_hash"], "hashed-password")
        self.assertEqual(migrated_application["user_id"], str(migrated_user["_id"]))
        self.assertEqual(migrated_application["status"], "Interview")
        self.assertEqual(database.users.count_documents({}), 1)
        self.assertEqual(database.applications.count_documents({}), 1)

    def test_sqlite_migration_is_safe_to_rerun_with_different_source_tags(self):
        database_path = Path(self.database_dir.name) / "legacy_repeated.sqlite3"
        source = sqlite3.connect(database_path)
        source.row_factory = sqlite3.Row
        source.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP
            );
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                skills TEXT,
                applied_date TIMESTAMP
            );
            INSERT INTO users VALUES (12, 'Repeat User', 'hashed-password', '2024-01-02 03:04:05');
            INSERT INTO applications VALUES
                (13, 12, 'Repeat Co', 'Engineer', 'Applied', 'Python', '2024-02-03 04:05:06');
        """)
        users, applications = read_sql_rows(source, "sqlite")
        source.close()

        database = self.mongo["rerun_migration_test"]
        migrate_rows(database, users, applications, "sqlite:legacy_a")
        counts = migrate_rows(database, users, applications, "sqlite:legacy_b")

        self.assertEqual(counts, (1, 1))
        self.assertEqual(database.users.count_documents({}), 1)
        self.assertEqual(database.applications.count_documents({}), 1)
        self.assertEqual(database.users.find_one({"name": "Repeat User"})["name_key"], "repeat user")

    def test_landing_page_has_inline_account_access(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'id="auth-form"', response.data)
        self.assertNotIn(b"Sign in | DevTrack AI", response.data)
        self.assertIn(b"Open Dashboard", response.data)
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
        self.assertEqual(response.headers["Location"], "/")

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

    def test_application_can_be_updated_and_deleted(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        response = self.client.post(
            "/api/jobs",
            json={"company": "Example Co", "role": "Engineer"},
        )
        self.assertEqual(response.status_code, 201)
        job_id = response.get_json()["id"]

        response = self.client.put(f"/api/jobs/{job_id}", json={"status": "Interview"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").get_json()[0]["status"], "Interview")

        response = self.client.delete(f"/api/jobs/{job_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").get_json(), [])
        self.assertEqual(self.client.delete(f"/api/jobs/{job_id}").status_code, 404)

    def test_application_changes_are_scoped_to_the_signed_in_user(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "First User", "password": "password123"},
        )
        job_id = self.client.post(
            "/api/jobs",
            json={"company": "Private Co", "role": "Engineer"},
        ).get_json()["id"]
        self.client.post("/logout")

        self.client.post(
            "/api/auth/register",
            json={"name": "Second User", "password": "password123"},
        )
        self.assertEqual(
            self.client.put(
                f"/api/jobs/{job_id}", json={"status": "Rejected"}
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"/api/jobs/{job_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs").get_json(), [])

    def test_application_validation_rejects_malformed_and_invalid_fields(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        for payload in (
            [],
            {"company": "Example Co"},
            {"company": "Example Co", "role": ["Engineer"]},
            {"company": "Example Co", "role": "Engineer", "status": "Unknown"},
            {"company": "x" * 121, "role": "Engineer"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/jobs", json=payload).status_code, 400
                )

        for payload in ([], {"status": 1}, {"status": "Unknown"}):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.put("/api/jobs/1", json=payload).status_code, 400
                )

    def test_database_errors_do_not_leak_backend_details(self):
        self.client.post(
            "/api/auth/register",
            json={"name": "Test User", "password": "password123"},
        )
        with self.assertLogs("root", level="ERROR"):
            with patch(
                "app.get_db",
                side_effect=PyMongoError("private database details"),
            ):
                job_id = str(ObjectId())
                for method, path, kwargs in (
                    ("get", "/api/jobs", {}),
                    ("post", "/api/jobs", {"json": {"company": "Co", "role": "Role"}}),
                    ("put", f"/api/jobs/{job_id}", {"json": {"status": "Applied"}}),
                    ("delete", f"/api/jobs/{job_id}", {}),
                ):
                    with self.subTest(method=method):
                        response = getattr(self.client, method)(path, **kwargs)
                        self.assertEqual(response.status_code, 500)
                        self.assertNotIn(b"private database details", response.data)

    def test_mongodb_connection_uses_configured_uri_and_database(self):
        import app as app_module

        client = mongomock.MongoClient()
        with (
            patch.dict(
                os.environ,
                {
                    "MONGODB_URI": "mongodb://db.example.test:27017",
                    "MONGODB_DB_NAME": "devtrack",
                },
            ),
            patch("app.MongoClient", return_value=client) as connect,
        ):
            app_module._mongo_client = None
            app_module._mongo_database = None
            app_module._mongo_settings = None
            database = get_db()

        self.assertIs(database, client["devtrack"])
        connect.assert_called_once_with(
            "mongodb://db.example.test:27017",
            serverSelectionTimeoutMS=5000,
        )
        self.assertIn("name_key_1", database.users.index_information())
        self.assertIn("user_id_1__id_-1", database.applications.index_information())
        client.close()

    def test_mongodb_connection_requires_a_uri(self):
        with patch.dict(os.environ, {"MONGODB_URI": ""}):
            with self.assertRaisesRegex(ConfigurationError, "MONGODB_URI"):
                get_db()

    def test_oversized_request_returns_json_413(self):
        original_limit = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 128
        try:
            response = self.client.post(
                "/api/analyze-resume",
                data="x" * 256,
                content_type="application/json",
            )
        finally:
            app.config["MAX_CONTENT_LENGTH"] = original_limit

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.get_json(),
            {"error": "Request body must be 10 MB or smaller"},
        )

    def test_unsupported_legacy_resume_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported file format"):
            extract_text_from_file(io.BytesIO(b"legacy document"), "resume.doc")

    def test_pdf_resume_page_limit_allows_two_pages_and_rejects_three(self):
        import pypdf

        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        two_page_pdf = io.BytesIO()
        writer.write(two_page_pdf)
        two_page_pdf.seek(0)
        self.assertEqual(
            extract_text_from_file(two_page_pdf, "resume.pdf"),
            "",
        )

        writer.add_blank_page(width=612, height=792)
        three_page_pdf = io.BytesIO()
        writer.write(three_page_pdf)
        three_page_pdf.seek(0)
        with self.assertRaisesRegex(ValueError, "no more than 2 pages"):
            extract_text_from_file(three_page_pdf, "resume.pdf")

    def test_docx_and_text_resume_page_limits_use_breaks_and_word_estimate(self):
        import docx
        from docx.enum.text import WD_BREAK

        document = docx.Document()
        paragraph = document.add_paragraph("Python engineer")
        paragraph.add_run().add_break(WD_BREAK.PAGE)
        paragraph.add_run().add_break(WD_BREAK.PAGE)
        docx_content = io.BytesIO()
        document.save(docx_content)
        docx_content.seek(0)
        with self.assertRaisesRegex(ValueError, "no more than 2 pages"):
            extract_text_from_file(docx_content, "resume.docx")

        long_document = docx.Document()
        long_document.add_paragraph("word " * 1001)
        long_docx_content = io.BytesIO()
        long_document.save(long_docx_content)
        long_docx_content.seek(0)
        with self.assertRaisesRegex(ValueError, "estimated at 3 pages"):
            extract_text_from_file(long_docx_content, "resume.docx")

        text_two_pages = io.BytesIO(("word " * 1000).encode("utf-8"))
        self.assertEqual(
            len(extract_text_from_file(text_two_pages, "resume.txt").split()),
            1000,
        )

        text_over_two_pages = io.BytesIO(("word " * 1001).encode("utf-8"))
        with self.assertRaisesRegex(ValueError, "no more than 2 pages"):
            extract_text_from_file(text_over_two_pages, "resume.txt")

    def test_resume_api_rejects_pdf_over_two_pages(self):
        import pypdf

        writer = pypdf.PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        pdf_content = io.BytesIO()
        writer.write(pdf_content)
        pdf_content.seek(0)

        response = self.client.post(
            "/api/analyze-resume",
            data={
                "role": "Python Full-Stack Developer",
                "resume": (pdf_content, "resume.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no more than 2 pages", response.get_json()["error"])

    def test_job_search_rejects_unknown_platform(self):
        response = self.client.get(
            "/api/search-jobs?role=Engineer&platform=unknown"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid job platform")

    def test_job_search_accepts_get_and_post_parameters(self):
        results = {"query": "Python Engineer", "jobs": [], "platform_links": []}
        with patch("app.search_role_jobs", return_value=results) as search:
            response = self.client.get(
                "/api/search-jobs?role=Python+Engineer&location=Toronto"
                "&platform=jobicy&employment_type=internship"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), results)
            search.assert_called_once_with(
                role="Python Engineer",
                location="Toronto",
                platform="jobicy",
                employment_type="internship",
            )

            search.reset_mock()
            response = self.client.post(
                "/api/search-jobs",
                json={
                    "role": "Data Engineer",
                    "location": "Remote",
                    "platform": "arbeitnow",
                    "employment_type": "fresher",
                },
            )
            self.assertEqual(response.status_code, 200)
            search.assert_called_once_with(
                role="Data Engineer",
                location="Remote",
                platform="arbeitnow",
                employment_type="fresher",
            )

    def test_job_search_handles_provider_errors_without_exposing_details(self):
        with self.assertLogs("root", level="ERROR"):
            with patch(
                "app.search_role_jobs",
                side_effect=RuntimeError("private provider details"),
            ):
                response = self.client.get("/api/search-jobs?role=Engineer")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"private provider details", response.data)

    def test_recommendations_return_ranked_matches_for_known_skills(self):
        response = self.client.post(
            "/api/recommend", json={"skills": "Python Flask SQL"}
        )
        self.assertEqual(response.status_code, 200)
        recommendations = response.get_json()["recommendations"]
        self.assertTrue(recommendations)
        self.assertLessEqual(len(recommendations), 5)
        self.assertTrue(
            all(item["title"] in {job["title"] for job in JOB_PROFILES}
                for item in recommendations)
        )
        self.assertTrue(all(0 < item["match"] <= 100 for item in recommendations))

        response = self.client.post(
            "/api/recommend", json={"skills": "unlisted-technology"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["recommendations"], [])

    def test_resume_analysis_accepts_text_and_rejects_short_content(self):
        resume_text = (
            "Experience\nPython Flask SQL developer. Built projects for 12 users "
            "and improved delivery by 20%. Education\nSkills\n"
        )
        response = self.client.post(
            "/api/analyze-resume",
            json={"role": "Python Full-Stack Developer", "resume_text": resume_text},
        )
        self.assertEqual(response.status_code, 200)
        analysis = response.get_json()
        self.assertEqual(analysis["target_role"], "Python Full-Stack Developer")
        self.assertGreaterEqual(analysis["match_score"], 10)
        self.assertLessEqual(analysis["match_score"], 100)
        self.assertIn("ats_checks", analysis)

        response = self.client.post(
            "/api/analyze-resume",
            json={"role": "Developer", "resume_text": "Too short"},
        )
        self.assertEqual(response.status_code, 400)

    def test_resume_analysis_recommends_roles_based_on_skill_matches(self):
        resume_text = (
            "Experience\nPython backend engineer with Flask, Django, SQL, PostgreSQL, "
            "Docker, REST APIs, Git, Linux, and cloud deployment experience.\n"
            "Projects\nBuilt data pipelines and analytics dashboards using pandas and NumPy."
        )
        response = self.client.post(
            "/api/analyze-resume",
            json={"role": "Python Full-Stack Developer", "resume_text": resume_text},
        )
        self.assertEqual(response.status_code, 200)
        analysis = response.get_json()
        self.assertTrue(analysis["recommended_roles"])
        self.assertLessEqual(len(analysis["recommended_roles"]), 5)
        self.assertTrue(
            all(item["title"] in {job["title"] for job in JOB_PROFILES}
                for item in analysis["recommended_roles"])
        )
        self.assertTrue(
            all(10 <= item["match"] <= 99 for item in analysis["recommended_roles"])
        )
        self.assertTrue(
            all(item["matched_skills"] for item in analysis["recommended_roles"])
        )

    def test_resume_analysis_auto_selects_role_when_target_is_omitted(self):
        resume_text = (
            "Experience\nBackend Engineer 2021-2024\n"
            "- Built Python Flask APIs with PostgreSQL and Docker.\n"
            "Skills\nPython Flask PostgreSQL Docker"
        )
        response = self.client.post(
            "/api/analyze-resume",
            json={"resume_text": resume_text},
        )
        self.assertEqual(response.status_code, 200)
        analysis = response.get_json()
        self.assertEqual(
            analysis["target_role"],
            analysis["recommended_roles"][0]["title"],
        )

    def test_resume_analysis_rejects_unrelated_text_with_technical_keywords(self):
        unrelated_text = (
            "This essay discusses Python, SQL, and projects as examples of technology "
            "in modern society. It describes career growth in general terms and explains "
            "how software affects daily life, but contains no person's qualifications, "
            "work history, education, contact details, or resume sections."
        )
        response = self.client.post(
            "/api/analyze-resume",
            json={"role": "Python Full-Stack Developer", "resume_text": unrelated_text},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not look like a resume", response.get_json()["error"])

    def test_resume_upload_rejects_non_resume_content_with_allowed_extension(self):
        unrelated_text = (
            "A general article about Python and SQL describes how technology may affect "
            "career growth and projects in society, without personal employment or "
            "education information, contact details, or resume section headings."
        )
        response = self.client.post(
            "/api/analyze-resume",
            data={
                "role": "Python Full-Stack Developer",
                "resume": (io.BytesIO(unrelated_text.encode("utf-8")), "resume.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not look like a resume", response.get_json()["error"])

    def test_resume_upload_rejects_wrong_file_field_and_unsupported_extension(self):
        resume_text = (
            "Experience\nSoftware Engineer 2020-2024\n"
            "- Built Python and SQL applications.\nEducation\nComputer Science"
        )
        response = self.client.post(
            "/api/analyze-resume",
            data={
                "role": "Python Full-Stack Developer",
                "document": (io.BytesIO(resume_text.encode("utf-8")), "resume.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only resume files", response.get_json()["error"])

        response = self.client.post(
            "/api/analyze-resume",
            data={
                "role": "Python Full-Stack Developer",
                "resume": (io.BytesIO(resume_text.encode("utf-8")), "resume.doc"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.get_json()["error"])

    def test_resume_analysis_accepts_text_file_upload(self):
        response = self.client.post(
            "/api/analyze-resume",
            data={
                "role": "Data Analyst",
                "resume": (
                    io.BytesIO(
                        b"Experience\nData Analyst 2020-2022\n"
                        b"- Used SQL and Python for analytics projects.\n"
                        b"Education\nBachelor degree"
                    ),
                    "resume.txt",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["target_role"], "Data Analyst")

    def test_interview_question_endpoint_covers_catalog_and_rejects_invalid_filters(self):
        for topic in INTERVIEW_QUESTIONS:
            for level in LEVELS:
                with self.subTest(topic=topic, level=level):
                    response = self.client.get(
                        "/api/interview-questions",
                        query_string={"topic": topic, "level": level},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.get_json()["questions"])

        for params in (
            {"topic": "unknown", "level": "basic"},
            {"topic": "python", "level": "unknown"},
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get(
                        "/api/interview-questions", query_string=params
                    ).status_code,
                    400,
                )

    def test_dsa_endpoint_covers_catalog_and_rejects_invalid_filters(self):
        for topic in DSA_TOPICS:
            for difficulty in DSA_LEVELS:
                with self.subTest(topic=topic, difficulty=difficulty):
                    response = self.client.get(
                        "/api/dsa-questions",
                        query_string={"topic": topic, "difficulty": difficulty},
                    )
                    self.assertEqual(response.status_code, 200)
                    questions = response.get_json()["questions"]
                    self.assertTrue(questions)
                    self.assertTrue(all(
                        item["topic"] == topic and item["difficulty"] == difficulty
                        for item in questions
                    ))

        for params in (
            {"topic": "unknown", "difficulty": "basic"},
            {"topic": "arrays", "difficulty": "unknown"},
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get(
                        "/api/dsa-questions", query_string=params
                    ).status_code,
                    400,
                )

    def test_login_uses_mongodb_when_configured(self):
        response = self.client.post(
            "/api/auth/register",
            json={"name": "MongoDB User", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)

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
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

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
        self.assertEqual(response.headers["Location"], "/")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").status_code, 200)

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

    def test_guest_mode_allows_dashboard_and_jobs_without_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/jobs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_guest_applications_transferred_on_register(self):
        response = self.client.post(
            "/api/jobs",
            json={"company": "Guest Co", "role": "Intern"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.client.get("/api/jobs").get_json()), 1)

        response = self.client.post(
            "/api/auth/register",
            json={"name": "Converted Guest", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)

        jobs = self.client.get("/api/jobs").get_json()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Guest Co")

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
