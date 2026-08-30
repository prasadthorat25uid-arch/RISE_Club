# RISE Club Portal — Production-Ready Backend Edition

This package converts the original static RISE prototype into a server-backed club portal.

## What is now real

- Server-side email/password authentication using secure, HTTP-only session cookies.
- No member self-registration. Only Admin/Super Admin can create member/lead/mentor accounts.
- Central SQLite database for local deployment.
- Admin can enable/disable member accounts; disabled users are logged out and cannot sign in.
- Public Join RISE form writes applications to the database.
- Research ideas, tasks, announcements and events are stored centrally.
- Role-based API authorization is enforced on the server.
- Audit log records important actions.
- CSV reports for admins.
- Private file upload endpoint with server-side authentication.
- SMTP invitation email when SMTP environment variables are configured.

## Local setup

1. Install Python 3.11+.
2. Copy `.env.example` to `.env` and set a strong `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.
3. Install dependencies:
   `python -m pip install -r requirements.txt`
4. Start:
   `uvicorn backend:app --reload --host 0.0.0.0 --port 8000`
5. Open `http://localhost:8000/`.
6. Portal: `http://localhost:8000/portal.html`.

The first admin account is created automatically from `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

## Email

Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM and PUBLIC_BASE_URL. When an administrator creates a member, the server sends the member their portal URL, email and temporary password.

For production, use a transactional SMTP provider and HTTPS. Set `COOKIE_SECURE=true` behind HTTPS.

## Deployment

A persistent production database is required. The included default SQLite database is suitable for a single-server deployment or testing. Do not use ephemeral serverless storage for the SQLite file. For a production multi-instance deployment, migrate the SQL layer to PostgreSQL and point uploads to durable object storage.

The app can be deployed to a Python-capable service such as Render, Railway, Fly.io, or a VPS. Start command:

`uvicorn backend:app --host 0.0.0.0 --port $PORT`

## Security notes

- Never publish `.env`, `rise.db`, or `private_uploads/`.
- Change the initial admin password immediately.
- Use HTTPS and `COOKIE_SECURE=true` in production.
- Use a long random SECRET_KEY.
- Add institution-approved SSO/Google Workspace authentication if required by Sanjivani University.
- For serious production use with multiple servers, use PostgreSQL and object storage.
