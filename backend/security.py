"""
Security helpers: a simple in-memory rate limiter and a CSRF double-submit
token scheme, both dependency-free (no flask-limiter/flask-wtf needed).

RATE LIMITING NOTE: this is an in-memory, per-process fixed-window limiter.
It resets on restart and does not coordinate across multiple worker
processes — fine for a single-process deployment (as this app runs today),
but a real multi-worker production deployment should replace this with a
shared store (e.g. Redis-backed flask-limiter) to enforce limits globally.
"""
import logging
import secrets
import time
from collections import defaultdict
from functools import wraps

from flask import request, jsonify, session

from config import config

logger = logging.getLogger("scholarai.security")

# ------------------------------------------------------------- rate limit --
_hits = defaultdict(list)  # key -> [timestamps]


def _client_key():
    # X-Forwarded-For support for when this sits behind a reverse proxy;
    # falls back to the direct remote address.
    fwd = request.headers.get("X-Forwarded-For")
    ip = fwd.split(",")[0].strip() if fwd else request.remote_addr
    return f"{ip}:{request.path}"


def rate_limit(max_requests, window_seconds):
    """Decorator: limits a route to `max_requests` per `window_seconds` per
    client IP (keyed per-route, so limits on different endpoints don't
    interfere with each other)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not config.RATE_LIMIT_ENABLED:
                return fn(*args, **kwargs)
            key = _client_key()
            now = time.time()
            hits = _hits[key]
            # drop timestamps outside the current window
            cutoff = now - window_seconds
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= max_requests:
                retry_after = int(hits[0] + window_seconds - now) + 1
                logger.warning(f"Rate limit exceeded for {key} ({len(hits)}/{max_requests})")
                resp = jsonify({"error": "Too many requests. Please try again shortly."})
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            hits.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ------------------------------------------------------------------ CSRF ---
CSRF_HEADER = "X-CSRF-Token"
CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
}


def issue_csrf_token():
    """Generates a fresh CSRF token and stores it in the session. Call this
    on login/register so the frontend can pick it up from the response."""
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token


def get_csrf_token():
    return session.get("csrf_token")


def csrf_protect():
    """Call from a before_request hook. Returns a Flask response (403) if
    the request fails CSRF validation, or None if it's fine to proceed.
    Only state-changing methods on session-authenticated /api/ routes are
    checked; GET/HEAD/OPTIONS are always safe, and login/register/password
    routes are exempt since no session/token exists yet at that point."""
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return None
    if not request.path.startswith("/api/"):
        return None
    if request.path in CSRF_EXEMPT_PATHS:
        return None
    if "user_id" not in session:
        # Not logged in — login_required() on the route will reject this
        # with a clean 401 anyway, no need for CSRF to also weigh in here.
        return None

    expected = session.get("csrf_token")
    provided = request.headers.get(CSRF_HEADER)
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        logger.warning(f"CSRF validation failed for {request.method} {request.path}")
        return jsonify({"error": "CSRF token missing or invalid. Please refresh and try again."}), 403
    return None
