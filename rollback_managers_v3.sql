-- ============================================================
--  Rollback for migration_managers_v3.sql
--  Run only if you need to fully revert the scoped-manager model.
--
--  Safe because visit_managers was never modified by v3 — dropping
--  the new tables + reverting the application code restores the
--  previous global-manager behavior completely.
-- ============================================================

DROP TABLE IF EXISTS public.manager_assignments;
DROP TABLE IF EXISTS public.managers;

-- visit_managers is intentionally NOT touched here — it still holds the
-- original global manager list and is the source of truth after rollback.
