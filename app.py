import logging
import os
import secrets
import sqlite3
import threading
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash
from ml.model import recommend_jobs
from ml.resume_analyzer import analyze_resume_for_role, extract_text_from_file
from ml.job_search import search_role_jobs
from ml.interview_questions import INTERVIEW_QUESTIONS, LEVELS, get_interview_questions
from ml.dsa_questions import DSA_LEVELS, DSA_TOPICS, get_dsa_questions

BASE_DIR = Path(__file__).resolve().parent

env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path, override=False)

flask_secret_key = os.getenv("FLASK_SECRET_KEY")
is_vercel = bool(os.getenv("VERCEL"))
if not flask_secret_key and is_vercel:
    raise RuntimeError(
        "FLASK_SECRET_KEY must be configured in Vercel Project Settings > Environment Variables."
    )

db_backend = os.getenv("DB_BACKEND", "sqlite").lower()
if is_vercel and db_backend != "mysql":
    raise RuntimeError(
        "Vercel requires a persistent MySQL database; configure DB_BACKEND=mysql and "
        "set DB_HOST, DB_USER, DB_PASSWORD, and DB_NAME in Project Settings > Environment Variables."
    )
if is_vercel:
    missing_db_settings = [
        key for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
        if not os.getenv(key)
    ]
    if missing_db_settings:
        raise RuntimeError(
            "Missing required Vercel database environment variables: "
            + ", ".join(missing_db_settings)
            + ". Configure them in Project Settings > Environment Variables."
        )

app = Flask(__name__, static_folder="public/static")
app.config.update(
    SECRET_KEY=flask_secret_key or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
        "SESSION_COOKIE_SECURE", "true" if is_vercel else "false"
    ).lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
if not flask_secret_key:
    logging.warning("FLASK_SECRET_KEY is not set; sessions will reset when the app restarts.")
DB_ERRORS = (Error, sqlite3.Error)
_mysql_auth_schema_initialized = False
_mysql_auth_schema_lock = threading.Lock()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please sign in to continue"}), 401
            return redirect(url_for("home", _anchor="account-access"))
        return view(*args, **kwargs)

    return wrapped


