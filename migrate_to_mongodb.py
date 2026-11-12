import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def object_id_for_legacy_id(legacy_id):
    value = int(legacy_id)
    if not 0 <= value < 2**96:
        raise ValueError(f"Legacy ID {legacy_id!r} cannot be represented as a MongoDB ObjectId")
    return ObjectId(f"{value:024x}")


def as_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def open_sqlite_source():
    database_path = os.getenv("SQLITE_PATH")
    if database_path:
        database_path = Path(database_path).expanduser()
    else:
        database_path = BASE_DIR / "database" / "applications.sqlite3"
    if not database_path.is_file():
        raise FileNotFoundError(f"SQLite source database does not exist: {database_path}")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def open_mysql_source():
    import mysql.connector

    missing_settings = [
        key for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
        if not os.getenv(key)
    ]
    if missing_settings:
        raise RuntimeError(
            "Missing MySQL source settings: " + ", ".join(missing_settings)
        )
    port = int(os.getenv("DB_PORT", "3306"))
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be between 1 and 65535.")
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=port,
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def read_sql_rows(connection, backend):
    cursor = connection.cursor(dictionary=True) if backend == "mysql" else connection.cursor()
    try:
        cursor.execute("SELECT id, name, password_hash, created_at FROM users ORDER BY id")
        users = cursor.fetchall()

        if backend == "mysql":
            cursor.execute("SHOW COLUMNS FROM applications")
            application_columns = {row["Field"] for row in cursor.fetchall()}
        else:
            cursor.execute("PRAGMA table_info(applications)")
            application_columns = {row["name"] for row in cursor.fetchall()}

        user_id_column = "user_id" if "user_id" in application_columns else "NULL AS user_id"
        cursor.execute(
            f"""
            SELECT id, {user_id_column}, company, role, status, skills, applied_date
            FROM applications
            ORDER BY id
            """
        )
        applications = cursor.fetchall()
        return users, applications
    finally:
        cursor.close()


def migrate_rows(database, users, applications, source_name):
    database.users.create_index("name_key", unique=True)
    database.applications.create_index([("user_id", 1), ("_id", -1)])

    user_ids = {}
    for row in users:
        document_id = object_id_for_legacy_id(row["id"])
        document = {
            "_id": document_id,
            "name": row["name"],
            "name_key": row["name"].casefold(),
            "password_hash": row["password_hash"],
            "created_at": as_datetime(row["created_at"]),
            "migration_source": source_name,
        }
        database.users.replace_one(
            {"_id": document_id},
            document,
            upsert=True,
        )
        user_ids[int(row["id"])] = str(document_id)

    for row in applications:
        legacy_user_id = row["user_id"]
        if legacy_user_id is not None and int(legacy_user_id) not in user_ids:
            raise ValueError(
                f"Application {row['id']} refers to missing user ID {legacy_user_id}"
            )
        document_id = object_id_for_legacy_id(row["id"])
        document = {
            "_id": document_id,
            "user_id": (
                user_ids[int(legacy_user_id)] if legacy_user_id is not None else None
            ),
            "company": row["company"],
            "role": row["role"],
            "status": row["status"],
            "skills": row["skills"] or "",
            "applied_date": as_datetime(row["applied_date"]),
            "migration_source": source_name,
        }
        database.applications.replace_one(
            {"_id": document_id},
            document,
            upsert=True,
        )

    return len(users), len(applications)


def main():
    backend = os.getenv("SOURCE_DB_BACKEND", "").strip().lower()
    if backend not in {"sqlite", "mysql"}:
        raise RuntimeError("Set SOURCE_DB_BACKEND to sqlite or mysql for the SQL source.")

    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI must be configured for the MongoDB destination.")
    mongo_database_name = os.getenv("MONGODB_DB_NAME", "devtrack_ai")

    source = None
    client = None
    try:
        source = open_sqlite_source() if backend == "sqlite" else open_mysql_source()
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        source_rows = read_sql_rows(source, backend)
        sqlite_path = Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "database" / "applications.sqlite3")))
        source_name = (
            f"{backend}:{os.getenv('DB_NAME')}"
            if backend == "mysql"
            else f"sqlite:{sqlite_path.name}"
        )
        counts = migrate_rows(client[mongo_database_name], *source_rows, source_name)
        print(f"Migrated {counts[0]} users and {counts[1]} applications.")
    finally:
        if source is not None:
            source.close()
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
