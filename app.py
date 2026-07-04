import os
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
import random
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import db as dbmod

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB


def get_conn():
    if "conn" not in g:
        g.conn = dbmod.get_db()
    return g.conn


@app.teardown_appcontext
def close_conn(exception=None):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


@app.before_request
def track_user_presence():
    if not session.get("user_id"):
        return
    conn = get_conn()
    dbmod.prune_presence(conn, minutes=5)
    dbmod.mark_user_presence(conn, session["user_id"], is_active=True)
    conn.commit()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_conn().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


app.jinja_env.globals["current_user"] = current_user


@app.context_processor
def inject_att_today():
    user = current_user()
    if not user:
        return {}
    today = date.today().isoformat()
    att = get_conn().execute(
        "SELECT * FROM attendance WHERE user_id=? AND date=?", (user["id"], today)
    ).fetchone()
    return {"att_today": att}



def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def save_upload(file_key, subfolder=""):
    file = request.files.get(file_key)
    if not file or file.filename == "":
        return None
    filename = secure_filename(file.filename)
    unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    target_dir = os.path.join(app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, unique)
    file.save(path)
    rel = os.path.join("uploads", subfolder, unique).replace("\\", "/")
    return rel


# ---------- Auth ----------

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        conn = get_conn()
        role = request.form.get("role", "admin").strip().lower()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company_name = request.form.get("company_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, email, password, confirm]):
            flash("Please fill in all required fields.", "error")
            return render_template("signup.html", role=role)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html", role=role)
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html", role=role)
        if role not in {"admin", "employee"}:
            flash("Invalid role selected.", "error")
            return render_template("signup.html", role=role)
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("An account with that email already exists.", "error")
            return render_template("signup.html", role=role)

        if role == "admin":
            if not company_name:
                flash("Company name is required for admin signup.", "error")
                return render_template("signup.html", role=role)
            parts = name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else parts[0]
            year = date.today().year
            login_id = dbmod.generate_login_id(conn, first_name, last_name, year)
            logo_path = save_upload("logo", "logos")
            conn.execute(
                """INSERT INTO users (login_id, name, email, phone, password_hash, must_change_password,
                   role, company, date_of_joining, emp_code)
                   VALUES (?,?,?,?,?,0,?,?,?,?)""",
                (login_id, name, email, phone, generate_password_hash(password),
                 "admin", company_name, date.today().isoformat(), f"EMP{login_id[-4:]}"),
            )
            conn.execute("UPDATE company SET name = ?, logo_path = ?", (company_name, logo_path))
            conn.commit()
            dbmod.write_credentials_file(conn, {login_id: password})
            flash(f"Admin account created. Your Login ID is {login_id} — save it, you'll use it to sign in.", "success")
            return redirect(url_for("login"))

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else parts[0]
        year = date.today().year
        login_id = dbmod.generate_login_id(conn, first_name, last_name, year)
        cur = conn.execute(
            """INSERT INTO users (login_id, name, email, phone, password_hash, must_change_password,
               role, department, job_position, manager, company, location, date_of_joining, emp_code)
               VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,?)""",
            (login_id, name, email, phone, generate_password_hash(password), "employee",
             "General", "New Employee", "Admin", conn.execute("SELECT name FROM company").fetchone()["name"],
             "Head Office", date.today().isoformat(), f"EMP{login_id[-4:]}"),
        )
        uid = cur.lastrowid
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)", (uid, "paid", 24))
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)", (uid, "sick", 7))
        conn.execute("INSERT INTO salary_structure (user_id, monthly_wage) VALUES (?, ?)", (uid, 0))
        conn.commit()
        dbmod.write_credentials_file(conn, {login_id: password})
        flash(f"Employee account created. Your Login ID is {login_id} — use it to sign in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html", role="admin")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        conn = get_conn()
        user = conn.execute(
            "SELECT * FROM users WHERE login_id = ? OR email = ?", (identifier, identifier)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect Login ID/Email or password.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["name"] = user["name"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        conn = get_conn()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            flash("No account found with that email.", "error")
            return render_template("forgot_password.html")
        otp = f"{random.randint(100000, 999999)}"
        conn.execute("DELETE FROM password_resets WHERE email = ?", (email,))
        conn.execute(
            "INSERT INTO password_resets (email, otp, created_at, used) VALUES (?, ?, ?, 0)",
            (email, otp, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        session["reset_email"] = email
        flash(f"OTP sent to your email. Use code {otp} to reset your password.", "success")
        return redirect(url_for("reset_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")
    if request.method == "POST":
        email = request.form.get("email", "").strip() or email
        otp = request.form.get("otp", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not all([email, otp, password, confirm]):
            flash("Please fill in all reset fields.", "error")
            return render_template("reset_password.html", email=email)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", email=email)
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("reset_password.html", email=email)
        conn = get_conn()
        reset = conn.execute(
            "SELECT * FROM password_resets WHERE email = ? AND otp = ? AND used = 0 ORDER BY id DESC LIMIT 1",
            (email, otp),
        ).fetchone()
        if reset is None:
            flash("Invalid OTP.", "error")
            return render_template("reset_password.html", email=email)
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (generate_password_hash(password), email))
        conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset["id"],))
        conn.commit()
        session.pop("reset_email", None)
        flash("Password updated successfully. Please sign in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", email=email)


@app.route("/logout")
def logout():
    if session.get("user_id"):
        conn = get_conn()
        dbmod.mark_user_presence(conn, session["user_id"], is_active=False)
        conn.commit()
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_conn()
    user = current_user()
    today = date.today().isoformat()

    if user["role"] == "admin":
        employees = conn.execute("SELECT * FROM users WHERE role = 'employee' ORDER BY name").fetchall()
        online_ids = dbmod.get_online_employee_ids(conn, minutes=5)
        emp_data = []
        for e in employees:
            att = conn.execute(
                "SELECT * FROM attendance WHERE user_id = ? AND date = ?", (e["id"], today)
            ).fetchone()
            leave_today = conn.execute(
                """SELECT * FROM leave_requests WHERE user_id = ? AND status = 'approved'
                   AND ? BETWEEN start_date AND end_date""",
                (e["id"], today),
            ).fetchone()
            if e["id"] in online_ids:
                status = "online"
            elif leave_today:
                status = "leave"
            elif att and att["check_in"]:
                status = "present"
            else:
                status = "absent"
            emp_data.append({"user": e, "status": status})
        pending_leaves = conn.execute(
            "SELECT COUNT(*) c FROM leave_requests WHERE status = 'pending'"
        ).fetchone()["c"]
        present_today_count = sum(1 for entry in emp_data if entry["status"] in ("online", "present"))
        return render_template(
            "dashboard_admin.html",
            employees=emp_data,
            pending_leaves=pending_leaves,
            total_employees=len(employees),
            online_now=len(online_ids),
            present_today=present_today_count,
        )

    att_today = conn.execute(
        "SELECT * FROM attendance WHERE user_id = ? AND date = ?", (user["id"], today)
    ).fetchone()
    my_leaves = conn.execute(
        "SELECT * FROM leave_requests WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user["id"],)
    ).fetchall()
    return render_template("dashboard_employee.html", att_today=att_today, my_leaves=my_leaves)


# ---------- Employees (admin) ----------

@app.route("/employees")
@admin_required
def employees():
    conn = get_conn()
    q = request.args.get("q", "").strip()
    today = date.today().isoformat()
    if q:
        rows = conn.execute(
            "SELECT * FROM users WHERE role='employee' AND (name LIKE ? OR department LIKE ?) ORDER BY name",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users WHERE role='employee' ORDER BY name").fetchall()

    online_ids = dbmod.get_online_employee_ids(conn, minutes=5)
    emp_data = []
    for e in rows:
        att = conn.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (e["id"], today)).fetchone()
        leave_today = conn.execute(
            """SELECT * FROM leave_requests WHERE user_id=? AND status='approved'
               AND ? BETWEEN start_date AND end_date""",
            (e["id"], today),
        ).fetchone()
        if e["id"] in online_ids:
            status = "online"
        else:
            status = "leave" if leave_today else ("present" if att and att["check_in"] else "absent")
        emp_data.append({"user": e, "status": status})
    return render_template("employees.html", employees=emp_data, q=q)


@app.route("/employees/new", methods=["GET", "POST"])
@admin_required
def new_employee():
    if request.method == "POST":
        conn = get_conn()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        job_position = request.form.get("job_position", "").strip()
        manager = request.form.get("manager", "").strip()
        doj = request.form.get("date_of_joining") or date.today().isoformat()

        if not name or not email:
            flash("Name and email are required.", "error")
            return render_template("employee_form.html")

        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            flash("An employee with that email already exists.", "error")
            return render_template("employee_form.html")

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else parts[0]
        year = datetime.fromisoformat(doj).year
        login_id = dbmod.generate_login_id(conn, first_name, last_name, year)
        temp_password = f"{first_name[:3].lower()}@{year}"

        cur = conn.execute(
            """INSERT INTO users (login_id, name, email, phone, password_hash, must_change_password,
               role, department, job_position, manager, company, location, date_of_joining, emp_code)
               VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,?)""",
            (login_id, name, email, phone, generate_password_hash(temp_password), "employee",
             department, job_position, manager,
             conn.execute("SELECT name FROM company").fetchone()["name"], "Head Office", doj,
             f"EMP{login_id[-4:]}"),
        )
        uid = cur.lastrowid
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)",
                     (uid, "paid", 24))
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)",
                     (uid, "sick", 7))
        conn.execute("INSERT INTO salary_structure (user_id, monthly_wage) VALUES (?, ?)", (uid, 0))
        conn.commit()
        dbmod.write_credentials_file(conn, {login_id: temp_password})
        flash(f"Employee created. Login ID: {login_id}  |  Temporary password: {temp_password}", "success")
        return redirect(url_for("employees"))

    return render_template("employee_form.html")


