-- ============================================================
--  Grandma Visits — Supabase SQL Migration
--  Run in: Supabase Dashboard → SQL Editor → New Query
--
--  Also required (via Supabase Dashboard → Storage):
--    Create bucket "grandma-visit-photos" and set it to PUBLIC
-- ============================================================

-- ── 1. DESCENDANTS table ────────────────────────────────────
-- Family members who are allowed to schedule visits.
-- `name` is the business identifier (unique, case-sensitive).
CREATE TABLE IF NOT EXISTS public.descendants (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    phone       TEXT,
    email       TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT  descendants_name_unique UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_descendants_name      ON public.descendants (name);
CREATE INDEX IF NOT EXISTS idx_descendants_is_active ON public.descendants (is_active);

ALTER TABLE public.descendants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on descendants"
    ON public.descendants FOR ALL USING (true) WITH CHECK (true);


-- ── 2. VISIT_MANAGERS table ─────────────────────────────────
-- Managers who receive email notifications for new bookings.
CREATE TABLE IF NOT EXISTS public.visit_managers (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    email       TEXT        NOT NULL UNIQUE,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_visit_managers_is_active ON public.visit_managers (is_active);

ALTER TABLE public.visit_managers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on visit_managers"
    ON public.visit_managers FOR ALL USING (true) WITH CHECK (true);


-- ── 3. VISIT_SLOTS table ────────────────────────────────────
-- Available one-hour time slots for grandma visits.
-- Slots are created by admin; marked is_available=FALSE when booked.
CREATE TABLE IF NOT EXISTS public.visit_slots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slot_start      TIMESTAMPTZ NOT NULL,
    slot_end        TIMESTAMPTZ NOT NULL,
    is_available    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT visit_slots_start_unique UNIQUE (slot_start)
);

CREATE INDEX IF NOT EXISTS idx_visit_slots_slot_start    ON public.visit_slots (slot_start);
CREATE INDEX IF NOT EXISTS idx_visit_slots_is_available  ON public.visit_slots (is_available);

ALTER TABLE public.visit_slots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on visit_slots"
    ON public.visit_slots FOR ALL USING (true) WITH CHECK (true);


-- ── 4. GRANDMA_VISITS table ─────────────────────────────────
-- Booked and completed visits.
-- slot_id links back to visit_slots for slot release on cancellation.
-- descendant_name is denormalized for display without joins.
CREATE TABLE IF NOT EXISTS public.grandma_visits (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    descendant_id   UUID        NOT NULL REFERENCES public.descendants(id),
    descendant_name TEXT        NOT NULL,
    slot_id         UUID        REFERENCES public.visit_slots(id) ON DELETE SET NULL,
    slot_start      TIMESTAMPTZ NOT NULL,
    slot_end        TIMESTAMPTZ NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'completed', 'cancelled')),
    notes           TEXT,
    photo_url       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_grandma_visits_descendant_id ON public.grandma_visits (descendant_id);
CREATE INDEX IF NOT EXISTS idx_grandma_visits_slot_start    ON public.grandma_visits (slot_start);
CREATE INDEX IF NOT EXISTS idx_grandma_visits_status        ON public.grandma_visits (status);

ALTER TABLE public.grandma_visits ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on grandma_visits"
    ON public.grandma_visits FOR ALL USING (true) WITH CHECK (true);


-- ── 5. Sample data (optional — remove before production) ────
-- INSERT INTO public.visit_managers (name, email) VALUES
--     ('מנהלת א׳', 'manager1@example.com'),
--     ('מנהל ב׳',  'manager2@example.com');

-- INSERT INTO public.descendants (name, phone) VALUES
--     ('רחל כהן',  '050-1234567'),
--     ('דוד לוי',  '052-9876543');
