import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "scholarship.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    mobile TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student', -- student | admin
    is_active INTEGER NOT NULL DEFAULT 1,
    reset_token TEXT,
    reset_token_expires TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    dob TEXT,
    gender TEXT,
    address TEXT,
    state TEXT,
    district TEXT,
    pincode TEXT,
    college_name TEXT,
    university TEXT,
    course TEXT,
    branch TEXT,
    year_of_study TEXT,
    semester TEXT,
    cgpa REAL,
    annual_family_income REAL,
    category TEXT, -- General/OBC/SC/ST/EWS etc
    minority_status TEXT, -- Yes/No
    disability_status TEXT, -- Yes/No
    sports_quota TEXT, -- Yes/No
    skills TEXT,
    achievements TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scholarships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    description TEXT,
    scholarship_type TEXT, -- Government | Private
    amount REAL,
    state TEXT, -- 'All' or specific state
    course TEXT, -- 'All' or specific
    branch TEXT, -- 'All' or specific
    category TEXT, -- 'All' or specific (General/OBC/SC/ST/EWS)
    min_cgpa REAL DEFAULT 0,
    max_family_income REAL,
    gender_criteria TEXT DEFAULT 'Any', -- Any/Male/Female/Other
    min_age INTEGER,
    max_age INTEGER,
    required_documents TEXT, -- comma separated
    application_start TEXT,
    application_deadline TEXT,
    official_website TEXT,
    application_link TEXT,
    status TEXT NOT NULL DEFAULT 'Published', -- Published | Unpublished
    is_sample INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saved_scholarships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scholarship_id INTEGER NOT NULL REFERENCES scholarships(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, scholarship_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scholarship_id INTEGER NOT NULL REFERENCES scholarships(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'Draft', -- Draft | Submitted | Under Review | Approved | Rejected | Cancelled
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, scholarship_id)
);

CREATE TABLE IF NOT EXISTS application_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_type TEXT NOT NULL, -- ID Proof, Income Certificate, etc.
    file_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Uploaded', -- Missing | Uploaded | Pending Verification | Verified | Rejected
    reject_reason TEXT,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, -- NULL = broadcast to all students
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'General', -- Deadline | Missing Documents | Application Submitted | Status Changed | New Scholarship | Announcement
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chatbot_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chatbot_conversations(id) ON DELETE CASCADE,
    sender TEXT NOT NULL, -- user | bot
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

