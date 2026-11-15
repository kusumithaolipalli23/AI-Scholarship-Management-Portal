# Project memory

## Product intent & audience

- Scholarship platform with login, scholarship database/search, AI chatbot, and document uploads.
- Audience likely students seeking scholarships (inferred from features).

## Brand personality & voice

- Not yet inferred from context.

## Visual design & UX direction

- Web app with separate frontend and backend; frontend pages load independently of backend.
- No specific aesthetic, color, typography, or layout details inferred yet.

## Decisions, constraints & rationale

- Backend is Python (Flask); frontend is a separate layer.
- A Vercel config file exists and is configured to deploy the backend.
- Bolt hosting serves only static frontend — Flask backend cannot run there, so backend-dependent features (login, database, AI chatbot, uploads) won't function on a Bolt-published link.
- Vercel identified as a better deployment target for full-stack functionality (frontend + Flask + database).
- Alternative path: restructure frontend to work on Bolt hosting with Supabase replacing the Flask backend.

## Open questions & assumptions

- Database technology is unconfirmed; Supabase has been proposed as a possible backend replacement but not yet chosen.
- User has not indicated a preferred deployment path (Vercel full-stack vs. Bolt + Supabase restructure).
- No details yet on specific frontend framework, styling system, or chatbot implementation.