# ---------- Profile ----------

@app.route("/profile/<int:user_id>")
@login_required
def profile(user_id):
    conn = get_conn()
    user = current_user()
    if user["id"] != user_id and user["role"] != "admin":
        abort(403)
    target = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if target is None:
        abort(404)
    tab = request.args.get("tab", "profile")
    if tab == "salary" and user["role"] != "admin":
        abort(403)

    skills = conn.execute("SELECT * FROM skills WHERE user_id=?", (user_id,)).fetchall()
    certifications = conn.execute("SELECT * FROM certifications WHERE user_id=?", (user_id,)).fetchall()
    salary = conn.execute("SELECT * FROM salary_structure WHERE user_id=?", (user_id,)).fetchone()

    is_own_profile = user["id"] == user_id
    can_edit_all = user["role"] == "admin"

    return render_template(
        "profile.html", target=target, tab=tab, skills=skills, certifications=certifications,
        salary=salary, is_own_profile=is_own_profile, can_edit_all=can_edit_all,
    )


@app.route("/profile/<int:user_id>/edit", methods=["POST"])
@login_required
def edit_profile(user_id):
    conn = get_conn()
    user = current_user()
    if user["id"] != user_id and user["role"] != "admin":
        abort(403)

    limited_fields = ["phone", "residing_address"]
    full_fields = limited_fields + [
        "name", "email", "department", "job_position", "manager", "location",
        "about", "job_love_note", "hobbies", "date_of_birth", "personal_email",
        "gender", "nationality", "marital_status", "bank_account_number", "bank_name",
        "ifsc_code", "pan_no", "uan_no",
    ]
    allowed = full_fields if user["role"] == "admin" else limited_fields

    updates = {}
    for field in allowed:
        if field in request.form:
            updates[field] = request.form.get(field, "").strip()

    pic_path = save_upload("profile_picture", "profile_pics")
    if pic_path:
        updates["profile_picture"] = pic_path

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        conn.commit()

    new_skill = request.form.get("new_skill", "").strip()
    if new_skill:
        conn.execute("INSERT INTO skills (user_id, skill_name) VALUES (?, ?)", (user_id, new_skill))
        conn.commit()

    flash("Profile updated.", "success")
    return redirect(url_for("profile", user_id=user_id, tab=request.form.get("tab", "profile")))


