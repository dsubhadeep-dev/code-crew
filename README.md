# HRMS-BY CODE CREW — Human Resource Management System

A full-stack HR system: authentication, role-based dashboards, employee profiles,
attendance (check-in/out), leave/time-off with approvals, and an auto-calculating
salary structure tab. Built with Flask + SQLite + server-rendered HTML/CSS/JS —
no build step, no separate frontend server.

## Run it locally

```bash
cd hrms
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

A `hrms.db` SQLite file is created automatically on first run, seeded with:

- **Admin** — check your terminal/console output is not shown for the login ID;
  instead open `hrms.db` or just sign up fresh via `/signup` to create your own
  Admin account. A demo admin is also seeded with password `admin123` — its
  Login ID follows the pattern `OIADUS<year>0001`.
- **3 demo employees** — password `employee123` for all of them.

To see every seeded Login ID, run:

```bash
python3 -c "import db; c=db.get_db(); [print(r['login_id'], r['role']) for r in c.execute('SELECT login_id, role FROM users')]"
```

## Project structure

```
hrms/
  app.py              Flask routes and app logic
  db.py                Database schema, connection, seed data
  wsgi.py              Production entry point
  Procfile             For gunicorn-based hosts (Render, Railway, Heroku)
  requirements.txt
  templates/           Jinja2 HTML templates
  static/css/           Stylesheet (responsive)
  static/js/            Salary calculator + interactivity
  static/uploads/       Profile pictures, resumes, logos, attachments
```

## Deploying

This app is stateless except for SQLite + the `uploads/` folder, so any host
that gives you persistent disk works (Render, Railway, a VPS, PythonAnywhere).
Platforms with ephemeral filesystems (e.g. plain Heroku dynos) will reset the
database on every deploy/restart — fine for a demo, not for production data.

**General steps (Render/Railway style):**

1. Push this folder to a GitHub repo.
2. Create a new "Web Service" from the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn wsgi:app`
5. Set an environment variable `SECRET_KEY` to a long random string.
6. Attach a persistent disk mounted at the project folder if the platform
   offers one, so `hrms.db` and `static/uploads/` survive restarts.

**Environment variables:**

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key — set a real value in production | `dev-secret-change-me` |
| `PORT` | Port to bind (most hosts set this for you) | `5000` |

## Roles

- **Admin/HR** signs up via `/signup` (this is also how the company is created).
- Admin adds employees from **Employees → + Add Employee** — a Login ID and
  temporary password are generated and shown once; share them with the employee.
- Employees cannot self-register, per the original spec.

## What's implemented vs. deferred

Implemented: auth, roles, dashboards, employee directory with live status
icons, full profile (Profile / Private Info / Resume / Skills / Certifications
tabs), admin-only Salary Info tab with a live-recalculating component engine,
attendance check-in/out with computed work hours, leave apply + allocations +
admin approve/reject, company settings.

Deferred (flagged for a v2): email verification on signup, resume/document
preview rendering (upload works, inline preview does not), certifications
add/edit form (currently seed/read-only in the UI), payslip generation from
attendance data.