def initialize_mysql_auth_schema(connection):
    global _mysql_auth_schema_initialized
    if _mysql_auth_schema_initialized:
        return

    with _mysql_auth_schema_lock:
        if _mysql_auth_schema_initialized:
            return

        cursor = connection.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NULL,
                    company VARCHAR(120) NOT NULL,
                    role VARCHAR(120) NOT NULL,
                    status ENUM(
                        'Applied',
                        'Interview',
                        'Selected',
                        'Rejected'
                    ) NOT NULL DEFAULT 'Applied',
                    skills TEXT,
                    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX applications_user_id_idx (user_id)
                )
            """)
            cursor.execute("SHOW COLUMNS FROM applications LIKE 'user_id'")
            if not cursor.fetchone():
                try:
                    cursor.execute("ALTER TABLE applications ADD COLUMN user_id INT NULL")
                except Error as error:
                    if error.errno != 1060:
                        raise
            try:
                cursor.execute("CREATE INDEX applications_user_id_idx ON applications (user_id)")
            except Error as error:
                if error.errno != 1061:
                    raise
            connection.commit()
        finally:
            cursor.close()

        _mysql_auth_schema_initialized = True


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/login")
def login():
    return redirect(url_for("home", _anchor="account-access"))


class SQLiteCursor:
    def __init__(self, cursor, dictionary=False):
        self.cursor = cursor
        self.dictionary = dictionary

    def execute(self, query, params=None):
        query = query.replace("%s", "?")
        if params is None:
            self.cursor.execute(query)
        else:
            self.cursor.execute(query, params)
        return self

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows] if self.dictionary else rows

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if self.dictionary and row else row

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def close(self):
        self.cursor.close()


class SQLiteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self, dictionary=False):
        return SQLiteCursor(self.connection.cursor(), dictionary=dictionary)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def get_db():
    if os.getenv("DB_BACKEND", "sqlite").lower() == "sqlite":
        database_path = Path(
            os.getenv("SQLITE_PATH", str(BASE_DIR / "database" / "applications.sqlite3"))
        )
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                company VARCHAR(120) NOT NULL,
                role VARCHAR(120) NOT NULL,
                status TEXT NOT NULL DEFAULT 'Applied'
                    CHECK (status IN ('Applied', 'Interview', 'Selected', 'Rejected')),
                skills TEXT,
                applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        application_columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(applications)")
        }
        if "user_id" not in application_columns:
            connection.execute("ALTER TABLE applications ADD COLUMN user_id INTEGER")
        return SQLiteConnection(connection)

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    try:
        initialize_mysql_auth_schema(connection)
    except Exception:
        connection.close()
        raise
    return connection


@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request_json_object()
    name = data.get("name")
    password = data.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        return jsonify({"error": "Name and password are required"}), 400

    name = name.strip()
    if not 2 <= len(name) <= 80:
        return jsonify({"error": "Name must be between 2 and 80 characters"}), 400
    if not 8 <= len(password) <= 128:
        return jsonify({"error": "Password must be between 8 and 128 characters"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        is_first_user = cursor.fetchone()[0] == 0
        cursor.execute("SELECT id FROM users WHERE name=%s", (name,))
        if cursor.fetchone():
            return jsonify({"error": "An account with that name already exists"}), 409

        cursor.execute(
            "INSERT INTO users (name, password_hash) VALUES (%s, %s)",
            (name, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
        if is_first_user:
            cursor.execute(
                "UPDATE applications SET user_id=%s WHERE user_id IS NULL",
                (user_id,),
            )
        conn.commit()
        session.clear()
        session.permanent = True
        session["user_id"] = user_id
        session["user_name"] = name
        return jsonify({"message": "Account created", "redirect": url_for("dashboard")}), 201
    except DB_ERRORS as error:
        if isinstance(error, sqlite3.IntegrityError) or getattr(error, "errno", None) == 1062:
            return jsonify({"error": "An account with that name already exists"}), 409
        logging.exception("Could not register account")
        return jsonify({"error": "Could not create your account"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request_json_object()
    name = data.get("name")
    password = data.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        return jsonify({"error": "Name and password are required"}), 400
    if not 2 <= len(name.strip()) <= 80 or not 1 <= len(password) <= 128:
        return jsonify({"error": "Invalid name or password"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, password_hash FROM users WHERE name=%s",
            (name.strip(),),
        )
        user = cursor.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid name or password"}), 401

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return jsonify({"message": "Signed in", "redirect": url_for("dashboard")})
    except DB_ERRORS:
        logging.exception("Could not sign in")
        return jsonify({"error": "Could not sign in right now"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({
        "message": "Signed out",
        "redirect": url_for("home", _anchor="account-access"),
    })


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("home", _anchor="account-access"))


def request_json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.route("/api/jobs", methods=["GET"])
@login_required
def get_jobs():
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, company, role, status, skills, applied_date
            FROM applications
            WHERE user_id=%s
            ORDER BY id DESC
        """, (session["user_id"],))
        jobs = cursor.fetchall()

        cursor.close()
        conn.close()

        for job in jobs:
            if job["applied_date"]:
                applied_date = job["applied_date"]
                job["applied_date"] = (
                    applied_date.isoformat()
                    if hasattr(applied_date, "isoformat")
                    else str(applied_date)
                )

        return jsonify(jobs)

    except DB_ERRORS as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs", methods=["POST"])
@login_required
def add_job():
    data = request_json_object()

    company = data.get("company", "")
    role = data.get("role", "")
    status = data.get("status", "Applied")
    skills = data.get("skills", "")
    if not all(isinstance(value, str) for value in (company, role, status, skills)):
        return jsonify({"error": "Company, role, status, and skills must be text"}), 400

    company = company.strip()
    role = role.strip()
    status = status.strip()
    skills = skills.strip()

    if not company or not role:
        return jsonify({"error": "Company and role are required"}), 400
    if len(company) > 120 or len(role) > 120:
        return jsonify({"error": "Company and role must be 120 characters or fewer"}), 400

    if status not in ["Applied", "Interview", "Selected", "Rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO applications
            (user_id, company, role, status, skills)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session["user_id"], company, role, status, skills)
        )

        conn.commit()
        new_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return jsonify({
            "message": "Application added successfully",
            "id": new_id
        }), 201

    except DB_ERRORS as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<int:job_id>", methods=["PUT"])
@login_required
def update_job(job_id):
    data = request_json_object()
    status = data.get("status", "")
    if not isinstance(status, str):
        return jsonify({"error": "Status must be text"}), 400
    status = status.strip()

    if status not in ["Applied", "Interview", "Selected", "Rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE applications SET status=%s WHERE id=%s AND user_id=%s",
            (status, job_id, session["user_id"])
        )

        conn.commit()
        changed = cursor.rowcount

        cursor.close()
        conn.close()

        if not changed:
            return jsonify({"error": "Application not found"}), 404

        return jsonify({"message": "Status updated successfully"})

    except DB_ERRORS as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<int:job_id>", methods=["DELETE"])
