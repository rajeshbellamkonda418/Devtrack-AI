# Deploying to Vercel

Vercel detects the Flask application in `app.py`. Static assets are kept under
`public/static` so Vercel can serve them from its CDN; templates are included in
the Python function by `vercel.json`.

Create a MongoDB database (for example, in MongoDB Atlas) and configure these
environment variables in the Vercel project for every deployment environment:

- `FLASK_SECRET_KEY`: a long, random secret used to sign sessions.
- `MONGODB_URI`: the MongoDB connection URI. Restrict its database user to the
  application database and allow the deployed service to reach the cluster.
- `MONGODB_DB_NAME`: the database name; defaults to `devtrack_ai`.

The application creates its collections and indexes when the first database
request is made. Vercel's function filesystem is ephemeral, so the app does not
use a local SQLite database for persistent data.
