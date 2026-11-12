import logging
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, DuplicateKeyError, PyMongoError
from werkzeug.exceptions import RequestEntityTooLarge
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

app = Flask(__name__, static_folder="public/static")
app.config.update(
    SECRET_KEY=flask_secret_key or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
        "SESSION_COOKIE_SECURE", "true" if is_vercel else "false"
    ).lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
if not flask_secret_key:
    logging.warning("FLASK_SECRET_KEY is not set; sessions will reset when the app restarts.")
DB_ERRORS = (PyMongoError,)
_mongo_client = None
_mongo_database = None
_mongo_settings = None
_mongo_lock = threading.Lock()


def ensure_session_user():
    if "user_id" not in session:
        session.permanent = True
        session["user_id"] = f"guest_{secrets.token_urlsafe(12)}"
        session["user_name"] = "Guest"
    elif "user_name" not in session or not session["user_name"]:
        session["user_name"] = "Guest"
    return session["user_id"], session["user_name"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        ensure_session_user()
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/login")
def login():
    return redirect(url_for("home"))


def get_db():
    global _mongo_client, _mongo_database, _mongo_settings

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise ConfigurationError(
            "MONGODB_URI must be configured before using database-backed endpoints."
        )
    database_name = os.getenv("MONGODB_DB_NAME", "devtrack_ai")
    settings = (uri, database_name)

    with _mongo_lock:
        if settings != _mongo_settings:
            if _mongo_client is not None:
                _mongo_client.close()
            _mongo_client = None
            _mongo_database = None
            _mongo_settings = None

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            try:
                client.admin.command("ping")
                database = client[database_name]
                database.users.create_index("name_key", unique=True)
                database.applications.create_index([("user_id", 1), ("_id", -1)])
            except PyMongoError:
                client.close()
                raise

            _mongo_client = client
            _mongo_database = database
            _mongo_settings = settings

    return _mongo_database


@app.errorhandler(413)
def request_entity_too_large(_error):
    return jsonify({"error": "Request body must be 10 MB or smaller"}), 413


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

    try:
        database = get_db()
        is_first_user = database.users.count_documents({}) == 0
        name_key = name.casefold()
        if database.users.find_one({"name_key": name_key}):
            return jsonify({"error": "An account with that name already exists"}), 409

        guest_user_id = session.get("user_id")
        user = {
            "name": name,
            "name_key": name_key,
            "password_hash": generate_password_hash(password),
            "created_at": datetime.now(timezone.utc),
        }
        user_id = database.users.insert_one(user).inserted_id
        if is_first_user:
            database.applications.update_many(
                {"user_id": None},
                {"$set": {"user_id": str(user_id)}},
            )
        if guest_user_id and guest_user_id.startswith("guest_"):
            database.applications.update_many(
                {"user_id": guest_user_id},
                {"$set": {"user_id": str(user_id)}},
            )
        session.clear()
        session.permanent = True
        session["user_id"] = str(user_id)
        session["user_name"] = name
        return jsonify({"message": "Account created", "redirect": url_for("dashboard")}), 201
    except DuplicateKeyError:
        return jsonify({"error": "An account with that name already exists"}), 409
    except DB_ERRORS:
        logging.exception("Could not register account")
        return jsonify({"error": "Could not create your account"}), 500


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request_json_object()
    name = data.get("name")
    password = data.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        return jsonify({"error": "Name and password are required"}), 400
    if not 2 <= len(name.strip()) <= 80 or not 1 <= len(password) <= 128:
        return jsonify({"error": "Invalid name or password"}), 400

    try:
        database = get_db()
        user = database.users.find_one({"name_key": name.strip().casefold()})
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid name or password"}), 401

        session.clear()
        session.permanent = True
        session["user_id"] = str(user["_id"])
        session["user_name"] = user["name"]
        return jsonify({"message": "Signed in", "redirect": url_for("dashboard")})
    except DB_ERRORS:
        logging.exception("Could not sign in")
        return jsonify({"error": "Could not sign in right now"}), 500


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({
        "message": "Signed out",
        "redirect": url_for("home"),
    })


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))


