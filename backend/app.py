import logging
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, send_from_directory, send_file

from werkzeug.security import generate_password_hash, check_password_hash

from config import config
from logging_config import setup_logging
from repo import get_repo
import ai_engine
import email_service
import storage
import reports
import security
from engine import evaluate, recommend_scholarships

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=None)

if not config.SECRET_KEY:
    logging.getLogger("scholarai").warning(
        "SECRET_KEY is not set in .env — using a randomly generated key for this "
        "process only. Sessions will not survive a restart. Set SECRET_KEY in "
        "production so sessions remain valid across deploys/restarts."
    )
app.secret_key = config.SECRET_KEY or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = storage.MAX_FILE_SIZE + 1024 * 1024

# Secure session cookies + idle timeout. SESSION_REFRESH_EACH_REQUEST (Flask
# default: True) means the expiry slides forward on each request, so this is
# an idle/inactivity timeout rather than a fixed time-since-login timeout.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_SAMESITE"] = config.SESSION_COOKIE_SAMESITE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)

logger = setup_logging(app)
repo = get_repo()

ai_status = ai_engine.active_provider_summary()

logger.info(f"ScholarAI backend started. DB backend={repo.name}, "
            f"AI engine={ai_status}, "
            f"Email={'smtp' if config.EMAIL_CONFIGURED else 'dev-mode token fallback'}, "
            f"Storage={config.STORAGE_BACKEND}, "
            f"SessionTimeout={config.SESSION_TIMEOUT_MINUTES}min, "
            f"RateLimit={'on' if config.RATE_LIMIT_ENABLED else 'off'}")


@app.before_request
def _csrf_check():
    result = security.csrf_protect()
    if result is not None:
        return result


# ---------------------------------------------------------------- errors --
@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.errorhandler(400)
def handle_400(e):
    return jsonify({"error": getattr(e, "description", "Bad request")}), 400


@app.errorhandler(413)
def handle_413(e):
    return jsonify({"error": "Uploaded file is too large"}), 413


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    logger.exception(f"Unhandled exception on {request.method} {request.path}: {e}")
    return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


# ---------------------------------------------------------------- helpers --
def profile_completion(profile):
    if not profile:
        return 0
    fields = ["dob", "gender", "address", "state", "district", "pincode", "college_name",
              "university", "course", "branch", "year_of_study", "semester", "cgpa",
              "annual_family_income", "category", "minority_status", "disability_status",
              "sports_quota", "skills", "achievements"]
    filled = sum(1 for f in fields if profile.get(f) not in (None, ""))
    return round((filled / len(fields)) * 100)


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = session.get("user_id")
            if not uid:
                return jsonify({"error": "Authentication required"}), 401
            if role and session.get("role") != role:
                return jsonify({"error": "Forbidden: insufficient permissions"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user_id():
    return session.get("user_id")


def get_pagination_args():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 10))
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(1, min(per_page, 100))  # cap to prevent abuse
    return page, per_page