@login_required
def delete_job(job_id):
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM applications WHERE id=%s AND user_id=%s",
            (job_id, session["user_id"])
        )

        conn.commit()
        changed = cursor.rowcount

        cursor.close()
        conn.close()

        if not changed:
            return jsonify({"error": "Application not found"}), 404

        return jsonify({"message": "Application deleted"})

    except DB_ERRORS as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recommend", methods=["POST"])
def recommend():
    data = request_json_object()

    skills = data.get("skills", "")
    if not isinstance(skills, str):
        return jsonify({"error": "Skills must be text"}), 400
    skills = skills.strip()
    if not skills:
        return jsonify({"error": "Enter your skills"}), 400

    recommendations = recommend_jobs(skills)

    return jsonify({
        "recommendations": recommendations
    })


@app.route("/api/analyze-resume", methods=["POST"])
def analyze_resume():
    try:
        target_role = ""
        resume_text = ""

        if "resume" in request.files:
            file = request.files["resume"]
            if not file or not file.filename:
                return jsonify({"error": "No resume file selected"}), 400

            target_role = (request.form.get("role") or "").strip()
            resume_text = extract_text_from_file(file.stream, file.filename)
        else:
            data = request_json_object()
            target_role = data.get("role", "")
            resume_text = data.get("resume_text", "")

        if not isinstance(target_role, str) or not isinstance(resume_text, str):
            return jsonify({"error": "Target role and resume text must be text"}), 400
        target_role = target_role.strip()
        resume_text = resume_text.strip()

        if not target_role:
            return jsonify({"error": "Target role is required for resume analysis"}), 400

        if not resume_text:
            return jsonify({"error": "Please provide a resume file (PDF, DOCX, TXT) or paste resume text"}), 400

        analysis = analyze_resume_for_role(resume_text, target_role)
        return jsonify(analysis)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to analyze resume: {str(e)}"}), 500


@app.route("/api/search-jobs", methods=["GET", "POST"])
def search_jobs():
    try:
        if request.method == "POST":
            data = request_json_object()
            fields = {
                "role": data.get("role", ""),
                "location": data.get("location", "Remote"),
                "platform": data.get("platform", "all"),
                "employment_type": data.get("employment_type", "all"),
            }
            if not all(isinstance(value, str) for value in fields.values()):
                return jsonify({"error": "Search parameters must be text"}), 400
            role = fields["role"].strip()
            location = fields["location"].strip()
            platform = fields["platform"].strip().lower()
            employment_type = fields["employment_type"].strip().lower()
        else:
            role = (request.args.get("role") or "").strip()
            location = (request.args.get("location") or "Remote").strip()
            platform = (request.args.get("platform") or "all").strip().lower()
            employment_type = (request.args.get("employment_type") or "all").strip().lower()

        if not role:
            return jsonify({"error": "Role is required for job search"}), 400

        if employment_type not in {"all", "fresher", "internship", "part_time", "freelance"}:
            return jsonify({"error": "Invalid employment type"}), 400

        results = search_role_jobs(
            role=role,
            location=location,
            platform=platform,
            employment_type=employment_type,
        )
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": f"Failed to search jobs: {str(e)}"}), 500


@app.route("/api/interview-questions", methods=["GET"])
def interview_questions():
    topic = (request.args.get("topic") or "").strip().lower()
    level = (request.args.get("level") or "").strip().lower()

    if topic not in INTERVIEW_QUESTIONS:
        return jsonify({"error": "Choose a valid interview topic"}), 400
    if level not in LEVELS:
        return jsonify({"error": "Choose a valid difficulty level"}), 400

    return jsonify({
        "topic": topic,
        "level": level,
        "questions": get_interview_questions(topic, level),
    })


@app.route("/api/dsa-questions", methods=["GET"])
def dsa_questions():
    topic = (request.args.get("topic") or "all").strip().lower()
    difficulty = (request.args.get("difficulty") or "all").strip().lower()

    if topic != "all" and topic not in DSA_TOPICS:
        return jsonify({"error": "Choose a valid DSA topic"}), 400
    if difficulty != "all" and difficulty not in DSA_LEVELS:
        return jsonify({"error": "Choose a valid difficulty level"}), 400

    return jsonify({
        "topic": topic,
        "difficulty": difficulty,
        "questions": get_dsa_questions(topic, difficulty),
    })


if __name__ == "__main__":
    app.run(debug=True)
