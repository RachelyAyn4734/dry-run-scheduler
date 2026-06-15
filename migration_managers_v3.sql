-- ============================================================
--  Scoped Manager Notifications — Migration v3
--  Apply on top of schema_grandma.sql + migration_grandma_v2.sql.
--  Run once in: Supabase Dashboard → SQL Editor → New Query
--
--  Introduces a scalable manager model:
--    managers             — global people (identity, edited once)
--    manager_assignments  — which service/entity each manager covers
--
--  visit_managers is LEFT UNTOUCHED for rollback safety.
--  Application code stops reading it only after this migration is verified.
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- SECTION 1: managers (global people)
-- ════════════════════════════════════════════════════════════
-- A manager is a person. Name/email are stored once and reused
-- across every service/entity they manage. email is stored
-- lowercased by the app (matching normalize_email) and is UNIQUE.

CREATE TABLE IF NOT EXISTS public.managers (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    email      TEXT        NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,   -- global kill-switch for the person
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT managers_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_managers_is_active ON public.managers (is_active);

ALTER TABLE public.managers ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'managers' AND policyname = 'Allow all on managers'
    ) THEN
        -- Permissive policy matches the existing project convention: the app uses
        -- the anon key for both admin and visitor flows. Write-path security is
        -- provided by the app-level admin password.
        CREATE POLICY "Allow all on managers"
            ON public.managers FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;


-- ════════════════════════════════════════════════════════════
-- SECTION 2: manager_assignments (scope)
-- ════════════════════════════════════════════════════════════
-- Each row says "this manager covers this service (and entity)".
--   service_type = 'dry_run' → entity_id IS NULL      (one global Dry Run scope)
--   service_type = 'grandma' → entity_id = grandmas.id (one scope per grandma)
--
-- entity_id is intentionally polymorphic (no FK): it points to a different
-- table per service_type. Referential integrity for grandma assignments is
-- enforced in the app layer (only real grandmas are offered) plus the
-- ON DELETE CASCADE from managers. The CHECK constraint below guarantees the
-- service_type/entity_id shape is always valid.

CREATE TABLE IF NOT EXISTS public.manager_assignments (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    manager_id   UUID        NOT NULL REFERENCES public.managers(id) ON DELETE CASCADE,
    service_type TEXT        NOT NULL CHECK (service_type IN ('dry_run', 'grandma')),
    entity_id    UUID,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Scope-shape integrity (clarification #1):
    --   dry_run must NOT carry an entity_id; grandma MUST carry one.
    CONSTRAINT chk_ma_scope_shape CHECK (
        (service_type = 'dry_run' AND entity_id IS NULL)
        OR
        (service_type = 'grandma' AND entity_id IS NOT NULL)
    )
);

ALTER TABLE public.manager_assignments ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'manager_assignments' AND policyname = 'Allow all on manager_assignments'
    ) THEN
        CREATE POLICY "Allow all on manager_assignments"
            ON public.manager_assignments FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- Uniqueness: a manager cannot hold the same scope twice.
-- Two partial indexes are required because Postgres treats NULL entity_id
-- values as distinct, so a single UNIQUE(manager_id, service_type, entity_id)
-- would not prevent duplicate dry_run rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ma_scope_entity
    ON public.manager_assignments (manager_id, service_type, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ma_scope_global
    ON public.manager_assignments (manager_id, service_type)
    WHERE entity_id IS NULL;

-- Recipient-resolution lookup path.
CREATE INDEX IF NOT EXISTS idx_ma_lookup
    ON public.manager_assignments (service_type, entity_id, is_active);

CREATE INDEX IF NOT EXISTS idx_ma_manager
    ON public.manager_assignments (manager_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 3: Data migration — copy existing managers
-- ════════════════════════════════════════════════════════════
-- Copy every existing visit_managers row into the new managers table.
-- Emails are lowercased to match the app's normalize_email convention.
-- No emails are hardcoded — everything is read dynamically.
-- Idempotent: re-running skips already-copied emails.

INSERT INTO public.managers (name, email, is_active, created_at)
SELECT vm.name, LOWER(vm.email), vm.is_active, vm.created_at
FROM public.visit_managers vm
ON CONFLICT (email) DO NOTHING;


-- ════════════════════════════════════════════════════════════
-- SECTION 4: Preserve current behavior — seed grandma assignments
-- ════════════════════════════════════════════════════════════
-- Today every active manager is notified for every grandma (global list).
-- To keep behavior identical on day one, assign each active existing
-- manager to EVERY active grandma. Admins can later narrow these.
--
-- No dry_run assignments are seeded — none existed before. Admins add
-- Dry Run managers via the new UI after deploy.

INSERT INTO public.manager_assignments (manager_id, service_type, entity_id, is_active)
SELECT m.id, 'grandma', g.id, TRUE
FROM public.managers m
JOIN public.visit_managers vm
    ON LOWER(vm.email) = m.email AND vm.is_active = TRUE
CROSS JOIN public.grandmas g
WHERE g.is_active = TRUE
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════
-- SECTION 5: Verification queries (optional — run manually)
-- ════════════════════════════════════════════════════════════
-- Confirm counts before trusting the migration:
--
--   SELECT COUNT(*) FROM public.managers;
--   SELECT COUNT(*) FROM public.visit_managers WHERE is_active = TRUE;
--     -> managers count should be >= active visit_managers count
--
--   SELECT m.name, m.email, COUNT(a.id) AS grandma_assignments
--   FROM public.managers m
--   LEFT JOIN public.manager_assignments a
--          ON a.manager_id = m.id AND a.service_type = 'grandma'
--   GROUP BY m.id, m.name, m.email
--   ORDER BY m.name;
