-- ============================================================================
-- ScholarAI — Supabase (Postgres) schema migration
-- Run this in the Supabase SQL Editor (Project > SQL Editor > New query)
-- before setting DB_BACKEND=supabase in .env.
--
-- This mirrors backend/db.py's SQLite schema field-for-field so the two
-- backends behave identically from the application's point of view.
-- ============================================================================

create table if not exists users (
    id bigint generated always as identity primary key,
    full_name text not null,
    email text unique not null,
    mobile text,
    password_hash text not null,
    role text not null default 'student' check (role in ('student','admin')),
    is_active boolean not null default true,
    reset_token text,
    reset_token_expires timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists profiles (
    user_id bigint primary key references users(id) on delete cascade,
    dob date,
    gender text,
    address text,
    state text,
    district text,
    pincode text,
    college_name text,
    university text,
    course text,
    branch text,
    year_of_study text,
    semester text,
    cgpa numeric,
    annual_family_income numeric,
    category text,
    minority_status text,
    disability_status text,
    sports_quota text,
    skills text,
    achievements text,
    updated_at timestamptz not null default now()
);

create table if not exists scholarships (
    id bigint generated always as identity primary key,
    name text not null,
    provider text not null,
    description text,
    scholarship_type text,
    amount numeric,
    state text,
    course text,
    branch text,
    category text,
    min_cgpa numeric default 0,
    max_family_income numeric,
    gender_criteria text default 'Any',
    min_age integer,
    max_age integer,
    required_documents text,
    application_start date,
    application_deadline date,
    official_website text,
    application_link text,
    status text not null default 'Published' check (status in ('Published','Unpublished')),
    is_sample boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists saved_scholarships (
    id bigint generated always as identity primary key,
    user_id bigint not null references users(id) on delete cascade,
    scholarship_id bigint not null references scholarships(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique(user_id, scholarship_id)
);

create table if not exists applications (
    id bigint generated always as identity primary key,
    reference_id text unique not null,
    user_id bigint not null references users(id) on delete cascade,
    scholarship_id bigint not null references scholarships(id) on delete cascade,
    status text not null default 'Draft'
        check (status in ('Draft','Submitted','Under Review','Approved','Rejected','Cancelled')),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(user_id, scholarship_id)
);

create table if not exists application_documents (
    id bigint generated always as identity primary key,
    user_id bigint not null references users(id) on delete cascade,
    doc_type text not null,
    file_name text not null,
    stored_name text not null,
    status text not null default 'Uploaded'
        check (status in ('Missing','Uploaded','Pending Verification','Verified','Rejected')),
    reject_reason text,
    uploaded_at timestamptz not null default now()
);

create table if not exists notifications (
    id bigint generated always as identity primary key,
    user_id bigint references users(id) on delete cascade, -- null = broadcast
    title text not null,
    message text not null,
    type text not null default 'General',
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists chatbot_conversations (
    id bigint generated always as identity primary key,
    user_id bigint not null references users(id) on delete cascade,
    created_at timestamptz not null default now()
);

create table if not exists chatbot_messages (
    id bigint generated always as identity primary key,
    conversation_id bigint not null references chatbot_conversations(id) on delete cascade,
    sender text not null check (sender in ('user','bot')),
    message text not null,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- Row Level Security
--
-- The Flask backend talks to Supabase using the SERVICE ROLE key (server-side
-- only, never exposed to the browser), which bypasses RLS by design — the
-- app itself enforces "students can only see their own data" in app.py's
-- session-based auth checks. These policies are defined anyway so that if
-- this schema is ever also queried directly with the ANON key (e.g. a future
-- client-side Supabase integration), the same rules apply at the database
-- level as a defense-in-depth measure.
-- ============================================================================

alter table users enable row level security;
alter table profiles enable row level security;
alter table scholarships enable row level security;
alter table saved_scholarships enable row level security;
alter table applications enable row level security;
alter table application_documents enable row level security;
alter table notifications enable row level security;
alter table chatbot_conversations enable row level security;
alter table chatbot_messages enable row level security;

-- Public/anon: can read published scholarships only
create policy "Published scholarships are publicly readable" on scholarships
    for select using (status = 'Published');

-- Authenticated users (via Supabase auth.uid() if adopted later) can only
-- access rows tied to their own user_id
create policy "Users can view their own profile" on profiles
    for select using (auth.uid()::text = user_id::text);
create policy "Users can update their own profile" on profiles
    for update using (auth.uid()::text = user_id::text);

create policy "Users can view their own saved scholarships" on saved_scholarships
    for all using (auth.uid()::text = user_id::text);

create policy "Users can view their own applications" on applications
    for all using (auth.uid()::text = user_id::text);

create policy "Users can view their own documents" on application_documents
    for all using (auth.uid()::text = user_id::text);

create policy "Users can view their own notifications" on notifications
    for select using (auth.uid()::text = user_id::text or user_id is null);

create policy "Users can view their own chatbot conversations" on chatbot_conversations
    for all using (auth.uid()::text = user_id::text);

-- Note: the service-role key used by the Flask backend bypasses all of the
-- above automatically; these policies matter only for direct anon/authenticated
-- client access, which this app does not currently use.

-- ============================================================================
-- RPC function backing GET /api/admin/stats (aggregate analytics)
-- PostgREST can't express GROUP BY directly, so the aggregation lives here.
-- ============================================================================
create or replace function admin_dashboard_stats()
returns json
language plpgsql
security definer
as $$
declare
    result json;
begin
    select json_build_object(
        'total_students', (select count(*) from users where role = 'student'),
        'total_scholarships', (select count(*) from scholarships),
        'total_applications', (select count(*) from applications),
        'pending_applications', (select count(*) from applications where status in ('Submitted','Under Review')),
        'approved_applications', (select count(*) from applications where status = 'Approved'),
        'rejected_applications', (select count(*) from applications where status = 'Rejected'),
        'monthly_applications', (
            select coalesce(json_agg(row_to_json(t)), '[]'::json) from (
                select to_char(created_at, 'YYYY-MM') as month, count(*) as c
                from applications group by month order by month
            ) t
        ),
        'scholarship_popularity', (
            select coalesce(json_agg(row_to_json(t)), '[]'::json) from (
                select s.name, count(a.id) as c
                from scholarships s left join applications a on a.scholarship_id = s.id
                group by s.id, s.name order by c desc limit 8
            ) t
        ),
        'by_category', (
            select coalesce(json_agg(row_to_json(t)), '[]'::json) from (
                select coalesce(p.category, 'Unspecified') as category, count(*) as c
                from applications a join profiles p on p.user_id = a.user_id
                group by p.category
            ) t
        ),
        'by_state', (
            select coalesce(json_agg(row_to_json(t)), '[]'::json) from (
                select coalesce(p.state, 'Unspecified') as state, count(*) as c
                from applications a join profiles p on p.user_id = a.user_id
                group by p.state
            ) t
        ),
        'status_distribution', (
            select coalesce(json_agg(row_to_json(t)), '[]'::json) from (
                select status, count(*) as c from applications group by status
            ) t
        )
    ) into result;
    return result;
end;
$$;

-- ============================================================================
-- Seed data (mirrors backend/db.py's seed_data — admin + demo student +
-- 10 sample scholarships). Password hashes below are Werkzeug
-- generate_password_hash() output for 'admin123' and 'student123' respectively
-- using the scrypt method — the Flask app's check_password_hash() call
-- verifies these directly, so demo logins work identically on Supabase.
-- Regenerate these if you change the passwords.
-- ============================================================================
-- NOTE: Because Werkzeug's scrypt hashes embed a random salt, copy the exact
-- hash your own `python3 -c "from werkzeug.security import generate_password_hash;
-- print(generate_password_hash('admin123'))"` produces rather than reusing a
-- hash generated elsewhere. Insert seed rows via the Supabase table editor or
-- a short one-off Python script using backend/repo_supabase.py's SupabaseRepo,
-- which is simpler than hand-writing INSERTs with correct password hashes here.
