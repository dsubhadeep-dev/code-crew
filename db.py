import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrms.db")
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.txt")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    must_change_password INTEGER DEFAULT 1,
    role TEXT CHECK(role IN ('admin','employee')) NOT NULL,
    department TEXT,
    job_position TEXT,
    manager TEXT,
    company TEXT,
    location TEXT,
    profile_picture TEXT,
    about TEXT,
    job_love_note TEXT,
    hobbies TEXT,
    date_of_birth TEXT,
    residing_address TEXT,
    personal_email TEXT,
    gender TEXT,
    nationality TEXT,
    marital_status TEXT,
    bank_account_number TEXT,
    bank_name TEXT,
    ifsc_code TEXT,
    pan_no TEXT,
    uan_no TEXT,
    emp_code TEXT,
    date_of_joining TEXT
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    skill_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    issuing_body TEXT,
    date_earned TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    check_in TEXT,
    check_out TEXT,
    work_hours REAL,
    status TEXT DEFAULT 'present',
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    leave_type TEXT CHECK(leave_type IN ('paid','sick','unpaid')) NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days REAL NOT NULL,
    remarks TEXT,
    status TEXT CHECK(status IN ('pending','approved','rejected')) DEFAULT 'pending',
    admin_comment TEXT
);

CREATE TABLE IF NOT EXISTS leave_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    leave_type TEXT NOT NULL,
    days_available REAL NOT NULL,
    UNIQUE(user_id, leave_type)
);

CREATE TABLE IF NOT EXISTS salary_structure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    monthly_wage REAL DEFAULT 0,
    basic_pct REAL DEFAULT 50,
    hra_pct REAL DEFAULT 50,
    standard_allowance REAL DEFAULT 4167,
    performance_bonus_pct REAL DEFAULT 8.33,
    lta_pct REAL DEFAULT 8.33,
    professional_tax REAL DEFAULT 200,
    pf_employee_pct REAL DEFAULT 12,
    pf_employer_pct REAL DEFAULT 12
);

CREATE TABLE IF NOT EXISTS company (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    logo_path TEXT
);

CREATE TABLE IF NOT EXISTS user_presence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    last_seen TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    otp TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    assigned_to INTEGER NOT NULL,
    assigned_by INTEGER NOT NULL,
    due_date TEXT,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    proof_links TEXT,
    proof_images TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    if conn.execute("SELECT COUNT(*) c FROM company").fetchone()["c"] == 0:
        conn.execute("INSERT INTO company (name, logo_path) VALUES (?, ?)", ("Your Company", None))
        conn.commit()
    write_credentials_file(conn)
    conn.close()


def write_credentials_file(conn, password_map=None):
    if password_map is None:
        password_map = {}
    rows = conn.execute("SELECT login_id, name, role FROM users ORDER BY id").fetchall()
    lines = [
        "HRMS Login Credentials",
        "Generated automatically by the app",
        "",
    ]
    for row in rows:
        login_id = row["login_id"]
        name = row["name"]
        role = row["role"]
        password = password_map.get(login_id)
        if password is None:
            if role == "admin":
                password = "admin123"
            else:
                password = "employee123"
        lines.append(f"{role} | {name} | {login_id} | {password}")
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def prune_presence(conn, minutes=5):
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE user_presence SET is_active = 0 WHERE is_active = 1 AND last_seen < ?", (cutoff,))


