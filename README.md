# ScholarAI — AI-Powered Student Scholarship Management Portal

A full-stack scholarship discovery, eligibility, application, and management
platform with a Student Portal and a separate Admin Panel.

## Tech Stack
- **Backend:** Python (Flask) — REST API, session-based auth, file uploads, PDF/CSV/Excel generation, structured logging
- **Database:** SQLite by default (zero-config, WAL mode, hardened against lock contention), or Supabase (Postgres via REST) — one env var switch
- **Frontend:** Vanilla HTML/CSS/JS single-page app (no build step, no external CDN dependency) — unchanged across all backend hardening work
- **AI:** Multi-provider (Gemini, OpenRouter, Groq) with automatic priority-ordered failover and a transparent rule-based engine as the final fallback
- **Email:** Real SMTP for password reset, with dev-mode fallback when unconfigured
- **File storage:** Local disk (hardened with magic-byte validation) or Supabase Storage
- **Security:** CSRF protection, rate limiting, secure/SameSite session cookies, session idle-timeout, parameterized SQL throughout

## Running the project

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # optional — the app runs fine with no .env at all (SQLite + rule-based AI)
python3 app.py
```

Open **http://localhost:5050**. With no `.env` file, this runs entirely
self-contained: SQLite, rule-based recommendations/chatbot, dev-mode
password reset, local file storage.

## AI: multi-provider with automatic failover

The recommendation "why" explanations and the chatbot are powered by
whichever AI provider succeeds first, tried in this fixed priority order:

**Gemini → OpenRouter → Groq → rule-based engine**

`AI_PROVIDER` in `.env` picks which one is tried *first*: `gemini`,
`openrouter`, `groq`, or `auto` (tries Gemini → OpenRouter → Groq, in that
order — also the default if `AI_PROVIDER` is left blank or set to an
unrecognized value, which is logged as a warning rather than failing
silently). Whichever provider is tried first, if it fails for **any**
reason — HTTP 429 / quota exceeded (e.g. Gemini's `429
RESOURCE_EXHAUSTED`), a timeout, a network error, an invalid API key, any
5xx, or a malformed/unparseable response — the app automatically falls
through the remaining **configured** providers in the order above, and
only uses the rule-based engine if every configured provider fails or none
are configured at all. A provider with no API key set is skipped, never
attempted. **The app never crashes because of an AI provider issue, and
chat history is preserved across every fallback.**

Every attempt is logged to `backend/logs/app.log` with the current
provider, the exact failure reason, a notice when switching providers, and
the final provider used with its response time, e.g.:
```
Current provider: gemini
Provider 'gemini' failed after 38.9ms — reason: HTTP 429 quota/rate-limit exceeded: ...RESOURCE_EXHAUSTED...limit: 0...
Provider switched: gemini -> openrouter
Current provider: openrouter
Final provider used: openrouter (response time: 214.3ms)
```

```bash
# .env
AI_PROVIDER=auto             # or: gemini / openrouter / groq
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...       # tried next if Gemini fails
GROQ_API_KEY=...             # tried next if OpenRouter also fails
```

You don't need all three — configure just one, two, or all three. Only
`AI_PROVIDER`'s pick plus whichever others have a key set are ever tried.

Eligibility *scoring* itself always stays rule-based/deterministic (it's a
factual criteria match, not something to let an LLM guess at) — AI
providers only generate the natural-language "why" explanation and
chatbot replies.

The chatbot API response (`{"reply": ..., "engine": ...}`) is unchanged;
`engine` now reports whichever provider actually answered (`"gemini"`,
`"openrouter"`, `"groq"`, or `"rule-based"`) instead of a Gemini-only
boolean. The frontend does not branch on this value, so this is not a UI
change.

### Backward compatibility
Older `.env` files with only `GEMINI_API_KEY` (± `USE_GEMINI`) still work
unchanged — `AI_PROVIDER` defaults to `"gemini"` automatically when a
Gemini key is present and `AI_PROVIDER` itself is left unset.

## Database: SQLite hardening

- Every connection uses `PRAGMA journal_mode=WAL` + a 30-second busy
  timeout — the standard fix for `database is locked` under concurrent
  requests.
- Every repository method uses a `db_connection()` context manager that
  guarantees the connection is closed on every exit path, including
  exceptions — a previously-existing leak where a failed write (e.g. a
  `FOREIGN KEY constraint failed`) could leave a connection open and
  holding a lock has been eliminated.
- Routes that accept a `scholarship_id` from the client now validate it
  exists before writing, returning a clean `404` instead of a raw
  `IntegrityError`.
- Stress-tested with 15 concurrent threads performing ~60 simultaneous
  writes against shared tables: 0 errors, 0 lock failures.

## Environment variables

See `backend/.env.example` for the full list with inline documentation.
Nothing is required to run the app as described above — everything below
is opt-in.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing key (recommended for production so sessions survive restarts) |
| `DB_BACKEND` | `sqlite` (default) or `supabase` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase project credentials |
| `AI_PROVIDER` | Which AI provider to try first: `gemini` / `openrouter` / `groq` / `auto` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini credentials/model |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | OpenRouter credentials/model |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq credentials/model |
| `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/etc. | Real email sending for password reset |
| `STORAGE_BACKEND` | `local` (default) or `supabase` |
| `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `SESSION_TIMEOUT_MINUTES` | Session security |
| `RATE_LIMIT_ENABLED` | In-memory per-IP rate limiting on auth endpoints |
| `LOG_LEVEL`, `LOG_DIR` | Logging |

## Test credentials

| Role | Email | Password |
|---|---|---|
| Student | student@scholarship.test | student123 |
| Admin | admin@scholarship.test | admin123 |

## Feature summary
Auth (register/login/logout/forgot-reset password/session timeout),
student dashboard, profile, scholarship search/filters, eligibility
checker, AI recommendations, comparison, save/apply/track applications
with full status timeline and notifications, document upload/verification
with magic-byte content validation, calendar, chatbot, PDF report, admin
panel (students/scholarships/applications/documents/announcements),
admin Reports (CSV/Excel/PDF export for all 4 datasets), pagination on
all admin tables, analytics dashboard, CSRF protection, rate limiting,
secure session cookies, responsive layout (desktop/tablet/mobile).

## Known limitations
- Rate limiting is in-memory/single-process — use a shared store (e.g.
  Redis-backed) if scaling to multiple worker processes
- No malware/antivirus scanning on uploads (extension + size + magic-byte
  checks only)
- No OCR-based document verification — manual admin verify/reject by design
- Supabase backend and real AI provider calls require real network access
  and real credentials to verify in your deployment environment — the code
  paths are complete and their failure/fallback behavior is proven, but
  live success against each vendor's actual API can only be confirmed
  where genuine outbound network access exists
