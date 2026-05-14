-- ============================================================
--  Supabase SQL — Full Schema
--  Run in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- ── 1. USERS table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
    email       TEXT        PRIMARY KEY,          -- unique login key
    name        TEXT        NOT NULL,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on users"
    ON public.users FOR ALL USING (true) WITH CHECK (true);


-- ── 2. SLOTS table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.slots (
    id          BIGSERIAL   PRIMARY KEY,
    date        DATE        NOT NULL,
    time_slot   TIME        NOT NULL,
    is_booked   BOOLEAN     NOT NULL DEFAULT FALSE,
    booked_by   TEXT,                             -- display name
    user_email  TEXT REFERENCES public.users(email) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT slots_date_time_unique UNIQUE (date, time_slot)
);

-- If slots table already exists, just add the user_email column:
-- ALTER TABLE public.slots ADD COLUMN IF NOT EXISTS
--     user_email TEXT REFERENCES public.users(email) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_slots_date       ON public.slots (date);
CREATE INDEX IF NOT EXISTS idx_slots_is_booked  ON public.slots (is_booked);
CREATE INDEX IF NOT EXISTS idx_slots_user_email ON public.slots (user_email);

ALTER TABLE public.slots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on slots"
    ON public.slots FOR ALL USING (true) WITH CHECK (true);