def mark_user_presence(conn, user_id, is_active=True):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = conn.execute("SELECT id FROM user_presence WHERE user_id = ?", (user_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE user_presence SET last_seen = ?, is_active = ? WHERE user_id = ?",
            (now, 1 if is_active else 0, user_id),
        )
    else:
        conn.execute(
            "INSERT INTO user_presence (user_id, last_seen, is_active) VALUES (?, ?, ?)",
            (user_id, now, 1 if is_active else 0),
        )


def get_online_employee_ids(conn, minutes=5):
    prune_presence(conn, minutes=minutes)
    rows = conn.execute(
        "SELECT user_id FROM user_presence WHERE is_active = 1 AND user_id IN (SELECT id FROM users WHERE role='employee')"
    ).fetchall()
    return {row["user_id"] for row in rows}


def generate_login_id(conn, first_name, last_name, year):
    prefix = "OI"
    fn = (first_name[:2] if first_name else "XX").upper().ljust(2, "X")
    ln = (last_name[:2] if last_name else "XX").upper().ljust(2, "X")
    like_pattern = f"{prefix}{fn}{ln}{year}%"
    rows = conn.execute(
        "SELECT login_id FROM users WHERE login_id LIKE ?", (like_pattern,)
    ).fetchall()
    serial = len(rows) + 1
    return f"{prefix}{fn}{ln}{year}{serial:04d}"


def generate_recent_team_history(conn, days=7, start_date=None):
    if start_date is None:
        start_date = date.today() - timedelta(days=days - 1)

    employees = conn.execute("SELECT id FROM users WHERE role='employee'").fetchall()
    attendance_created = 0
    leave_created = 0

    for employee in employees:
        uid = employee["id"]
        for offset in range(days):
            current_date = start_date + timedelta(days=offset)
            current_date_str = current_date.isoformat()
            exists = conn.execute(
                "SELECT id FROM attendance WHERE user_id=? AND date=?",
                (uid, current_date_str),
            ).fetchone()
            if exists:
                continue

            if current_date.weekday() >= 5:
                status = "present"
                check_in = None
                check_out = None
                work_hours = None
            else:
                roll = random.randint(1, 100)
                if roll <= 12:
                    status = "absent"
                    check_in = None
                    check_out = None
                    work_hours = None
                elif roll <= 22:
                    status = "leave"
                    check_in = None
                    check_out = None
                    work_hours = None
                else:
                    status = "present"
                    start_hour = 9 + random.randint(0, 1)
                    start_min = random.choice([0, 15, 30, 45])
                    end_hour = start_hour + 8 + random.randint(0, 1)
                    end_min = random.choice([0, 15, 30, 45])
                    check_in = f"{start_hour:02d}:{start_min:02d}"
                    check_out = f"{end_hour:02d}:{end_min:02d}"
                    try:
                        delta = (
                            datetime.strptime(check_out, "%H:%M") - datetime.strptime(check_in, "%H:%M")
                        ).total_seconds() / 3600
                        work_hours = round(delta, 2)
                    except ValueError:
                        work_hours = None

            conn.execute(
                "INSERT INTO attendance (user_id, date, check_in, check_out, work_hours, status) VALUES (?,?,?,?,?,?)",
                (uid, current_date_str, check_in, check_out, work_hours, status),
            )
            attendance_created += 1

            if status == "leave":
                existing_leave = conn.execute(
                    "SELECT id FROM leave_requests WHERE user_id=? AND start_date=? AND end_date=?",
                    (uid, current_date_str, current_date_str),
                ).fetchone()
                if not existing_leave:
                    conn.execute(
                        "INSERT INTO leave_requests (user_id, leave_type, start_date, end_date, days, remarks, status, admin_comment) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            uid,
                            random.choice(("paid", "sick", "unpaid")),
                            current_date_str,
                            current_date_str,
                            1,
                            "Auto-generated demo record",
                            "approved",
                            "Generated automatically",
                        ),
                    )
                    leave_created += 1

    return {"attendance": attendance_created, "leave_requests": leave_created}


def seed_demo_data():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    if existing > 0:
        write_credentials_file(conn)
        conn.close()
        return
    year = date.today().year
    admin_login = generate_login_id(conn, "Admin", "User", year)
    password_map = {admin_login: "admin123"}
    conn.execute(
        """INSERT INTO users (login_id, name, email, phone, password_hash, must_change_password,
           role, department, job_position, manager, company, location, date_of_joining, emp_code)
           VALUES (?,?,?,?,?,0,?,?,?,?,?,?,?,?)""",
        (admin_login, "Admin User", "admin@company.com", "9000000000",
         generate_password_hash("admin123"), "admin", "Administration", "HR Manager",
         "-", "Your Company", "Head Office", date.today().isoformat(), "EMP0001"),
    )
    demo_employees = [
        ("Riya", "Sharma", "Engineering", "Software Engineer"),
        ("Arjun", "Verma", "Sales", "Sales Executive"),
        ("Neha", "Kapoor", "Design", "UI/UX Designer"),
    ]
    for fn, ln, dept, job in demo_employees:
        login_id = generate_login_id(conn, fn, ln, year)
        password_map[login_id] = "employee123"
        cur = conn.execute(
            """INSERT INTO users (login_id, name, email, phone, password_hash, must_change_password,
               role, department, job_position, manager, company, location, date_of_joining, emp_code)
               VALUES (?,?,?,?,?,0,?,?,?,?,?,?,?,?)""",
            (login_id, f"{fn} {ln}", f"{fn.lower()}.{ln.lower()}@company.com", "9000000001",
             generate_password_hash("employee123"), "employee", dept, job,
             "Admin User", "Your Company", "Head Office", date.today().isoformat(),
             f"EMP{login_id[-4:]}"),
        )
        uid = cur.lastrowid
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)",
                     (uid, "paid", 24))
        conn.execute("INSERT INTO leave_allocations (user_id, leave_type, days_available) VALUES (?,?,?)",
                     (uid, "sick", 7))
        conn.execute("INSERT INTO salary_structure (user_id, monthly_wage) VALUES (?, ?)", (uid, 50000))
    generate_recent_team_history(conn, days=7)
    write_credentials_file(conn, password_map)
    conn.commit()
    conn.close()