@app.route("/profile/<int:user_id>/salary", methods=["POST"])
@admin_required
def update_salary(user_id):
    conn = get_conn()

    def f(name, default=0):
        try:
            return float(request.form.get(name, default) or default)
        except ValueError:
            return default

    wage = f("monthly_wage")
    basic_pct = f("basic_pct", 50)
    hra_pct = f("hra_pct", 50)
    standard_allowance = f("standard_allowance", 4167)
    performance_bonus_pct = f("performance_bonus_pct", 8.33)
    lta_pct = f("lta_pct", 8.33)
    professional_tax = f("professional_tax", 200)
    pf_employee_pct = f("pf_employee_pct", 12)
    pf_employer_pct = f("pf_employer_pct", 12)

    existing = conn.execute("SELECT id FROM salary_structure WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        conn.execute(
            """UPDATE salary_structure SET monthly_wage=?, basic_pct=?, hra_pct=?, standard_allowance=?,
               performance_bonus_pct=?, lta_pct=?, professional_tax=?, pf_employee_pct=?, pf_employer_pct=?
               WHERE user_id=?""",
            (wage, basic_pct, hra_pct, standard_allowance, performance_bonus_pct, lta_pct,
             professional_tax, pf_employee_pct, pf_employer_pct, user_id),
        )
    else:
        conn.execute(
            """INSERT INTO salary_structure (user_id, monthly_wage, basic_pct, hra_pct, standard_allowance,
               performance_bonus_pct, lta_pct, professional_tax, pf_employee_pct, pf_employer_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, wage, basic_pct, hra_pct, standard_allowance, performance_bonus_pct, lta_pct,
             professional_tax, pf_employee_pct, pf_employer_pct),
        )
    conn.commit()
    flash("Salary structure saved.", "success")
    return redirect(url_for("profile", user_id=user_id, tab="salary"))


# ---------- Attendance ----------

@app.route("/admin/generate-sample-history", methods=["POST"])
@admin_required
def generate_sample_history():
    conn = get_conn()
    summary = dbmod.generate_recent_team_history(conn, days=7)
    conn.commit()
    flash(
        f"Generated {summary['attendance']} attendance records and {summary['leave_requests']} leave requests for the last 7 days.",
        "success",
    )
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/attendance")
@login_required
def attendance():
    conn = get_conn()
    user = current_user()
    month = request.args.get("month", date.today().strftime("%Y-%m"))

    if user["role"] == "admin":
        selected_date = request.args.get("date", date.today().isoformat())
        q = request.args.get("q", "").strip()
        if q:
            rows = conn.execute(
                """SELECT a.*, u.name as emp_name FROM attendance a JOIN users u ON u.id=a.user_id
                   WHERE a.date=? AND u.name LIKE ? ORDER BY u.name""",
                (selected_date, f"%{q}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, u.name as emp_name FROM attendance a JOIN users u ON u.id=a.user_id
                   WHERE a.date=? ORDER BY u.name""",
                (selected_date,),
            ).fetchall()
        return render_template("attendance_admin.html", rows=rows, selected_date=selected_date, q=q)

    rows = conn.execute(
        "SELECT * FROM attendance WHERE user_id=? AND date LIKE ? ORDER BY date DESC",
        (user["id"], f"{month}%"),
    ).fetchall()
    present_count = sum(1 for r in rows if r["check_in"])
    today = date.today().isoformat()
    att_today = conn.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (user["id"], today)).fetchone()
    return render_template("attendance_employee.html", rows=rows, month=month,
                            present_count=present_count, att_today=att_today)


