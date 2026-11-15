"""
SQLite implementation of the data repository. This mirrors the exact SQL
that previously lived inline in app.py — no query logic was changed, only
moved here behind named methods so app.py can transparently switch to
SupabaseRepo when DB_BACKEND=supabase.

Every method uses `with db_connection() as conn:` instead of manual
get_db()/conn.close() pairs. This guarantees the connection is ALWAYS
closed — including when a query raises (e.g. a FOREIGN KEY or UNIQUE
constraint violation) — which was previously NOT guaranteed: an exception
between get_db() and conn.close() skipped the close() entirely, leaking
the connection while it could still be holding a lock, until Python's
garbage collector eventually reaped it. That leak was a direct, real cause
of both intermittent "database is locked" errors under load and of
unhandled 500s for simple bad-input cases like an invalid scholarship_id.
"""
import uuid

from db import get_db, db_connection, init_db as _init_db


def _d(row):
    return dict(row) if row is not None else None


def _dl(rows):
    return [dict(r) for r in rows]


class SQLiteRepo:
    name = "sqlite"

    def init(self):
        _init_db()

    # ---------------- users / auth ----------------
    def get_user_by_email(self, email):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            return _d(row)

    def get_user_by_id(self, user_id):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            return _d(row)

    def create_user(self, full_name, email, mobile, password_hash, role="student"):
        with db_connection() as conn:
            cur = conn.execute(
                "INSERT INTO users (full_name, email, mobile, password_hash, role) VALUES (?,?,?,?,?)",
                (full_name, email, mobile, password_hash, role),
            )
            user_id = cur.lastrowid
            conn.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
            conn.commit()
            return user_id

    def update_user_basic(self, user_id, full_name=None, mobile=None):
        with db_connection() as conn:
            if full_name:
                conn.execute("UPDATE users SET full_name=? WHERE id=?", (full_name, user_id))
            if mobile:
                conn.execute("UPDATE users SET mobile=? WHERE id=?", (mobile, user_id))
            conn.commit()

    def update_user_active(self, user_id, is_active):
        with db_connection() as conn:
            conn.execute("UPDATE users SET is_active=? WHERE id=? AND role='student'", (1 if is_active else 0, user_id))
            conn.commit()

    def set_reset_token(self, user_id, token, expires_iso):
        with db_connection() as conn:
            conn.execute("UPDATE users SET reset_token=?, reset_token_expires=? WHERE id=?", (token, expires_iso, user_id))
            conn.commit()

    def get_user_by_reset_token(self, token):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE reset_token=?", (token,)).fetchone()
            return _d(row)

    def reset_password_with_token(self, user_id, password_hash):
        with db_connection() as conn:
            conn.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_token_expires=NULL WHERE id=?",
                         (password_hash, user_id))
            conn.commit()

    # ---------------- profile ----------------
    def get_profile(self, user_id):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
            return _d(row)

    def update_profile(self, user_id, updates):
        if not updates:
            return self.get_profile(user_id)
        with db_connection() as conn:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [user_id]
            conn.execute(f"UPDATE profiles SET {set_clause}, updated_at=datetime('now') WHERE user_id=?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
            return _d(row)

    # ---------------- scholarships ----------------
    def list_scholarships(self, args):
        """`args` is a dict-like of query params: q, type, state, course, branch,
        category, min_amount, max_amount, max_income, sort."""
        where = ["status='Published'"]
        params = []
        if args.get("q"):
            where.append("(LOWER(name) LIKE ? OR LOWER(provider) LIKE ?)")
            q = f"%{args.get('q').lower()}%"
            params += [q, q]
        if args.get("type") and args.get("type") != "All":
            where.append("scholarship_type=?")
            params.append(args.get("type"))
        if args.get("state") and args.get("state") != "All":
            where.append("(state=? OR state='All')")
            params.append(args.get("state"))
        if args.get("course") and args.get("course") != "All":
            where.append("(course=? OR course='All')")
            params.append(args.get("course"))
        if args.get("branch") and args.get("branch") != "All":
            where.append("(branch=? OR branch='All')")
            params.append(args.get("branch"))
        if args.get("category") and args.get("category") != "All":
            where.append("(category=? OR category='All')")
            params.append(args.get("category"))
        if args.get("min_amount"):
            where.append("amount >= ?")
            params.append(float(args.get("min_amount")))
        if args.get("max_amount"):
            where.append("amount <= ?")
            params.append(float(args.get("max_amount")))
        if args.get("max_income"):
            where.append("(max_family_income IS NULL OR max_family_income >= ?)")
            params.append(float(args.get("max_income")))
        where_sql = " AND ".join(where)

        sort = args.get("sort", "relevance")
        order_sql = "created_at DESC"
        if sort == "deadline":
            order_sql = "application_deadline ASC"
        elif sort == "amount":
            order_sql = "amount DESC"

        with db_connection() as conn:
            rows = conn.execute(f"SELECT * FROM scholarships WHERE {where_sql} ORDER BY {order_sql}", params).fetchall()
            return _dl(rows)

    def list_published_scholarships(self):
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM scholarships WHERE status='Published'").fetchall()
            return _dl(rows)

    def get_scholarship(self, sid):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM scholarships WHERE id=?", (sid,)).fetchone()
            return _d(row)

    def list_scholarships_by_ids(self, ids):
        if not ids:
            return []
        with db_connection() as conn:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(f"SELECT * FROM scholarships WHERE id IN ({placeholders})", ids).fetchall()
            return _dl(rows)

    def list_all_scholarships_admin(self, page=None, per_page=10):
        with db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) c FROM scholarships").fetchone()["c"]
            query = "SELECT * FROM scholarships ORDER BY created_at DESC"
            if page is not None:
                offset = (page - 1) * per_page
                rows = conn.execute(query + " LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
            items = _dl(rows)
            if page is not None:
                return {"items": items, "total": total, "page": page, "per_page": per_page,
                        "total_pages": max(1, (total + per_page - 1) // per_page)}
            return items

    def create_scholarship(self, values):
        with db_connection() as conn:
            cols = ", ".join(values.keys())
            placeholders = ", ".join("?" * len(values))
            cur = conn.execute(f"INSERT INTO scholarships ({cols}, is_sample) VALUES ({placeholders}, 0)", list(values.values()))
            sid = cur.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM scholarships WHERE id=?", (sid,)).fetchone()
            return _d(row)

    def update_scholarship(self, sid, updates):
        with db_connection() as conn:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE scholarships SET {set_clause} WHERE id=?", list(updates.values()) + [sid])
            conn.commit()
            row = conn.execute("SELECT * FROM scholarships WHERE id=?", (sid,)).fetchone()
            return _d(row)

    def delete_scholarship(self, sid):
        with db_connection() as conn:
            conn.execute("DELETE FROM scholarships WHERE id=?", (sid,))
            conn.commit()

    # ---------------- saved ----------------
    def list_saved(self, user_id):
        with db_connection() as conn:
            rows = conn.execute("""
                SELECT s.* FROM saved_scholarships sv JOIN scholarships s ON s.id = sv.scholarship_id
                WHERE sv.user_id=? ORDER BY sv.created_at DESC
            """, (user_id,)).fetchall()
            return _dl(rows)

    def save_scholarship(self, user_id, sid):
        """Returns True if saved, False if the scholarship doesn't exist
        (FOREIGN KEY violation) or was already saved (UNIQUE violation).
        Both are legitimate non-error outcomes from the caller's point of
        view, but the caller can now tell "did nothing happen" apart from
        "actually saved", which the old silent except:pass could not."""
        with db_connection() as conn:
            try:
                conn.execute("INSERT INTO saved_scholarships (user_id, scholarship_id) VALUES (?,?)", (user_id, sid))
                conn.commit()
                return True
            except Exception:
                return False

    def unsave_scholarship(self, user_id, sid):
        with db_connection() as conn:
            conn.execute("DELETE FROM saved_scholarships WHERE user_id=? AND scholarship_id=?", (user_id, sid))
            conn.commit()

    # ---------------- applications ----------------
    def list_applications(self, user_id):
        with db_connection() as conn:
            rows = conn.execute("""
                SELECT a.*, s.name as scholarship_name, s.provider, s.amount, s.application_deadline
                FROM applications a JOIN scholarships s ON s.id = a.scholarship_id
                WHERE a.user_id=? ORDER BY a.created_at DESC
            """, (user_id,)).fetchall()
            return _dl(rows)

    def get_application_by_user_scholarship(self, user_id, sid):
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM applications WHERE user_id=? AND scholarship_id=?", (user_id, sid)).fetchone()
            return _d(row)

    def create_application(self, user_id, sid):
        ref = "APP-" + uuid.uuid4().hex[:10].upper()
        with db_connection() as conn:
            conn.execute("INSERT INTO applications (reference_id, user_id, scholarship_id, status) VALUES (?,?,?,'Draft')",
                         (ref, user_id, sid))
            conn.commit()
            row = conn.execute("SELECT * FROM applications WHERE reference_id=?", (ref,)).fetchone()
            return _d(row)

    def get_application(self, aid, user_id=None):
        with db_connection() as conn:
            if user_id is not None:
                row = conn.execute("SELECT * FROM applications WHERE id=? AND user_id=?", (aid, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
            return _d(row)

    def update_application(self, aid, status=None, notes=None):
        with db_connection() as conn:
            fields, params = [], []
            if status:
                fields.append("status=?")
                params.append(status)
            if notes is not None:
                fields.append("notes=?")
                params.append(notes)
            fields.append("updated_at=datetime('now')")
            params.append(aid)
            conn.execute(f"UPDATE applications SET {', '.join(fields)} WHERE id=?", params)
            conn.commit()
            row = conn.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
            return _d(row)

    def list_all_applications_admin(self, status=None, page=None, per_page=10):
        with db_connection() as conn:
            where = ""
            params = []
            if status:
                where = " WHERE a.status=?"
                params.append(status)
            count_query = f"""
                SELECT COUNT(*) c FROM applications a JOIN scholarships s ON s.id = a.scholarship_id
                JOIN users u ON u.id = a.user_id{where}
            """
            total = conn.execute(count_query, params).fetchone()["c"]
            query = f"""
                SELECT a.*, s.name as scholarship_name, u.full_name as student_name, u.email as student_email
                FROM applications a JOIN scholarships s ON s.id = a.scholarship_id JOIN users u ON u.id = a.user_id
                {where} ORDER BY a.created_at DESC
            """
            if page is not None:
                offset = (page - 1) * per_page
                rows = conn.execute(query + " LIMIT ? OFFSET ?", params + [per_page, offset]).fetchall()
            else:
                rows = conn.execute(query, params).fetchall()
            items = _dl(rows)
            if page is not None:
                return {"items": items, "total": total, "page": page, "per_page": per_page,
                        "total_pages": max(1, (total + per_page - 1) // per_page)}
            return items

    # ---------------- documents ----------------
    def list_documents(self, user_id):
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM application_documents WHERE user_id=? ORDER BY uploaded_at DESC", (user_id,)).fetchall()
            return _dl(rows)

    def create_document_record(self, user_id, doc_type, file_name, stored_name):
        with db_connection() as conn:
            conn.execute("""INSERT INTO application_documents (user_id, doc_type, file_name, stored_name, status)
                             VALUES (?,?,?,?, 'Uploaded')""", (user_id, doc_type, file_name, stored_name))
            conn.commit()
            row = conn.execute("SELECT * FROM application_documents WHERE stored_name=?", (stored_name,)).fetchone()
            return _d(row)

    def get_document(self, did, user_id=None):
        with db_connection() as conn:
            if user_id is not None:
                row = conn.execute("SELECT * FROM application_documents WHERE id=? AND user_id=?", (did, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM application_documents WHERE id=?", (did,)).fetchone()
            return _d(row)

    def delete_document_record(self, did):
        with db_connection() as conn:
            conn.execute("DELETE FROM application_documents WHERE id=?", (did,))
            conn.commit()

    def list_all_documents_admin(self, page=None, per_page=10):
        with db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) c FROM application_documents").fetchone()["c"]
            query = """
                SELECT d.*, u.full_name as student_name, u.email as student_email
                FROM application_documents d JOIN users u ON u.id = d.user_id ORDER BY d.uploaded_at DESC
            """
            if page is not None:
                offset = (page - 1) * per_page
                rows = conn.execute(query + " LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
            items = _dl(rows)
            if page is not None:
                return {"items": items, "total": total, "page": page, "per_page": per_page,
                        "total_pages": max(1, (total + per_page - 1) // per_page)}
            return items

    def update_document_status_admin(self, did, status, reject_reason=None):
        with db_connection() as conn:
            conn.execute("UPDATE application_documents SET status=?, reject_reason=? WHERE id=?",
                         (status, reject_reason if status == "Rejected" else None, did))
            conn.commit()

    # ---------------- notifications ----------------
    def list_notifications(self, user_id, limit=50):
        with db_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM notifications WHERE user_id=? OR user_id IS NULL ORDER BY created_at DESC LIMIT ?
            """, (user_id, limit)).fetchall()
            return _dl(rows)

    def create_notification(self, user_id, title, message, ntype):
        with db_connection() as conn:
            conn.execute("INSERT INTO notifications (user_id, title, message, type) VALUES (?,?,?,?)",
                         (user_id, title, message, ntype))
            conn.commit()

    def mark_notification_read(self, nid, user_id):
        with db_connection() as conn:
            conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND (user_id=? OR user_id IS NULL)", (nid, user_id))
            conn.commit()

    def mark_all_notifications_read(self, user_id):
        with db_connection() as conn:
            conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=? OR user_id IS NULL", (user_id,))
            conn.commit()

    def count_unread_notifications(self, user_id):
        with db_connection() as conn:
            row = conn.execute("SELECT COUNT(*) c FROM notifications WHERE (user_id=? OR user_id IS NULL) AND is_read=0",
                                (user_id,)).fetchone()
            return row["c"]

    # ---------------- calendar ----------------
    def list_calendar_scholarships(self):
        with db_connection() as conn:
            rows = conn.execute("SELECT id, name, application_start, application_deadline FROM scholarships WHERE status='Published'").fetchall()
            return _dl(rows)

    # ---------------- chatbot ----------------
    def get_or_create_conversation(self, user_id):
        with db_connection() as conn:
            conv = conn.execute("SELECT * FROM chatbot_conversations WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
            if conv:
                return conv["id"]
            cur = conn.execute("INSERT INTO chatbot_conversations (user_id) VALUES (?)", (user_id,))
            conv_id = cur.lastrowid
            conn.commit()
            return conv_id

    def add_chat_message(self, conversation_id, sender, message):
        with db_connection() as conn:
            conn.execute("INSERT INTO chatbot_messages (conversation_id, sender, message) VALUES (?,?,?)",
                         (conversation_id, sender, message))
            conn.commit()

    def get_chat_history(self, user_id):
        with db_connection() as conn:
            conv = conn.execute("SELECT * FROM chatbot_conversations WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
            if not conv:
                return []
            rows = conn.execute("SELECT * FROM chatbot_messages WHERE conversation_id=? ORDER BY created_at ASC", (conv["id"],)).fetchall()
            return _dl(rows)

    def clear_chat_history(self, user_id):
        with db_connection() as conn:
            conn.execute("DELETE FROM chatbot_conversations WHERE user_id=?", (user_id,))
            conn.commit()

    # ---------------- admin: students ----------------
    def list_students(self, q="", page=None, per_page=10):
        with db_connection() as conn:
            where = "role='student' AND (LOWER(full_name) LIKE ? OR LOWER(email) LIKE ?)"
            params = (f"%{q.lower()}%", f"%{q.lower()}%")
            total = conn.execute(f"SELECT COUNT(*) c FROM users WHERE {where}", params).fetchone()["c"]
            query = f"""
                SELECT id, full_name, email, mobile, is_active, created_at FROM users
                WHERE {where} ORDER BY created_at DESC
            """
            if page is not None:
                offset = (page - 1) * per_page
                rows = conn.execute(query + " LIMIT ? OFFSET ?", params + (per_page, offset)).fetchall()
            else:
                rows = conn.execute(query, params).fetchall()
            items = _dl(rows)
            if page is not None:
                return {"items": items, "total": total, "page": page, "per_page": per_page,
                        "total_pages": max(1, (total + per_page - 1) // per_page)}
            return items

    def get_student_detail(self, uid):
        with db_connection() as conn:
            user = conn.execute("SELECT id, full_name, email, mobile, is_active, created_at FROM users WHERE id=? AND role='student'", (uid,)).fetchone()
            if not user:
                return None
            profile = conn.execute("SELECT * FROM profiles WHERE user_id=?", (uid,)).fetchone()
            applications = conn.execute("""
                SELECT a.*, s.name as scholarship_name FROM applications a JOIN scholarships s ON s.id = a.scholarship_id WHERE a.user_id=?
            """, (uid,)).fetchall()
            result = dict(user)
            result["profile"] = _d(profile)
            result["applications"] = _dl(applications)
            return result

    # ---------------- admin: stats ----------------
    def get_admin_stats(self):
        with db_connection() as conn:
            total_students = conn.execute("SELECT COUNT(*) c FROM users WHERE role='student'").fetchone()["c"]
            total_scholarships = conn.execute("SELECT COUNT(*) c FROM scholarships").fetchone()["c"]
            total_applications = conn.execute("SELECT COUNT(*) c FROM applications").fetchone()["c"]
            pending = conn.execute("SELECT COUNT(*) c FROM applications WHERE status IN ('Submitted','Under Review')").fetchone()["c"]
            approved = conn.execute("SELECT COUNT(*) c FROM applications WHERE status='Approved'").fetchone()["c"]
            rejected = conn.execute("SELECT COUNT(*) c FROM applications WHERE status='Rejected'").fetchone()["c"]
            monthly = conn.execute("""
                SELECT strftime('%Y-%m', created_at) as month, COUNT(*) c FROM applications GROUP BY month ORDER BY month
            """).fetchall()
            popularity = conn.execute("""
                SELECT s.name, COUNT(a.id) c FROM scholarships s LEFT JOIN applications a ON a.scholarship_id = s.id
                GROUP BY s.id ORDER BY c DESC LIMIT 8
            """).fetchall()
            by_category = conn.execute("""
                SELECT COALESCE(p.category, 'Unspecified') category, COUNT(*) c
                FROM applications a JOIN profiles p ON p.user_id = a.user_id GROUP BY p.category
            """).fetchall()
            by_state = conn.execute("""
                SELECT COALESCE(p.state, 'Unspecified') state, COUNT(*) c
                FROM applications a JOIN profiles p ON p.user_id = a.user_id GROUP BY p.state
            """).fetchall()
            status_dist = conn.execute("SELECT status, COUNT(*) c FROM applications GROUP BY status").fetchall()
            return {
                "total_students": total_students, "total_scholarships": total_scholarships,
                "total_applications": total_applications, "pending_applications": pending,
                "approved_applications": approved, "rejected_applications": rejected,
                "monthly_applications": _dl(monthly), "scholarship_popularity": _dl(popularity),
                "by_category": _dl(by_category), "by_state": _dl(by_state), "status_distribution": _dl(status_dist),
            }