def get_db():
    # timeout=30 makes SQLite's own busy-handler retry for up to 30s before
    # raising "database is locked", instead of Python's 5s default — this
    # buys much more headroom under concurrent writes.
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL (Write-Ahead Logging) lets readers proceed without blocking on a
    # writer (and vice versa) instead of SQLite's default rollback-journal
    # mode, which takes an exclusive lock for the whole write. This is the
    # standard fix for "database is locked" under concurrent access from a
    # multi-request web server. Idempotent/cheap to set on every connection
    # (a no-op once already enabled on the database file).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def db_connection():
    """Context manager guaranteeing the connection is ALWAYS closed, even if
    an exception (e.g. a FOREIGN KEY / UNIQUE constraint violation) is
    raised mid-transaction. A connection that's never closed on the
    exception path leaks and can keep holding a lock until Python's garbage
    collector eventually reaps it — a real, previously-existing cause of
    "database is locked" under load. Every repo_sqlite.py method now uses
    this instead of manual get_db()/conn.close() pairs."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db(seed=True):
    fresh = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    if seed and fresh:
        seed_data(conn)
    conn.close()


def seed_data(conn):
    from werkzeug.security import generate_password_hash
    cur = conn.cursor()

    # Admin account
    cur.execute(
        "INSERT INTO users (full_name, email, mobile, password_hash, role) VALUES (?,?,?,?,?)",
        ("Portal Admin", "admin@scholarship.test", "9999999999",
         generate_password_hash("admin123"), "admin")
    )

    # Demo student account
    cur.execute(
        "INSERT INTO users (full_name, email, mobile, password_hash, role) VALUES (?,?,?,?,?)",
        ("Asha Reddy", "student@scholarship.test", "9876543210",
         generate_password_hash("student123"), "student")
    )
    student_id = cur.lastrowid
    cur.execute("""
        INSERT INTO profiles (user_id, dob, gender, address, state, district, pincode,
            college_name, university, course, branch, year_of_study, semester, cgpa,
            annual_family_income, category, minority_status, disability_status, sports_quota,
            skills, achievements)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (student_id, "2004-05-14", "Female", "12-3 Lake View Colony", "Telangana", "Hyderabad", "500001",
          "Osmania University College of Engineering", "Osmania University", "B.Tech", "Computer Science",
          "3rd Year", "5th Semester", 8.6, 320000, "OBC", "No", "No", "No",
          "Python, Web Development, Public Speaking", "State-level coding hackathon winner 2025"))

    today = datetime.now()

    def d(days):
        return (today + timedelta(days=days)).strftime("%Y-%m-%d")

    scholarships = [
        dict(name="National Merit Scholarship for Engineering Students", provider="Ministry of Education (Govt. of India)",
             description="Merit-based scholarship for undergraduate engineering students from economically weaker sections, covering tuition and a monthly stipend.",
             scholarship_type="Government", amount=75000, state="All", course="B.Tech", branch="All",
             category="All", min_cgpa=7.5, max_family_income=350000, gender_criteria="Any", min_age=17, max_age=25,
             required_documents="ID Proof,Income Certificate,Marks Memo,Bonafide Certificate",
             application_start=d(-20), application_deadline=d(25),
             official_website="https://scholarships.gov.in", application_link="https://scholarships.gov.in/apply"),
        dict(name="State Minority Welfare Scholarship", provider="Telangana Minorities Welfare Department",
             description="Financial assistance for minority community students pursuing higher education within the state.",
             scholarship_type="Government", amount=40000, state="Telangana", course="All", branch="All",
             category="All", min_cgpa=6.0, max_family_income=250000, gender_criteria="Any", min_age=16, max_age=30,
             required_documents="ID Proof,Income Certificate,Bonafide Certificate",
             application_start=d(-10), application_deadline=d(15),
             official_website="https://minoritywelfare.telangana.gov.in", application_link="https://minoritywelfare.telangana.gov.in/apply"),
        dict(name="Girls in STEM Excellence Grant", provider="TechForward Foundation",
             description="Private grant encouraging female students in STEM fields with strong academic performance.",
             scholarship_type="Private", amount=60000, state="All", course="B.Tech", branch="Computer Science",
             category="All", min_cgpa=8.0, max_family_income=600000, gender_criteria="Female", min_age=17, max_age=24,
             required_documents="ID Proof,Marks Memo,Student ID",
             application_start=d(-5), application_deadline=d(40),
             official_website="https://techforward.example.org", application_link="https://techforward.example.org/apply"),
        dict(name="SC/ST Higher Education Support Scheme", provider="Social Welfare Department",
             description="Scholarship supporting SC/ST students pursuing undergraduate and postgraduate courses.",
             scholarship_type="Government", amount=55000, state="All", course="All", branch="All",
             category="SC/ST", min_cgpa=5.5, max_family_income=250000, gender_criteria="Any", min_age=16, max_age=30,
             required_documents="ID Proof,Caste Certificate,Income Certificate,Bonafide Certificate",
             application_start=d(-30), application_deadline=d(10),
             official_website="https://socialwelfare.gov.in", application_link="https://socialwelfare.gov.in/apply"),
        dict(name="Sports Achievers Scholarship", provider="Sports Authority Trust",
             description="For students under the sports quota with notable state/national level achievements.",
             scholarship_type="Private", amount=35000, state="All", course="All", branch="All",
             category="All", min_cgpa=5.0, max_family_income=800000, gender_criteria="Any", min_age=16, max_age=26,
             required_documents="ID Proof,Achievement Certificate,Bonafide Certificate",
             application_start=d(-15), application_deadline=d(60),
             official_website="https://sportstrust.example.org", application_link="https://sportstrust.example.org/apply"),
        dict(name="Differently Abled Students Support Grant", provider="Ministry of Social Justice",
             description="Financial support for differently-abled students to pursue higher education without financial burden.",
             scholarship_type="Government", amount=90000, state="All", course="All", branch="All",
             category="All", min_cgpa=5.0, max_family_income=400000, gender_criteria="Any", min_age=16, max_age=35,
             required_documents="ID Proof,Disability Certificate,Income Certificate",
             application_start=d(-8), application_deadline=d(50),
             official_website="https://socialjustice.gov.in", application_link="https://socialjustice.gov.in/apply"),
        dict(name="Computer Science Innovators Scholarship", provider="InfoNext Pvt Ltd",
             description="For high-achieving Computer Science / IT branch students showing project or research excellence.",
             scholarship_type="Private", amount=50000, state="All", course="B.Tech", branch="Computer Science",
             category="All", min_cgpa=8.5, max_family_income=1000000, gender_criteria="Any", min_age=17, max_age=24,
             required_documents="ID Proof,Marks Memo,Student ID",
             application_start=d(-2), application_deadline=d(30),
             official_website="https://infonext.example.com", application_link="https://infonext.example.com/apply"),
        dict(name="EWS Undergraduate Fee Reimbursement", provider="State Higher Education Council",
             description="Fee reimbursement scheme for Economically Weaker Section (EWS) undergraduate students.",
             scholarship_type="Government", amount=45000, state="Telangana", course="All", branch="All",
             category="EWS", min_cgpa=6.0, max_family_income=800000, gender_criteria="Any", min_age=16, max_age=28,
             required_documents="ID Proof,Income Certificate,EWS Certificate,Bonafide Certificate",
             application_start=d(-25), application_deadline=d(5),
             official_website="https://hec.telangana.gov.in", application_link="https://hec.telangana.gov.in/apply"),
        dict(name="Rural Talent Scholarship", provider="Bharat Rural Development Trust",
             description="For meritorious students from rural districts pursuing any undergraduate degree.",
             scholarship_type="Private", amount=30000, state="All", course="All", branch="All",
             category="All", min_cgpa=6.5, max_family_income=300000, gender_criteria="Any", min_age=16, max_age=25,
             required_documents="ID Proof,Income Certificate,Bonafide Certificate",
             application_start=d(-12), application_deadline=d(3),
             official_website="https://ruraldevtrust.example.org", application_link="https://ruraldevtrust.example.org/apply"),
        dict(name="Post Graduate Research Fellowship", provider="National Science & Technology Board",
             description="Fellowship for students pursuing postgraduate research in core engineering and science branches.",
             scholarship_type="Government", amount=120000, state="All", course="M.Tech", branch="All",
             category="All", min_cgpa=8.0, max_family_income=1200000, gender_criteria="Any", min_age=21, max_age=32,
             required_documents="ID Proof,Marks Memo,Research Proposal",
             application_start=d(-1), application_deadline=d(70),
             official_website="https://nstb.gov.in", application_link="https://nstb.gov.in/apply"),
    ]

    for s in scholarships:
        cur.execute("""
            INSERT INTO scholarships (name, provider, description, scholarship_type, amount, state, course,
                branch, category, min_cgpa, max_family_income, gender_criteria, min_age, max_age,
                required_documents, application_start, application_deadline, official_website,
                application_link, status, is_sample)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'Published', 1)
        """, (s["name"], s["provider"], s["description"], s["scholarship_type"], s["amount"], s["state"],
              s["course"], s["branch"], s["category"], s["min_cgpa"], s["max_family_income"],
              s["gender_criteria"], s["min_age"], s["max_age"], s["required_documents"],
              s["application_start"], s["application_deadline"], s["official_website"], s["application_link"]))

    # Welcome notification + announcement for demo student
    cur.execute("""INSERT INTO notifications (user_id, title, message, type)
                   VALUES (?, 'Welcome to the Scholarship Portal', 'Complete your profile to get personalized AI-powered scholarship recommendations.', 'Announcement')""",
                (student_id,))
    cur.execute("""INSERT INTO notifications (user_id, title, message, type)
                   VALUES (NULL, 'New scholarships added', '10 sample scholarships are now available on the portal. Explore and check your eligibility.', 'New Scholarship')""")

    conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