@app.route("/attendance/checkin", methods=["POST"])
@login_required
def checkin():
    conn = get_conn()
    user = current_user()
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    existing = conn.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (user["id"], today)).fetchone()
    if existing and existing["check_in"]:
        flash("Already checked in today.", "error")
    elif existing:
        conn.execute("UPDATE attendance SET check_in=?, status='present' WHERE id=?", (now, existing["id"]))
        conn.commit()
    else:
        conn.execute(
            "INSERT INTO attendance (user_id, date, check_in, status) VALUES (?,?,?,?)",
            (user["id"], today, now, "present"),
        )
        conn.commit()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/attendance/checkout", methods=["POST"])
@login_required
def checkout():
    conn = get_conn()
    user = current_user()
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    existing = conn.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (user["id"], today)).fetchone()
    if not existing or not existing["check_in"]:
        flash("You need to check in first.", "error")
    elif existing["check_out"]:
        flash("Already checked out today.", "error")
    else:
        t_in = datetime.strptime(existing["check_in"], "%H:%M")
        t_out = datetime.strptime(now, "%H:%M")
        hours = round((t_out - t_in).seconds / 3600, 2)
        conn.execute("UPDATE attendance SET check_out=?, work_hours=? WHERE id=?", (now, hours, existing["id"]))
        conn.commit()
    return redirect(request.referrer or url_for("dashboard"))


