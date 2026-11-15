"""
Centralized configuration. All secrets/config come from environment
variables (loaded from a local .env file via python-dotenv). Nothing here
should ever be hardcoded in source control.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # loads backend/.env if present; real env vars always take precedence


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # -------- Core --------
    SECRET_KEY = os.environ.get("SECRET_KEY")  # required in production; app.py falls back to a random key with a warning if unset
    ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = _bool("FLASK_DEBUG", False)

    # -------- Database backend --------
    # "sqlite" (default, zero-config, used for local dev/demo) or "supabase"
    DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite").strip().lower()
    SQLITE_PATH = os.environ.get("SQLITE_PATH")  # optional override; db.py has its own default

    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

    # -------- AI (multi-provider: Gemini -> OpenRouter -> Groq -> rule-based) --------
    # AI_PROVIDER picks which provider is tried FIRST: "gemini", "openrouter",
    # "groq", or "auto" (tries Gemini -> OpenRouter -> Groq in that fixed
    # order; also the behavior when AI_PROVIDER is left blank). Whatever is
    # tried first, on failure (e.g. Gemini's 429 RESOURCE_EXHAUSTED quota
    # error, a timeout, a network error, an invalid key, or any 5xx) the app
    # automatically falls through the remaining CONFIGURED providers in
    # fixed priority order, and only uses the rule-based engine if every
    # configured provider fails. A provider with no API key set is skipped,
    # not attempted.
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "").strip().lower()

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

    # Backward compatibility: older .env files set only GEMINI_API_KEY (and
    # maybe USE_GEMINI) with no AI_PROVIDER at all. If AI_PROVIDER is unset,
    # default it to "gemini" whenever a Gemini key is present (matching the
    # previous auto-activation behavior), else leave it unset (rule-based).
    # USE_GEMINI=false is still honored as an explicit "skip Gemini" override.
    _use_gemini_env = os.environ.get("USE_GEMINI")
    _gemini_explicitly_disabled = _use_gemini_env is not None and not _bool("USE_GEMINI", False)
    if not AI_PROVIDER:
        AI_PROVIDER = "gemini" if (GEMINI_API_KEY and not _gemini_explicitly_disabled) else ""

    # True if at least one real AI provider is configured (used for the
    # startup log / dashboard "engine" default expectations).
    AI_CONFIGURED = bool(
        (GEMINI_API_KEY and not _gemini_explicitly_disabled) or OPENROUTER_API_KEY or GROQ_API_KEY
    )
    # Kept for any code/tests still referencing the old flag name.
    USE_GEMINI = bool(GEMINI_API_KEY) and not _gemini_explicitly_disabled

    # -------- Email (SMTP) for forgot/reset password --------
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5050")
    # Real email is only attempted when SMTP_HOST/USER/PASSWORD are all set;
    # otherwise the app falls back to returning the reset token directly in
    # the API response (current dev-mode behavior), so nothing breaks
    # when email isn't configured.
    EMAIL_CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)

    # -------- File storage --------
    # "local" (default, current behavior: backend/uploads/) or "supabase"
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "documents")

    # -------- Logging --------
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.environ.get("LOG_DIR", "logs")

    # -------- Session security --------
    # Secure requires HTTPS — browsers (and curl) will silently refuse to send
    # a Secure-flagged cookie back over plain HTTP, which would break local
    # dev/testing on http://localhost. Default False here; set true in any
    # real HTTPS deployment.
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "60") or 60)

    # -------- Rate limiting --------
    RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", True)


config = Config()