# --------------------------------------------------------------- frontend --
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def frontend_files(path):
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    full = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ------------------------------------------------------------------- auth --
@app.post("/api/auth/register")
@security.rate_limit(max_requests=20, window_seconds=300)
def register():
    data = request.get_json(force=True)
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    mobile = (data.get("mobile") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm_password") or ""

    if not full_name or not email or not mobile or not password:
        return jsonify({"error": "All fields are required"}), 400
    if "@" not in email or "." not in email:
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    if repo.get_user_by_email(email):
        return jsonify({"error": "An account with this email already exists"}), 409

    user_id = repo.create_user(full_name, email, mobile, generate_password_hash(password), role="student")
    repo.create_notification(user_id, "Welcome to the Scholarship Portal",
                              "Complete your profile to unlock personalized AI-powered scholarship recommendations.",
                              "Announcement")
    logger.info(f"New student registered: {email} (id={user_id})")

    session.permanent = True
    session["user_id"] = user_id
    session["role"] = "student"
    session["full_name"] = full_name
    csrf_token = security.issue_csrf_token()
    return jsonify({"message": "Registration successful", "csrf_token": csrf_token, "user": {
        "id": user_id, "full_name": full_name, "email": email, "role": "student"
    }})


@app.post("/api/auth/login")
@security.rate_limit(max_requests=20, window_seconds=300)
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    expected_role = data.get("role")

    user = repo.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        logger.info(f"Failed login attempt for {email}")
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.get("is_active", True):
        return jsonify({"error": "This account has been deactivated. Contact support."}), 403
    if expected_role and user["role"] != expected_role:
        return jsonify({"error": f"This account is not registered as {expected_role}"}), 403

    session.permanent = True
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["full_name"] = user["full_name"]
    csrf_token = security.issue_csrf_token()
    logger.info(f"Login: {email} (role={user['role']})")
    return jsonify({"message": "Login successful", "csrf_token": csrf_token, "user": {
        "id": user["id"], "full_name": user["full_name"], "email": user["email"], "role": user["role"]
    }})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.get("/api/auth/me")
def me():
    uid = current_user_id()
    if not uid:
        return jsonify({"user": None})
    user = repo.get_user_by_id(uid)
    if not user:
        session.clear()
        return jsonify({"user": None})
    csrf_token = security.get_csrf_token() or security.issue_csrf_token()
    return jsonify({"user": {k: user[k] for k in ("id", "full_name", "email", "mobile", "role")},
                     "csrf_token": csrf_token})


@app.post("/api/auth/forgot-password")
@security.rate_limit(max_requests=5, window_seconds=300)
def forgot_password():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    user = repo.get_user_by_email(email)
    if not user:
        # Do not reveal whether the email exists
        return jsonify({"message": "If that email exists, a reset link/token has been generated."})

    token = secrets.token_urlsafe(24)
    expires = (datetime.now() + timedelta(hours=1)).isoformat()
    repo.set_reset_token(user["id"], token, expires)

    sent, err = email_service.send_reset_email(user["email"], user["full_name"], token)
    if sent:
        logger.info(f"Password reset email sent to {email}")
        return jsonify({"message": "A password reset link has been sent to your email."})

    if err == "not_configured":
        # Dev-mode fallback — unchanged from before, so local/demo use keeps working
        return jsonify({"message": "Reset token generated (demo mode - no email service configured).",
                         "demo_reset_token": token})

    # SMTP was configured but sending failed — surface it rather than silently
    # falling back, since a configured-but-broken mail server needs attention.
    logger.error(f"Configured SMTP failed to send reset email to {email}: {err}")
    return jsonify({"error": "Could not send the reset email right now. Please try again shortly."}), 502


@app.post("/api/auth/reset-password")
@security.rate_limit(max_requests=10, window_seconds=300)
def reset_password():
    data = request.get_json(force=True)
    token = data.get("token")
    new_password = data.get("password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    user = repo.get_user_by_reset_token(token)
    if not user or not user.get("reset_token_expires") or \
            datetime.fromisoformat(str(user["reset_token_expires"]).replace("Z", "+00:00")).replace(tzinfo=None) < datetime.now():
        return jsonify({"error": "Reset token is invalid or has expired"}), 400
    repo.reset_password_with_token(user["id"], generate_password_hash(new_password))
    logger.info(f"Password reset completed for user id={user['id']}")
    return jsonify({"message": "Password has been reset. You can now log in."})


# --------------------------------------------------------------- profile --
@app.get("/api/profile")
@login_required()
def get_profile():
    user = repo.get_user_by_id(current_user_id())
    profile = repo.get_profile(current_user_id())
    result = {k: user[k] for k in ("id", "full_name", "email", "mobile", "role", "created_at")}
    result["profile"] = profile
    result["profile_completion"] = profile_completion(profile)
    return jsonify(result)


PROFILE_FIELDS = ["dob", "gender", "address", "state", "district", "pincode", "college_name",
                   "university", "course", "branch", "year_of_study", "semester", "cgpa",
                   "annual_family_income", "category", "minority_status", "disability_status",
                   "sports_quota", "skills", "achievements"]


@app.put("/api/profile")
@login_required()
def update_profile():
    data = request.get_json(force=True)
    full_name = data.get("full_name")
    mobile = data.get("mobile")
    if full_name or mobile:
        repo.update_user_basic(current_user_id(), full_name=full_name or None, mobile=mobile or None)
        if full_name:
            session["full_name"] = full_name

    updates = {k: data.get(k) for k in PROFILE_FIELDS if k in data}
    for k in ("cgpa", "annual_family_income"):
        if k in updates and updates[k] not in (None, ""):
            try:
                updates[k] = float(updates[k])
            except (TypeError, ValueError):
                updates[k] = None
    profile = repo.update_profile(current_user_id(), updates)
    return jsonify({"message": "Profile updated", "profile": profile,
                     "profile_completion": profile_completion(profile)})


# ---------------------------------------------------------- scholarships --
@app.get("/api/scholarships")
def list_scholarships():
    return jsonify(repo.list_scholarships(request.args))


@app.get("/api/scholarships/<int:sid>")
def get_scholarship(sid):
    row = repo.get_scholarship(sid)
    if not row:
        return jsonify({"error": "Scholarship not found"}), 404
    return jsonify(row)


@app.get("/api/scholarships/<int:sid>/eligibility")
@login_required()
def check_eligibility(sid):
    sch = repo.get_scholarship(sid)
    profile = repo.get_profile(current_user_id())
    if not sch:
        return jsonify({"error": "Scholarship not found"}), 404
    result = evaluate(profile, sch)
    result["scholarship"] = sch
    return jsonify(result)


@app.post("/api/compare")
def compare_scholarships():
    data = request.get_json(force=True)
    ids = data.get("ids", [])[:3]
    if not ids:
        return jsonify([])
    rows = repo.list_scholarships_by_ids(ids)
    profile = repo.get_profile(current_user_id()) if current_user_id() else None
    out = []
    for r in rows:
        item = dict(r)
        if profile:
            ev = evaluate(profile, r)
            item["eligibility"] = ev["eligibility"]
            item["score"] = ev["score"]
        out.append(item)
    return jsonify(out)


# -------------------------------------------------------- recommendations --
@app.get("/api/recommendations")
@login_required()
def recommendations():
    profile = repo.get_profile(current_user_id())
    scholarships = repo.list_published_scholarships()
    result = ai_engine.get_recommendations(profile, scholarships, limit=10)
    out = []
    for r in result["recommendations"]:
        out.append({
            "scholarship": r["scholarship"], "score": r["score"], "eligibility": r["eligibility"],
            "matched": r["matched"], "missing": r["missing"],
            "missing_profile_fields": r["missing_profile_fields"], "why": r["why"],
        })
    return jsonify({"engine": result["engine"], "recommendations": out})


# ---------------------------------------------------------------- saved --
@app.get("/api/saved")
@login_required()
def list_saved():
    return jsonify(repo.list_saved(current_user_id()))


@app.post("/api/saved/<int:sid>")
@login_required()
def save_scholarship(sid):
    if not repo.get_scholarship(sid):
        return jsonify({"error": "Scholarship not found"}), 404
    repo.save_scholarship(current_user_id(), sid)
    return jsonify({"message": "Saved"})


@app.delete("/api/saved/<int:sid>")
@login_required()
def unsave_scholarship(sid):
    repo.unsave_scholarship(current_user_id(), sid)
    return jsonify({"message": "Removed"})


# ----------------------------------------------------------- applications --
@app.get("/api/applications")
@login_required()
def list_applications():
    return jsonify(repo.list_applications(current_user_id()))


@app.post("/api/applications")
@login_required()
def start_application():
    data = request.get_json(force=True)
    sid = data.get("scholarship_id")
    if not repo.get_scholarship(sid):
        return jsonify({"error": "Scholarship not found"}), 404
    existing = repo.get_application_by_user_scholarship(current_user_id(), sid)
    if existing:
        return jsonify({"error": "You have already started or submitted an application for this scholarship",
                         "application": existing}), 409
    app_row = repo.create_application(current_user_id(), sid)
    logger.info(f"Application started: user={current_user_id()} scholarship={sid} ref={app_row['reference_id']}")
    return jsonify({"message": "Application started as draft", "application": app_row})


@app.put("/api/applications/<int:aid>")
@login_required()
def update_application(aid):
    data = request.get_json(force=True)
    app_row = repo.get_application(aid, user_id=current_user_id())
    if not app_row:
        return jsonify({"error": "Application not found"}), 404

    new_status = data.get("status")
    notes = data.get("notes")
    if new_status == "Submitted" and app_row["status"] not in ("Draft",):
        return jsonify({"error": "Only draft applications can be submitted"}), 400
    if new_status == "Cancelled" and app_row["status"] in ("Approved", "Rejected"):
        return jsonify({"error": "Cannot cancel a finalized application"}), 400

    updated = repo.update_application(aid, status=new_status, notes=notes)

    if new_status == "Submitted":
        sch = repo.get_scholarship(app_row["scholarship_id"])
        repo.create_notification(current_user_id(), "Application Submitted",
                                  f"Your application for {sch['name']} has been submitted successfully.",
                                  "Application Submitted")
        logger.info(f"Application submitted: id={aid} user={current_user_id()}")
    return jsonify({"message": "Application updated", "application": updated})


# --------------------------------------------------------------- documents --
@app.get("/api/documents")
@login_required()
def list_documents():
    return jsonify(repo.list_documents(current_user_id()))


@app.post("/api/documents")
@login_required()
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    doc_type = request.form.get("doc_type", "Other")
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    file_bytes = file.read()
    try:
        saved = storage.save_document(file.filename, file_bytes)
    except storage.StorageError as e:
        return jsonify({"error": str(e)}), 400

    from werkzeug.utils import secure_filename
    row = repo.create_document_record(current_user_id(), doc_type, secure_filename(file.filename), saved["stored_name"])
    logger.info(f"Document uploaded: user={current_user_id()} type={doc_type} backend={saved['backend']}")
    return jsonify({"message": "Document uploaded", "document": row})


@app.get("/api/documents/<int:did>/file")
@login_required()
def download_document(did):
    # Admins need to view a document's actual content to verify/reject it
    # (that's the whole point of "document verification") — so admins can
    # fetch any document. Students remain restricted to their own only.
    if session.get("role") == "admin":
        row = repo.get_document(did)
    else:
        row = repo.get_document(did, user_id=current_user_id())
    if not row:
        return jsonify({"error": "Document not found"}), 404
    if config.STORAGE_BACKEND == "supabase":
        try:
            file_bytes = storage.load_document(row["stored_name"])
        except storage.StorageError as e:
            return jsonify({"error": str(e)}), 404
        import io
        return send_file(io.BytesIO(file_bytes), download_name=row["file_name"])
    return send_from_directory(storage.LOCAL_UPLOAD_DIR, row["stored_name"])


@app.delete("/api/documents/<int:did>")
@login_required()
def delete_document(did):
    row = repo.get_document(did, user_id=current_user_id())
    if row:
        storage.delete_document(row["stored_name"])
        repo.delete_document_record(did)
    return jsonify({"message": "Document deleted"})


# ------------------------------------------------------------ notifications --
@app.get("/api/notifications")
@login_required()
def list_notifications():
    return jsonify(repo.list_notifications(current_user_id()))


@app.put("/api/notifications/<int:nid>/read")
@login_required()
def mark_notification_read(nid):
    repo.mark_notification_read(nid, current_user_id())
    return jsonify({"message": "Marked as read"})


@app.put("/api/notifications/read-all")
@login_required()
def mark_all_notifications_read():
    repo.mark_all_notifications_read(current_user_id())
    return jsonify({"message": "All marked as read"})


# ----------------------------------------------------------------- calendar --
@app.get("/api/calendar")
def calendar_events():
    rows = repo.list_calendar_scholarships()
    events = []
    for r in rows:
        events.append({"scholarship_id": r["id"], "title": r["name"], "date": r["application_start"], "type": "Opening"})
        events.append({"scholarship_id": r["id"], "title": r["name"], "date": r["application_deadline"], "type": "Deadline"})
    return jsonify(events)


# ------------------------------------------------------------------ chatbot --
MAX_CHAT_MESSAGE_LENGTH = 1000


@app.post("/api/chatbot")
@login_required()
def chatbot():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
    if len(message) > MAX_CHAT_MESSAGE_LENGTH:
        return jsonify({"error": f"Message is too long (max {MAX_CHAT_MESSAGE_LENGTH} characters)"}), 400

    profile = repo.get_profile(current_user_id())
    scholarships = repo.list_published_scholarships()
    history = repo.get_chat_history(current_user_id())

    conv_id = repo.get_or_create_conversation(current_user_id())
    repo.add_chat_message(conv_id, "user", message)
    reply, engine_used = ai_engine.chat(message, profile, scholarships, history=history)
    repo.add_chat_message(conv_id, "bot", reply)
    return jsonify({"reply": reply, "engine": engine_used})


@app.get("/api/chatbot/history")
@login_required()
def chatbot_history():
    return jsonify(repo.get_chat_history(current_user_id()))


@app.delete("/api/chatbot/history")
@login_required()
def clear_chatbot_history():
    repo.clear_chat_history(current_user_id())
    return jsonify({"message": "Conversation cleared"})


# --------------------------------------------------------------- dashboard --
@app.get("/api/dashboard")
@login_required()
def dashboard():
    profile = repo.get_profile(current_user_id())
    scholarships = repo.list_published_scholarships()
    recs = recommend_scholarships(profile, scholarships, limit=5)
    eligible = [r for r in recs if r["eligibility"] == "Eligible"]
    saved_list = repo.list_saved(current_user_id())
    applications = repo.list_applications(current_user_id())[:5]
    notifications = repo.list_notifications(current_user_id(), limit=5)
    unread_count = repo.count_unread_notifications(current_user_id())

    upcoming_deadlines = sorted(
        [s for s in scholarships if s.get("application_deadline") and str(s["application_deadline"]) >= datetime.now().strftime("%Y-%m-%d")],
        key=lambda s: s["application_deadline"]
    )[:5]

    return jsonify({
        "full_name": session.get("full_name"),
        "profile_completion": profile_completion(profile),
        "recommended": [{"scholarship": r["scholarship"], "score": r["score"],
                          "eligibility": r["eligibility"], "why": r["why"]} for r in recs],
        "eligible_count": len(eligible),
        "saved_count": len(saved_list),
        "applications": applications,
        "notifications": notifications,
        "unread_notifications": unread_count,
        "upcoming_deadlines": upcoming_deadlines,
    })


# ----------------------------------------------------------------- reports --
@app.get("/api/report/pdf")
@login_required()
def generate_report():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import io

    user = repo.get_user_by_id(current_user_id())
    profile = repo.get_profile(current_user_id())
    scholarships = repo.list_published_scholarships()
    saved = repo.list_saved(current_user_id())
    applications = repo.list_applications(current_user_id())

    recs = recommend_scholarships(profile, scholarships, limit=5)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph("Scholarship Portal — Student Report", styles["Title"]), Spacer(1, 10)]

    story.append(Paragraph("Student Profile", styles["Heading2"]))
    profile_data = [
        ["Name", user["full_name"]], ["Email", user["email"]], ["Mobile", user.get("mobile") or "-"],
        ["College", (profile.get("college_name") if profile else "") or "-"],
        ["Course / Branch", f"{(profile.get('course') if profile else '') or '-'} / {(profile.get('branch') if profile else '') or '-'}"],
        ["CGPA", str(profile.get("cgpa")) if profile and profile.get("cgpa") is not None else "-"],
        ["Category", (profile.get("category") if profile else "") or "-"],
        ["State", (profile.get("state") if profile else "") or "-"],
        ["Annual Family Income", str(profile.get("annual_family_income")) if profile and profile.get("annual_family_income") is not None else "-"],
    ]
    t = Table(profile_data, colWidths=[150, 300])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    story += [t, Spacer(1, 14)]

    story.append(Paragraph("Top Recommended Scholarships (Rule-Based Engine)", styles["Heading2"]))
    rec_data = [["Scholarship", "Score", "Eligibility", "Deadline"]]
    for r in recs:
        s = r["scholarship"]
        rec_data.append([s["name"], f"{r['score']}%", r["eligibility"], s["application_deadline"]])
    t2 = Table(rec_data, colWidths=[250, 60, 100, 90])
    t2.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story += [t2, Spacer(1, 14)]

    story.append(Paragraph("Saved Scholarships", styles["Heading2"]))
    story.append(Paragraph(", ".join([s["name"] for s in saved]) or "None", styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Application Status", styles["Heading2"]))
    app_data = [["Reference ID", "Scholarship", "Status"]]
    for a in applications:
        app_data.append([a["reference_id"], a["scholarship_name"], a["status"]])
    if len(app_data) == 1:
        app_data.append(["-", "No applications yet", "-"])
    t3 = Table(app_data, colWidths=[120, 250, 100])
    t3.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story += [t3]

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                      download_name="scholarship_report.pdf")


# ================================================================= ADMIN ===
@app.get("/api/admin/stats")
@login_required("admin")
def admin_stats():
    return jsonify(repo.get_admin_stats())


@app.get("/api/admin/students")
@login_required("admin")
def admin_list_students():
    q = request.args.get("q", "")
    page, per_page = get_pagination_args()
    return jsonify(repo.list_students(q, page=page, per_page=per_page))


@app.get("/api/admin/students/<int:uid>")
@login_required("admin")
def admin_get_student(uid):
    result = repo.get_student_detail(uid)
    if not result:
        return jsonify({"error": "Student not found"}), 404
    return jsonify(result)


@app.put("/api/admin/students/<int:uid>/active")
@login_required("admin")
def admin_toggle_student(uid):
    data = request.get_json(force=True)
    repo.update_user_active(uid, bool(data.get("is_active")))
    return jsonify({"message": "Updated"})


@app.get("/api/admin/scholarships")
@login_required("admin")
def admin_list_scholarships():
    page, per_page = get_pagination_args()
    return jsonify(repo.list_all_scholarships_admin(page=page, per_page=per_page))


SCHOLARSHIP_FIELDS = ["name", "provider", "description", "scholarship_type", "amount", "state", "course",
                       "branch", "category", "min_cgpa", "max_family_income", "gender_criteria", "min_age",
                       "max_age", "required_documents", "application_start", "application_deadline",
                       "official_website", "application_link", "status"]


@app.post("/api/admin/scholarships")
@login_required("admin")
def admin_create_scholarship():
    data = request.get_json(force=True)
    if not data.get("name") or not data.get("provider"):
        return jsonify({"error": "Name and provider are required"}), 400
    # Only include fields the admin actually provided a non-null value for,
    # so omitted fields fall back to the database's own column defaults
    # (status='Published', min_cgpa=0, gender_criteria='Any') instead of
    # being explicitly inserted as NULL. Explicit `0`/`""` values are still
    # included since `is not None` — only a truly absent/null field is skipped.
    values = {f: data.get(f) for f in SCHOLARSHIP_FIELDS if data.get(f) is not None}
    values.setdefault("status", "Published")
    row = repo.create_scholarship(values)
    repo.create_notification(None, "New scholarship added", f"{values['name']} is now available. Check your eligibility!", "New Scholarship")
    logger.info(f"Admin created scholarship: {values['name']}")
    return jsonify({"message": "Scholarship created", "scholarship": row})


@app.put("/api/admin/scholarships/<int:sid>")
@login_required("admin")
def admin_update_scholarship(sid):
    data = request.get_json(force=True)
    updates = {f: data[f] for f in SCHOLARSHIP_FIELDS if f in data}
    if not updates:
        return jsonify({"error": "No fields to update"}), 400
    row = repo.update_scholarship(sid, updates)
    if not row:
        return jsonify({"error": "Scholarship not found"}), 404
    return jsonify({"message": "Scholarship updated", "scholarship": row})


@app.delete("/api/admin/scholarships/<int:sid>")
@login_required("admin")
def admin_delete_scholarship(sid):
    repo.delete_scholarship(sid)
    logger.info(f"Admin deleted scholarship id={sid}")
    return jsonify({"message": "Scholarship deleted"})


@app.get("/api/admin/applications")
@login_required("admin")
def admin_list_applications():
    status = request.args.get("status")
    page, per_page = get_pagination_args()
    return jsonify(repo.list_all_applications_admin(status, page=page, per_page=per_page))


@app.put("/api/admin/applications/<int:aid>/status")
@login_required("admin")
def admin_update_application_status(aid):
    data = request.get_json(force=True)
    new_status = data.get("status")
    valid = {"Under Review", "Approved", "Rejected"}
    if new_status not in valid:
        return jsonify({"error": f"Status must be one of {valid}"}), 400
    app_row = repo.get_application(aid)
    if not app_row:
        return jsonify({"error": "Application not found"}), 404
    repo.update_application(aid, status=new_status)
    sch = repo.get_scholarship(app_row["scholarship_id"])
    repo.create_notification(app_row["user_id"], "Application Status Updated",
                              f"Your application for {sch['name']} is now '{new_status}'.", "Status Changed")
    logger.info(f"Admin updated application id={aid} to status={new_status}")
    return jsonify({"message": "Status updated"})


@app.get("/api/admin/documents")
@login_required("admin")
def admin_list_documents():
    page, per_page = get_pagination_args()
    return jsonify(repo.list_all_documents_admin(page=page, per_page=per_page))


@app.put("/api/admin/documents/<int:did>/status")
@login_required("admin")
def admin_update_document_status(did):
    data = request.get_json(force=True)
    new_status = data.get("status")
    reason = data.get("reject_reason", "")
    valid = {"Pending Verification", "Verified", "Rejected"}
    if new_status not in valid:
        return jsonify({"error": f"Status must be one of {valid}"}), 400
    doc = repo.get_document(did)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    repo.update_document_status_admin(did, new_status, reason if new_status == "Rejected" else None)
    if new_status == "Rejected":
        repo.create_notification(doc["user_id"], "Document Rejected",
                                  f"Your {doc['doc_type']} was rejected: {reason}", "Missing Documents")
    return jsonify({"message": "Document status updated"})


@app.post("/api/admin/announcements")
@login_required("admin")
def admin_create_announcement():
    data = request.get_json(force=True)
    title = data.get("title")
    message = data.get("message")
    if not title or not message:
        return jsonify({"error": "Title and message are required"}), 400
    repo.create_notification(None, title, message, "Announcement")
    logger.info(f"Admin announcement sent: {title}")
    return jsonify({"message": "Announcement sent to all students"})


# ------------------------------------------------------------ admin reports --
@app.get("/api/admin/reports/summary")
@login_required("admin")
def admin_reports_summary():
    return jsonify({
        "students": len(repo.list_students("")),
        "scholarships": len(repo.list_all_scholarships_admin()),
        "applications": len(repo.list_all_applications_admin()),
        "documents": len(repo.list_all_documents_admin()),
    })


@app.get("/api/admin/reports/<report_type>/<fmt>")
@login_required("admin")
def admin_generate_report(report_type, fmt):
    if report_type not in reports.REPORT_TYPES:
        return jsonify({"error": f"Unknown report type. Choose from: {', '.join(reports.REPORT_TYPES)}"}), 400
    if fmt not in reports.GENERATORS:
        return jsonify({"error": f"Unknown format. Choose from: {', '.join(reports.GENERATORS)}"}), 400

    rows = reports.get_report_rows(repo, report_type)
    file_bytes = reports.GENERATORS[fmt](report_type, rows)
    filename = f"{report_type}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{reports.EXTENSIONS[fmt]}"
    logger.info(f"Admin generated {fmt} report: {report_type} ({len(rows)} records)")

    import io
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=reports.CONTENT_TYPES[fmt],
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=config.DEBUG)