# ---------- Leave ----------

@app.route("/work")
@login_required
def work():
    conn = get_conn()
    user = current_user()
    if user["role"] == "admin":
        employees = conn.execute("SELECT * FROM users WHERE role='employee' ORDER BY name").fetchall()
        tasks = conn.execute(
            """SELECT wt.*, u.name as employee_name FROM work_tasks wt JOIN users u ON u.id=wt.assigned_to
               ORDER BY wt.status, wt.due_date, wt.id DESC"""
        ).fetchall()
        return render_template("work_admin.html", employees=employees, tasks=tasks)

    tasks = conn.execute(
        """SELECT wt.*, u.name as assigned_by_name FROM work_tasks wt JOIN users u ON u.id=wt.assigned_by
           WHERE wt.assigned_to=? ORDER BY wt.status, wt.due_date, wt.id DESC""",
        (user["id"],),
    ).fetchall()
    return render_template("work_employee.html", tasks=tasks)


@app.route("/work/add", methods=["POST"])
@admin_required
def add_work_task():
    conn = get_conn()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    assigned_to = request.form.get("assigned_to", "")
    due_date = request.form.get("due_date", "")
    if not title or not assigned_to:
        flash("Task title and assignee are required.", "error")
        return redirect(url_for("work"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO work_tasks (title, description, assigned_to, assigned_by, due_date, status, progress, proof_links, proof_images, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', 0, '', '', ?, ?)""",
        (title, description, assigned_to, session["user_id"], due_date, now, now),
    )
    conn.commit()
    flash("Work task created successfully.", "success")
    return redirect(url_for("work"))


@app.route("/work/<int:task_id>/update", methods=["POST"])
@login_required
def update_work_task(task_id):
    conn = get_conn()
    task = conn.execute("SELECT * FROM work_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        abort(404)
    if session.get("role") != "admin" and task["assigned_to"] != session["user_id"]:
        abort(403)

    progress = request.form.get("progress", "0").strip()
    status = request.form.get("status", task["status"])
    proof_links = request.form.get("proof_links", "").strip()
    proof_images = request.form.get("proof_images", "").strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        progress_value = int(progress)
    except ValueError:
        progress_value = 0
    progress_value = max(0, min(100, progress_value))

    conn.execute(
        "UPDATE work_tasks SET progress=?, status=?, proof_links=?, proof_images=?, updated_at=? WHERE id=?",
        (progress_value, status, proof_links, proof_images, now, task_id),
    )
    conn.commit()
    flash("Work progress updated.", "success")
    return redirect(url_for("work"))


@app.route("/leave")
@login_required
def leave():
    conn = get_conn()
    user = current_user()
    if user["role"] == "admin":
        rows = conn.execute(
            """SELECT l.*, u.name as emp_name FROM leave_requests l JOIN users u ON u.id=l.user_id
               ORDER BY l.status='pending' DESC, l.id DESC"""
        ).fetchall()
        return render_template("leave_admin.html", rows=rows)

    rows = conn.execute("SELECT * FROM leave_requests WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    allocations = conn.execute("SELECT * FROM leave_allocations WHERE user_id=?", (user["id"],)).fetchall()
    return render_template("leave_employee.html", rows=rows, allocations=allocations)


@app.route("/leave/apply", methods=["POST"])
@login_required
def apply_leave():
    conn = get_conn()
    user = current_user()
    leave_type = request.form.get("leave_type")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    remarks = request.form.get("remarks", "").strip()

    if not all([leave_type, start_date, end_date]):
        flash("Please fill in all leave request fields.", "error")
        return redirect(url_for("leave"))

    d1 = datetime.fromisoformat(start_date)
    d2 = datetime.fromisoformat(end_date)
    if d2 < d1:
        flash("End date cannot be before start date.", "error")
        return redirect(url_for("leave"))
    days = (d2 - d1).days + 1

    conn.execute(
        "INSERT INTO leave_requests (user_id, leave_type, start_date, end_date, days, remarks) VALUES (?,?,?,?,?,?)",
        (user["id"], leave_type, start_date, end_date, days, remarks),
    )
    conn.commit()
    flash("Leave request submitted.", "success")
    return redirect(url_for("leave"))


@app.route("/leave/<int:leave_id>/approve", methods=["POST"])
@admin_required
def approve_leave(leave_id):
    conn = get_conn()
    lr = conn.execute("SELECT * FROM leave_requests WHERE id=?", (leave_id,)).fetchone()
    if lr is None:
        abort(404)
    conn.execute("UPDATE leave_requests SET status='approved', admin_comment=? WHERE id=?",
                 (request.form.get("comment", ""), leave_id))
    if lr["leave_type"] in ("paid", "sick"):
        conn.execute(
            "UPDATE leave_allocations SET days_available = days_available - ? WHERE user_id=? AND leave_type=?",
            (lr["days"], lr["user_id"], lr["leave_type"]),
        )
    conn.commit()
    flash("Leave approved.", "success")
    return redirect(url_for("leave"))


@app.route("/leave/<int:leave_id>/reject", methods=["POST"])
@admin_required
def reject_leave(leave_id):
    conn = get_conn()
    conn.execute("UPDATE leave_requests SET status='rejected', admin_comment=? WHERE id=?",
                 (request.form.get("comment", ""), leave_id))
    conn.commit()
    flash("Leave rejected.", "success")
    return redirect(url_for("leave"))


# ---------- Settings ----------

@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    conn = get_conn()
    if request.method == "POST":
        name = request.form.get("company_name", "").strip()
        logo_path = save_upload("logo", "logos")
        if logo_path:
            conn.execute("UPDATE company SET name=?, logo_path=?", (name, logo_path))
        else:
            conn.execute("UPDATE company SET name=?", (name,))
        conn.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    company = conn.execute("SELECT * FROM company").fetchone()
    return render_template("settings.html", company=company)


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You don't have access to this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found."), 404


with app.app_context():
    dbmod.init_db()
    dbmod.seed_demo_data()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
