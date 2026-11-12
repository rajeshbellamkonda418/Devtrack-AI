# Migrating existing SQL data to MongoDB

The backend now stores accounts and applications in MongoDB. Existing SQLite
and MySQL records are not copied automatically; run the migration before
switching production traffic to the new backend.

1. Install the project dependencies with `pip install -r requirements.txt`.
2. Set `MONGODB_URI` and optionally `MONGODB_DB_NAME` for the MongoDB target.
3. Set `SOURCE_DB_BACKEND` to `sqlite` or `mysql`.
4. For SQLite, set `SQLITE_PATH` if the database is not at
   `database/applications.sqlite3`. For MySQL, set the source `DB_HOST`,
   `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`.
5. Run `python migrate_to_mongodb.py` and verify the reported user/application
   counts before deploying the MongoDB-backed application.

The migration uses stable MongoDB IDs derived from SQL IDs, preserves user
password hashes and application ownership, and can be safely rerun against the
same MongoDB database. It does not delete or modify the SQL source. Keep a
backup of both databases and pause writes during the final migration/cutover
to avoid missing changes made while the export is running.
