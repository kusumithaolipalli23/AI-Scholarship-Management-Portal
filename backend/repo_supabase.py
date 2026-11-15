"""
Supabase implementation of the data repository, using the PostgREST REST
API directly via `requests` (avoids needing the `supabase-py` SDK or a
Postgres wire-protocol driver, neither of which could be installed in the
sandbox this was built in — this approach has no extra dependency beyond
`requests`, which is already required).

IMPORTANT: this backend is code-complete but could NOT be tested end-to-end
against a real Supabase project from the environment this was built in
(no outbound network access, no live project). Run `supabase_schema.sql`
against your Supabase project's SQL editor first, set DB_BACKEND=supabase
plus SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env, then re-run the test
suite (see README) against your real project before relying on this in
production.
"""
import logging
import uuid
from datetime import datetime

import requests

from config import config

logger = logging.getLogger("scholarai.supabase")


class SupabaseError(Exception):
    pass


class SupabaseRepo:
    name = "supabase"

    def __init__(self):
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
            raise SupabaseError(
                "DB_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to be set in .env"
            )
        self.base = f"{config.SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

    def init(self):
        # Schema is managed via supabase_schema.sql run in the Supabase SQL
        # editor (Postgres DDL can't be executed through PostgREST), so
        # there is nothing to auto-create here. This just verifies connectivity.
        try:
            r = requests.get(f"{self.base}/users", headers=self.headers, params={"limit": 1}, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Supabase connectivity check failed: {e}")
            raise SupabaseError(
                "Could not reach Supabase REST API. Check SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "
                "and that supabase_schema.sql has been applied."
            ) from e

    def _req(self, method, path, params=None, json_body=None, headers_extra=None, prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        if headers_extra:
            headers.update(headers_extra)
        try:
            resp = requests.request(method, f"{self.base}/{path}", headers=headers,
                                     params=params, json=json_body, timeout=15)
            resp.raise_for_status()
            if resp.text:
                return resp.json()
            return None
        except requests.RequestException as e:
            logger.error(f"Supabase request failed [{method} {path}]: {e}")
            raise SupabaseError(f"Database request failed: {e}") from e

    def _count(self, path, params=None):
        """Returns the exact row count for a filtered query via PostgREST's
        count=exact Prefer header, reading the Content-Range response header
        (e.g. '0-9/42' -> 42) rather than the row set itself."""
        headers = dict(self.headers)
        headers["Prefer"] = "count=exact"
        p = dict(params or {})
        p["select"] = "id"
        p["limit"] = "1"
        try:
            resp = requests.get(f"{self.base}/{path}", headers=headers, params=p, timeout=15)
            resp.raise_for_status()
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                return int(content_range.split("/")[-1])
            return 0
        except requests.RequestException as e:
            logger.error(f"Supabase count request failed [{path}]: {e}")
            raise SupabaseError(f"Database count request failed: {e}") from e

    def _rpc(self, fn_name, params_body):
        return self._req("POST", f"rpc/{fn_name}", json_body=params_body)

    @staticmethod
    def _one(rows):
        return rows[0] if rows else None

    # ---------------- users / auth ----------------
    def get_user_by_email(self, email):
        rows = self._req("GET", "users", params={"email": f"eq.{email}", "select": "*"})
        return self._one(rows)

    def get_user_by_id(self, user_id):
        rows = self._req("GET", "users", params={"id": f"eq.{user_id}", "select": "*"})
        return self._one(rows)

    def create_user(self, full_name, email, mobile, password_hash, role="student"):
        rows = self._req("POST", "users", json_body={
            "full_name": full_name, "email": email, "mobile": mobile,
            "password_hash": password_hash, "role": role,
        }, prefer="return=representation")
        user_id = rows[0]["id"]
        self._req("POST", "profiles", json_body={"user_id": user_id}, prefer="return=representation")
        return user_id

    def update_user_basic(self, user_id, full_name=None, mobile=None):
        body = {}
        if full_name:
            body["full_name"] = full_name
        if mobile:
            body["mobile"] = mobile
        if body:
            self._req("PATCH", "users", params={"id": f"eq.{user_id}"}, json_body=body)

    def update_user_active(self, user_id, is_active):
        self._req("PATCH", "users", params={"id": f"eq.{user_id}", "role": "eq.student"},
                   json_body={"is_active": bool(is_active)})

    def set_reset_token(self, user_id, token, expires_iso):
        self._req("PATCH", "users", params={"id": f"eq.{user_id}"},
                   json_body={"reset_token": token, "reset_token_expires": expires_iso})

    def get_user_by_reset_token(self, token):
        rows = self._req("GET", "users", params={"reset_token": f"eq.{token}", "select": "*"})
        return self._one(rows)

    def reset_password_with_token(self, user_id, password_hash):
        self._req("PATCH", "users", params={"id": f"eq.{user_id}"},
                   json_body={"password_hash": password_hash, "reset_token": None, "reset_token_expires": None})

    # ---------------- profile ----------------
    def get_profile(self, user_id):
        rows = self._req("GET", "profiles", params={"user_id": f"eq.{user_id}", "select": "*"})
        return self._one(rows)

    def update_profile(self, user_id, updates):
        if updates:
            body = dict(updates)
            body["updated_at"] = datetime.now().isoformat()
            self._req("PATCH", "profiles", params={"user_id": f"eq.{user_id}"}, json_body=body)
        return self.get_profile(user_id)

    # ---------------- scholarships ----------------
    def list_scholarships(self, args):
        params = {"status": "eq.Published", "select": "*"}
        conditions = []
        if args.get("q"):
            q = args.get("q")
            conditions.append(f"or=(name.ilike.*{q}*,provider.ilike.*{q}*)")
        if args.get("type") and args.get("type") != "All":
            params["scholarship_type"] = f"eq.{args.get('type')}"
        if args.get("state") and args.get("state") != "All":
            conditions.append(f"or=(state.eq.{args.get('state')},state.eq.All)")
        if args.get("course") and args.get("course") != "All":
            conditions.append(f"or=(course.eq.{args.get('course')},course.eq.All)")
        if args.get("branch") and args.get("branch") != "All":
            conditions.append(f"or=(branch.eq.{args.get('branch')},branch.eq.All)")
        if args.get("category") and args.get("category") != "All":
            conditions.append(f"or=(category.eq.{args.get('category')},category.eq.All)")
        if args.get("min_amount"):
            params["amount"] = f"gte.{args.get('min_amount')}"
        if args.get("max_amount"):
            params["amount"] = f"lte.{args.get('max_amount')}"

        sort = args.get("sort", "relevance")
        order = "created_at.desc"
        if sort == "deadline":
            order = "application_deadline.asc"
        elif sort == "amount":
            order = "amount.desc"
        params["order"] = order

        # PostgREST allows only one `or=` group per request easily combined via `and=`;
        # for simplicity each extra OR-condition is appended as a distinct query param
        # key using PostgREST's repeated-param support.
        url_params = list(params.items())
        for i, cond in enumerate(conditions):
            key, val = cond.split("=", 1)
            url_params.append((key, val))
        return self._req("GET", "scholarships", params=url_params)

    def list_published_scholarships(self):
        return self._req("GET", "scholarships", params={"status": "eq.Published", "select": "*"})

    def get_scholarship(self, sid):
        rows = self._req("GET", "scholarships", params={"id": f"eq.{sid}", "select": "*"})
        return self._one(rows)

    def list_scholarships_by_ids(self, ids):
        if not ids:
            return []
        id_list = ",".join(str(i) for i in ids)
        return self._req("GET", "scholarships", params={"id": f"in.({id_list})", "select": "*"})

    def list_all_scholarships_admin(self, page=None, per_page=10):
        params = {"select": "*", "order": "created_at.desc"}
        if page is None:
            return self._req("GET", "scholarships", params=params)
        total = self._count("scholarships")
        params["limit"] = str(per_page)
        params["offset"] = str((page - 1) * per_page)
        items = self._req("GET", "scholarships", params=params)
        return {"items": items or [], "total": total, "page": page, "per_page": per_page,
                "total_pages": max(1, (total + per_page - 1) // per_page)}

    def create_scholarship(self, values):
        body = dict(values)
        body["is_sample"] = False
        rows = self._req("POST", "scholarships", json_body=body, prefer="return=representation")
        return self._one(rows)

    def update_scholarship(self, sid, updates):
        rows = self._req("PATCH", "scholarships", params={"id": f"eq.{sid}"}, json_body=updates,
                          prefer="return=representation")
        return self._one(rows)

    def delete_scholarship(self, sid):
        self._req("DELETE", "scholarships", params={"id": f"eq.{sid}"})

    # ---------------- saved ----------------
    def list_saved(self, user_id):
        rows = self._req("GET", "saved_scholarships", params={
            "user_id": f"eq.{user_id}", "select": "created_at,scholarships(*)", "order": "created_at.desc"
        })
        return [r["scholarships"] for r in (rows or []) if r.get("scholarships")]

    def save_scholarship(self, user_id, sid):
        try:
            self._req("POST", "saved_scholarships", json_body={"user_id": user_id, "scholarship_id": sid})
            return True
        except SupabaseError:
            return False  # likely a duplicate (unique constraint) or nonexistent scholarship (FK constraint)

    def unsave_scholarship(self, user_id, sid):
        self._req("DELETE", "saved_scholarships", params={"user_id": f"eq.{user_id}", "scholarship_id": f"eq.{sid}"})

    # ---------------- applications ----------------
    def list_applications(self, user_id):
        rows = self._req("GET", "applications", params={
            "user_id": f"eq.{user_id}", "order": "created_at.desc",
            "select": "*,scholarships(name,provider,amount,application_deadline)",
        })
        out = []
        for r in rows or []:
            s = r.pop("scholarships", {}) or {}
            r["scholarship_name"] = s.get("name")
            r["provider"] = s.get("provider")
            r["amount"] = s.get("amount")
            r["application_deadline"] = s.get("application_deadline")
            out.append(r)
        return out

    def get_application_by_user_scholarship(self, user_id, sid):
        rows = self._req("GET", "applications", params={"user_id": f"eq.{user_id}", "scholarship_id": f"eq.{sid}", "select": "*"})
        return self._one(rows)

    def create_application(self, user_id, sid):
        ref = "APP-" + uuid.uuid4().hex[:10].upper()
        rows = self._req("POST", "applications", json_body={
            "reference_id": ref, "user_id": user_id, "scholarship_id": sid, "status": "Draft"
        }, prefer="return=representation")
        return self._one(rows)

    def get_application(self, aid, user_id=None):
        params = {"id": f"eq.{aid}", "select": "*"}
        if user_id is not None:
            params["user_id"] = f"eq.{user_id}"
        rows = self._req("GET", "applications", params=params)
        return self._one(rows)

    def update_application(self, aid, status=None, notes=None):
        body = {"updated_at": datetime.now().isoformat()}
        if status:
            body["status"] = status
        if notes is not None:
            body["notes"] = notes
        rows = self._req("PATCH", "applications", params={"id": f"eq.{aid}"}, json_body=body, prefer="return=representation")
        return self._one(rows)

    def list_all_applications_admin(self, status=None, page=None, per_page=10):
        params = {"select": "*,scholarships(name),users(full_name,email)", "order": "created_at.desc"}
        count_params = {}
        if status:
            params["status"] = f"eq.{status}"
            count_params["status"] = f"eq.{status}"
        if page is not None:
            total = self._count("applications", count_params)
            params["limit"] = str(per_page)
            params["offset"] = str((page - 1) * per_page)
        rows = self._req("GET", "applications", params=params)
        out = []
        for r in rows or []:
            s = r.pop("scholarships", {}) or {}
            u = r.pop("users", {}) or {}
            r["scholarship_name"] = s.get("name")
            r["student_name"] = u.get("full_name")
            r["student_email"] = u.get("email")
            out.append(r)
        if page is not None:
            return {"items": out, "total": total, "page": page, "per_page": per_page,
                    "total_pages": max(1, (total + per_page - 1) // per_page)}
        return out

    # ---------------- documents ----------------
    def list_documents(self, user_id):
        return self._req("GET", "application_documents", params={
            "user_id": f"eq.{user_id}", "order": "uploaded_at.desc", "select": "*"
        })

    def create_document_record(self, user_id, doc_type, file_name, stored_name):
        rows = self._req("POST", "application_documents", json_body={
            "user_id": user_id, "doc_type": doc_type, "file_name": file_name,
            "stored_name": stored_name, "status": "Uploaded",
        }, prefer="return=representation")
        return self._one(rows)

    def get_document(self, did, user_id=None):
        params = {"id": f"eq.{did}", "select": "*"}
        if user_id is not None:
            params["user_id"] = f"eq.{user_id}"
        rows = self._req("GET", "application_documents", params=params)
        return self._one(rows)

    def delete_document_record(self, did):
        self._req("DELETE", "application_documents", params={"id": f"eq.{did}"})

    def list_all_documents_admin(self, page=None, per_page=10):
        params = {"select": "*,users(full_name,email)", "order": "uploaded_at.desc"}
        total = None
        if page is not None:
            total = self._count("application_documents")
            params["limit"] = str(per_page)
            params["offset"] = str((page - 1) * per_page)
        rows = self._req("GET", "application_documents", params=params)
        out = []
        for r in rows or []:
            u = r.pop("users", {}) or {}
            r["student_name"] = u.get("full_name")
            r["student_email"] = u.get("email")
            out.append(r)
        if page is not None:
            return {"items": out, "total": total, "page": page, "per_page": per_page,
                    "total_pages": max(1, (total + per_page - 1) // per_page)}
        return out

    def update_document_status_admin(self, did, status, reject_reason=None):
        self._req("PATCH", "application_documents", params={"id": f"eq.{did}"}, json_body={
            "status": status, "reject_reason": reject_reason if status == "Rejected" else None
        })

    # ---------------- notifications ----------------
    def list_notifications(self, user_id, limit=50):
        rows = self._req("GET", "notifications", params=[
            ("or", f"(user_id.eq.{user_id},user_id.is.null)"),
            ("order", "created_at.desc"), ("limit", str(limit)), ("select", "*"),
        ])
        return rows or []

    def create_notification(self, user_id, title, message, ntype):
        self._req("POST", "notifications", json_body={
            "user_id": user_id, "title": title, "message": message, "type": ntype
        })

    def mark_notification_read(self, nid, user_id):
        self._req("PATCH", "notifications", params=[
            ("id", f"eq.{nid}"), ("or", f"(user_id.eq.{user_id},user_id.is.null)")
        ], json_body={"is_read": True})

    def mark_all_notifications_read(self, user_id):
        self._req("PATCH", "notifications", params=[
            ("or", f"(user_id.eq.{user_id},user_id.is.null)")
        ], json_body={"is_read": True})

    def count_unread_notifications(self, user_id):
        rows = self._req("GET", "notifications", params=[
            ("or", f"(user_id.eq.{user_id},user_id.is.null)"), ("is_read", "eq.false"), ("select", "id"),
        ])
        return len(rows or [])

    # ---------------- calendar ----------------
    def list_calendar_scholarships(self):
        return self._req("GET", "scholarships", params={
            "status": "eq.Published", "select": "id,name,application_start,application_deadline"
        })

    # ---------------- chatbot ----------------
    def get_or_create_conversation(self, user_id):
        rows = self._req("GET", "chatbot_conversations", params={
            "user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "1"
        })
        if rows:
            return rows[0]["id"]
        created = self._req("POST", "chatbot_conversations", json_body={"user_id": user_id}, prefer="return=representation")
        return created[0]["id"]

    def add_chat_message(self, conversation_id, sender, message):
        self._req("POST", "chatbot_messages", json_body={
            "conversation_id": conversation_id, "sender": sender, "message": message
        })

    def get_chat_history(self, user_id):
        conv = self._req("GET", "chatbot_conversations", params={
            "user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "1"
        })
        if not conv:
            return []
        return self._req("GET", "chatbot_messages", params={
            "conversation_id": f"eq.{conv[0]['id']}", "order": "created_at.asc"
        })

    def clear_chat_history(self, user_id):
        self._req("DELETE", "chatbot_conversations", params={"user_id": f"eq.{user_id}"})

    # ---------------- admin: students ----------------
    def list_students(self, q="", page=None, per_page=10):
        params = [("role", "eq.student"), ("order", "created_at.desc"),
                  ("select", "id,full_name,email,mobile,is_active,created_at")]
        count_params = {"role": "eq.student"}
        if q:
            params.append(("or", f"(full_name.ilike.*{q}*,email.ilike.*{q}*)"))
            count_params["or"] = f"(full_name.ilike.*{q}*,email.ilike.*{q}*)"
        if page is None:
            return self._req("GET", "users", params=params)
        total = self._count("users", count_params)
        params.append(("limit", str(per_page)))
        params.append(("offset", str((page - 1) * per_page)))
        items = self._req("GET", "users", params=params)
        return {"items": items or [], "total": total, "page": page, "per_page": per_page,
                "total_pages": max(1, (total + per_page - 1) // per_page)}

    def get_student_detail(self, uid):
        rows = self._req("GET", "users", params={
            "id": f"eq.{uid}", "role": "eq.student",
            "select": "id,full_name,email,mobile,is_active,created_at"
        })
        user = self._one(rows)
        if not user:
            return None
        profile = self.get_profile(uid)
        apps = self._req("GET", "applications", params={
            "user_id": f"eq.{uid}", "select": "*,scholarships(name)"
        })
        applications = []
        for a in apps or []:
            s = a.pop("scholarships", {}) or {}
            a["scholarship_name"] = s.get("name")
            applications.append(a)
        user["profile"] = profile
        user["applications"] = applications
        return user

    # ---------------- admin: stats ----------------
    def get_admin_stats(self):
        """
        Aggregate stats require GROUP BY / COUNT, which plain PostgREST can't
        express directly, so this calls a Postgres RPC function
        (`admin_dashboard_stats`) defined in supabase_schema.sql. This keeps
        the aggregation logic in the database (fast, correct) rather than
        pulling every row over REST and summing in Python.
        """
        result = self._rpc("admin_dashboard_stats", {})
        return result or {
            "total_students": 0, "total_scholarships": 0, "total_applications": 0,
            "pending_applications": 0, "approved_applications": 0, "rejected_applications": 0,
            "monthly_applications": [], "scholarship_popularity": [], "by_category": [],
            "by_state": [], "status_distribution": [],
        }