def request_json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.route("/api/jobs", methods=["GET"])
@login_required
def get_jobs():
    user_id, _ = ensure_session_user()
    try:
        jobs = list(
            get_db().applications.find(
                {"user_id": user_id},
                {"company": 1, "role": 1, "status": 1, "skills": 1, "applied_date": 1},
            ).sort("_id", -1)
        )
        for job in jobs:
            job["id"] = str(job.pop("_id"))
            if job["applied_date"]:
                applied_date = job["applied_date"]
                job["applied_date"] = (
                    applied_date.isoformat()
                    if hasattr(applied_date, "isoformat")
                    else str(applied_date)
                )

        return jsonify(jobs)

    except DB_ERRORS:
        logging.exception("Could not load applications")
        return jsonify({"error": "Could not load applications right now"}), 500


@app.route("/api/jobs", methods=["POST"])
@login_required
def add_job():
    user_id, _ = ensure_session_user()
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
        result = get_db().applications.insert_one({
            "user_id": user_id,
            "company": company,
            "role": role,
            "status": status,
            "skills": skills,
            "applied_date": datetime.now(timezone.utc),
        })

        return jsonify({
            "message": "Application added successfully",
            "id": str(result.inserted_id)
        }), 201

    except DB_ERRORS:
        logging.exception("Could not add application")
        return jsonify({"error": "Could not add application right now"}), 500


@app.route("/api/jobs/<job_id>", methods=["PUT"])
@login_required
def update_job(job_id):
    user_id, _ = ensure_session_user()
    data = request_json_object()
    status = data.get("status", "")
    if not isinstance(status, str):
        return jsonify({"error": "Status must be text"}), 400
    status = status.strip()

    if status not in ["Applied", "Interview", "Selected", "Rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    if not ObjectId.is_valid(job_id):
        return jsonify({"error": "Application not found"}), 404

    try:
        result = get_db().applications.update_one(
            {"_id": ObjectId(job_id), "user_id": user_id},
            {"$set": {"status": status}},
        )
        if not result.matched_count:
            return jsonify({"error": "Application not found"}), 404

        return jsonify({"message": "Status updated successfully"})

    except DB_ERRORS:
        logging.exception("Could not update application")
        return jsonify({"error": "Could not update application right now"}), 500


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
@login_required
def delete_job(job_id):
    user_id, _ = ensure_session_user()
    if not ObjectId.is_valid(job_id):
        return jsonify({"error": "Application not found"}), 404

    try:
        result = get_db().applications.delete_one(
            {"_id": ObjectId(job_id), "user_id": user_id}
        )
        if not result.deleted_count:
            return jsonify({"error": "Application not found"}), 404

        return jsonify({"message": "Application deleted"})

    except DB_ERRORS:
        logging.exception("Could not delete application")
        return jsonify({"error": "Could not delete application right now"}), 500


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

        if request.files:
            if "resume" not in request.files:
                return jsonify({"error": "Only resume files are valid for analysis"}), 400

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

        if not resume_text:
            return jsonify({"error": "Please provide a resume file (PDF, DOCX, TXT) or paste resume text"}), 400

        analysis = analyze_resume_for_role(resume_text, target_role)
        return jsonify(analysis)

    except RequestEntityTooLarge:
        raise
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        logging.exception("Failed to analyze resume")
        return jsonify({"error": "Failed to analyze resume right now"}), 500


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

        if platform not in {"all", "remoteok", "jobicy", "arbeitnow"}:
            return jsonify({"error": "Invalid job platform"}), 400

        if employment_type not in {"all", "fresher", "internship", "part_time", "freelance"}:
            return jsonify({"error": "Invalid employment type"}), 400

        results = search_role_jobs(
            role=role,
            location=location,
            platform=platform,
            employment_type=employment_type,
        )
        return jsonify(results)

    except Exception:
        logging.exception("Failed to search jobs")
        return jsonify({"error": "Failed to search jobs right now"}), 500


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
