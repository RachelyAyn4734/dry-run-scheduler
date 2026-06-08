-- ============================================================
--  Grandma Visits — Multi-Grandma Migration v2
--  Apply on top of schema_grandma.sql (original tables must exist).
--  Run once in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- SECTION 1: grandmas table (new)
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.grandmas (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    photo_url   TEXT,
    description TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT  grandmas_name_unique UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_grandmas_is_active ON public.grandmas (is_active);

ALTER TABLE public.grandmas ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'grandmas' AND policyname = 'Allow all on grandmas'
    ) THEN
        -- Security note: permissive policy matches the existing project convention.
        -- This is intentional: the app uses the anon key for both admin and visitor
        -- flows, so JWT-based RLS restrictions are not possible without a separate
        -- service-role client for admin. Write-path security is provided by
        -- SECURITY DEFINER RPCs and the app-level admin password.
        -- TODO (production hardening): introduce JWT auth + per-role policies.
        CREATE POLICY "Allow all on grandmas"
            ON public.grandmas FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;


-- Seed: the two grandmas.
--
-- Unicode escape syntax (U&'...') is used to avoid visual rendering ambiguity.
-- Code-block renderers display Hebrew (RTL) in LTR context as visually reversed;
-- the codepoints below are unambiguous. Verify character by character:
--
--   Name 1 — "סבתא שושי" (Savta Shoshi):
--     \05E1=ס  \05D1=ב  \05EA=ת  \05D0=א  (space)  \05E9=ש  \05D5=ו  \05E9=ש  \05D9=י
--     Read RTL: י-ש-ו-ש  א-ת-ב-ס  →  שושי סבתא  ✓
--
--   Name 2 — "סבתא אסתר" (Savta Esther):
--     \05E1=ס  \05D1=ב  \05EA=ת  \05D0=א  (space)  \05D0=א  \05E1=ס  \05EA=ת  \05E8=ר
--     Read RTL: ר-ת-ס-א  א-ת-ב-ס  →  אסתר סבתא  ✓

INSERT INTO public.grandmas (name, description) VALUES
    (
        U&'\05E1\05D1\05EA\05D0 \05E9\05D5\05E9\05D9',
        -- "סבתא שושי מחכה לביקורים עם שמחה ואהבה"
        U&'\05E1\05D1\05EA\05D0 \05E9\05D5\05E9\05D9 \05DE\05D7\05DB\05D4 \05DC\05D1\05D9\05E7\05D5\05E8\05D9\05DE \05E2\05DE \05E9\05DE\05D7\05D4 \05D5\05D0\05D4\05D1\05D4'
    ),
    (
        U&'\05E1\05D1\05EA\05D0 \05D0\05E1\05EA\05E8',
        -- "סבתא אסתר תמיד שמחה לראות את המשפחה"
        U&'\05E1\05D1\05EA\05D0 \05D0\05E1\05EA\05E8 \05EA\05DE\05D9\05D3 \05E9\05DE\05D7\05D4 \05DC\05E8\05D0\05D5\05EA \05D0\05EA \05D4\05DE\05E9\05E4\05D7\05D4'
    )
ON CONFLICT (name) DO NOTHING;


-- ════════════════════════════════════════════════════════════
-- SECTION 2: Alter visit_slots
-- ════════════════════════════════════════════════════════════

ALTER TABLE public.visit_slots
    ADD COLUMN IF NOT EXISTS grandma_id           UUID    REFERENCES public.grandmas(id),
    ADD COLUMN IF NOT EXISTS max_participants      INT     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS allows_shared_visits  BOOLEAN NOT NULL DEFAULT FALSE,
    -- is_active: admin-controlled flag. Set FALSE to close a slot regardless of capacity.
    -- Cancellation NEVER modifies this column — only admin changes it.
    ADD COLUMN IF NOT EXISTS is_active             BOOLEAN NOT NULL DEFAULT TRUE;

-- Constraints
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_vs_max_participants') THEN
        ALTER TABLE public.visit_slots
            ADD CONSTRAINT chk_vs_max_participants CHECK (max_participants >= 1);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_vs_slot_end_after_start') THEN
        ALTER TABLE public.visit_slots
            ADD CONSTRAINT chk_vs_slot_end_after_start CHECK (slot_end > slot_start);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_vs_slot_one_hour') THEN
        -- All grandma-visit slots are exactly one hour.
        -- Drop this constraint only if you intentionally introduce other durations.
        ALTER TABLE public.visit_slots
            ADD CONSTRAINT chk_vs_slot_one_hour
            CHECK (slot_end = slot_start + INTERVAL '1 hour');
    END IF;
END $$;

-- Replace time-only uniqueness with (grandma, time) pair.
-- Two grandmas can now have slots starting at the same time.
ALTER TABLE public.visit_slots
    DROP CONSTRAINT IF EXISTS visit_slots_start_unique;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'visit_slots_grandma_start_unique') THEN
        ALTER TABLE public.visit_slots
            ADD CONSTRAINT visit_slots_grandma_start_unique UNIQUE (grandma_id, slot_start);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_visit_slots_grandma_id ON public.visit_slots (grandma_id);
CREATE INDEX IF NOT EXISTS idx_visit_slots_is_active  ON public.visit_slots (is_active);


-- ════════════════════════════════════════════════════════════
-- SECTION 3: Alter grandma_visits
-- ════════════════════════════════════════════════════════════
-- Already present: slot_id, slot_start, slot_end, status,
--                  notes, photo_url, completed_at, created_at, updated_at.

ALTER TABLE public.grandma_visits
    ADD COLUMN IF NOT EXISTS grandma_id        UUID    REFERENCES public.grandmas(id),
    ADD COLUMN IF NOT EXISTS grandma_name      TEXT,
    ADD COLUMN IF NOT EXISTS participant_count INT     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS allow_joiners     BOOLEAN NOT NULL DEFAULT FALSE,
    -- actual_start / actual_end: filled by the visitor on the notes screen
    -- after the visit has ended. NULL until the visitor completes their summary.
    ADD COLUMN IF NOT EXISTS actual_start      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS actual_end        TIMESTAMPTZ;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_gv_participant_count') THEN
        ALTER TABLE public.grandma_visits
            ADD CONSTRAINT chk_gv_participant_count CHECK (participant_count >= 1);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_grandma_visits_grandma_id ON public.grandma_visits (grandma_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 4: RPC — book_visit_slot
-- ════════════════════════════════════════════════════════════
--
-- Atomically validates and books a visit slot.
-- Creates the grandma_visits record and updates visit_slots.is_available
-- inside one transaction. The slot-row FOR UPDATE lock is the sole
-- concurrency guard — concurrent bookings for the same slot serialize here.
--
-- Returns JSONB on success : { success: true, visit_id, remaining_spots }
-- Returns JSONB on failure : { success: false, reason: '<code>' }
--
-- Reason codes:
--   slot_not_found               | slot_grandma_mismatch
--   slot_closed_by_admin         | slot_not_available
--   slot_in_past                 | invalid_participant_count
--   descendant_not_found_or_inactive
--   slot_not_shareable           | slot_full
--   private_visit_exists         | slot_occupied_cannot_go_private

CREATE OR REPLACE FUNCTION public.book_visit_slot(
    p_slot_id           UUID,
    p_descendant_id     UUID,
    p_descendant_name   TEXT,
    p_grandma_id        UUID,
    p_grandma_name      TEXT,
    p_participant_count INT,
    p_allow_joiners     BOOLEAN
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_slot           RECORD;
    v_desc           RECORD;
    v_booked_count   INT;
    v_private_exists INT;
    v_new_visit_id   UUID;
    v_new_available  BOOLEAN;
BEGIN
    -- Step 1: Lock slot row.
    -- FOR UPDATE prevents any concurrent transaction from modifying this slot
    -- or committing a booking for it until this transaction ends.
    SELECT * INTO v_slot
    FROM public.visit_slots
    WHERE id = p_slot_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_not_found');
    END IF;

    -- Step 2: Grandma-slot integrity check.
    -- The slot the visitor selected must belong to the grandma they selected.
    IF v_slot.grandma_id IS DISTINCT FROM p_grandma_id THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_grandma_mismatch');
    END IF;

    -- Step 3: Admin-controlled slot gate.
    -- is_active = FALSE means admin explicitly closed this slot.
    -- Cancellations never change is_active.
    IF NOT v_slot.is_active THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_closed_by_admin');
    END IF;

    -- Step 4: Capacity cache check.
    -- is_available is auto-managed by this RPC and cancel_visit_booking.
    -- A FALSE here means the slot is full or was closed by a prior booking.
    IF NOT v_slot.is_available THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_not_available');
    END IF;

    -- Step 5: Slot must be in the future.
    IF v_slot.slot_start <= NOW() THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_in_past');
    END IF;

    -- Step 6: Participant count must be a positive integer.
    IF p_participant_count < 1 THEN
        RETURN jsonb_build_object('success', false, 'reason', 'invalid_participant_count');
    END IF;

    -- Step 7: Validate descendant exists and is active.
    SELECT * INTO v_desc
    FROM public.descendants
    WHERE id = p_descendant_id AND is_active = true;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'reason', 'descendant_not_found_or_inactive');
    END IF;

    -- Step 8: Slot-level sharing check.
    -- If the admin marked allows_shared_visits = FALSE, this slot is for one
    -- family only. Block any booking if a scheduled visit already exists.
    IF NOT v_slot.allows_shared_visits THEN
        SELECT COUNT(*) INTO v_booked_count
        FROM public.grandma_visits
        WHERE slot_id = p_slot_id AND status = 'scheduled';

        IF v_booked_count > 0 THEN
            RETURN jsonb_build_object('success', false, 'reason', 'slot_not_shareable');
        END IF;
    END IF;

    -- Step 9: Calculate current booked participant total.
    -- The slot-row lock (step 1) prevents any concurrent INSERT for this slot
    -- from committing before we do. No FOR UPDATE on this aggregate.
    SELECT COALESCE(SUM(participant_count), 0) INTO v_booked_count
    FROM public.grandma_visits
    WHERE slot_id = p_slot_id AND status = 'scheduled';

    -- Step 10: Physical capacity check.
    IF v_booked_count + p_participant_count > v_slot.max_participants THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_full');
    END IF;

    -- Step 11: Visit-level privacy check.
    -- If any existing scheduled visit in this slot set allow_joiners = FALSE,
    -- that family wants privacy — block all new bookings.
    SELECT COUNT(*) INTO v_private_exists
    FROM public.grandma_visits
    WHERE slot_id      = p_slot_id
      AND status       = 'scheduled'
      AND allow_joiners = false;

    IF v_private_exists > 0 THEN
        RETURN jsonb_build_object('success', false, 'reason', 'private_visit_exists');
    END IF;

    -- Step 12: If this visitor wants private, the slot must currently be empty.
    IF NOT p_allow_joiners AND v_booked_count > 0 THEN
        RETURN jsonb_build_object('success', false, 'reason', 'slot_occupied_cannot_go_private');
    END IF;

    -- Step 13: All checks passed — create the visit record.
    INSERT INTO public.grandma_visits (
        descendant_id,
        descendant_name,
        slot_id,
        slot_start,
        slot_end,
        grandma_id,
        grandma_name,
        participant_count,
        allow_joiners,
        status
    )
    SELECT
        p_descendant_id,
        p_descendant_name,
        p_slot_id,
        v_slot.slot_start,
        v_slot.slot_end,
        p_grandma_id,
        p_grandma_name,
        p_participant_count,
        p_allow_joiners,
        'scheduled'
    RETURNING id INTO v_new_visit_id;

    -- Step 14: Recalculate is_available after the insert and update the cache.
    -- Slot remains available only if:
    --   (a) the slot allows multiple families (allows_shared_visits = TRUE), AND
    --   (b) there is still remaining capacity.
    -- A non-shareable slot closes after its first booking even if max_participants > 1.
    SELECT COALESCE(SUM(participant_count), 0) INTO v_booked_count
    FROM public.grandma_visits
    WHERE slot_id = p_slot_id AND status = 'scheduled';

    v_new_available :=
        v_slot.allows_shared_visits
        AND (v_booked_count < v_slot.max_participants);

    UPDATE public.visit_slots
    SET is_available = v_new_available
    WHERE id = p_slot_id;

    RETURN jsonb_build_object(
        'success',         true,
        'visit_id',        v_new_visit_id,
        'remaining_spots', v_slot.max_participants - v_booked_count
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.book_visit_slot(UUID, UUID, TEXT, UUID, TEXT, INT, BOOLEAN)
    TO anon, authenticated;


-- ════════════════════════════════════════════════════════════
-- SECTION 5: RPC — cancel_visit_booking
-- ════════════════════════════════════════════════════════════
--
-- p_descendant_id:
--   Visitor path — pass the logged-in visitor's ID. Ownership is verified:
--     v_visit.descendant_id must equal p_descendant_id.
--   Admin path   — pass NULL to skip ownership check.
--
-- Reason codes: visit_not_found | already_cancelled | ownership_denied

CREATE OR REPLACE FUNCTION public.cancel_visit_booking(
    p_visit_id      UUID,
    p_descendant_id UUID DEFAULT NULL
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_visit  RECORD;
    v_slot   RECORD;
    v_booked INT;
BEGIN
    SELECT * INTO v_visit
    FROM public.grandma_visits
    WHERE id = p_visit_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'reason', 'visit_not_found');
    END IF;

    IF v_visit.status = 'cancelled' THEN
        RETURN jsonb_build_object('success', false, 'reason', 'already_cancelled');
    END IF;

    -- Ownership check: enforced when called from visitor flow (p_descendant_id IS NOT NULL).
    -- Admin calls pass NULL and skip this check.
    IF p_descendant_id IS NOT NULL AND v_visit.descendant_id <> p_descendant_id THEN
        RETURN jsonb_build_object('success', false, 'reason', 'ownership_denied');
    END IF;

    UPDATE public.grandma_visits
    SET status = 'cancelled', updated_at = NOW()
    WHERE id = p_visit_id;

    -- Re-open the slot if it still exists and is in the future.
    IF v_visit.slot_id IS NOT NULL THEN
        SELECT * INTO v_slot
        FROM public.visit_slots
        WHERE id = v_visit.slot_id
        FOR UPDATE;

        IF FOUND AND v_slot.slot_start > NOW() THEN
            SELECT COALESCE(SUM(participant_count), 0) INTO v_booked
            FROM public.grandma_visits
            WHERE slot_id = v_visit.slot_id AND status = 'scheduled';

            -- Re-open conditions (only if admin has not closed the slot):
            --   (a) slot is now empty — always re-open
            --   (b) slot allows sharing and still has remaining capacity
            -- Cancellation never modifies is_active.
            UPDATE public.visit_slots
            SET is_available =
                v_slot.is_active AND (
                    (v_booked = 0)
                    OR (v_slot.allows_shared_visits AND v_booked < v_slot.max_participants)
                )
            WHERE id = v_visit.slot_id;
        END IF;
    END IF;

    RETURN jsonb_build_object('success', true);
END;
$$;

GRANT EXECUTE ON FUNCTION public.cancel_visit_booking(UUID, UUID)
    TO anon, authenticated;


-- ════════════════════════════════════════════════════════════
-- SECTION 6: Helper — recalculate_visit_slot_availability
-- ════════════════════════════════════════════════════════════
-- Admin repair tool. Run from Supabase SQL Editor when is_available
-- gets out of sync due to manual data edits.
--
-- Usage:
--   SELECT * FROM public.recalculate_visit_slot_availability();
--
-- Returns one row per slot whose is_available was corrected.
-- Returns zero rows when all slots are consistent (normal state).

CREATE OR REPLACE FUNCTION public.recalculate_visit_slot_availability()
RETURNS TABLE(slot_id UUID, old_available BOOLEAN, new_available BOOLEAN)
LANGUAGE sql AS $$
    WITH booked AS (
        SELECT
            gv.slot_id,
            COALESCE(SUM(gv.participant_count), 0) AS total
        FROM public.grandma_visits gv
        WHERE gv.status = 'scheduled'
        GROUP BY gv.slot_id
    ),
    computed AS (
        SELECT
            vs.id           AS slot_id,
            vs.is_available AS current_flag,
            CASE
                -- Admin closed this slot: never available
                WHEN NOT vs.is_active
                    THEN false
                -- Past slot: never available
                WHEN vs.slot_start <= NOW()
                    THEN false
                -- No bookings: slot is open
                WHEN COALESCE(b.total, 0) = 0
                    THEN true
                -- Shared slot with remaining capacity: open
                WHEN vs.allows_shared_visits
                     AND COALESCE(b.total, 0) < vs.max_participants
                    THEN true
                -- All other cases (full, or non-shareable with a booking): closed
                ELSE false
            END AS correct_flag
        FROM public.visit_slots vs
        LEFT JOIN booked b ON b.slot_id = vs.id
    )
    UPDATE public.visit_slots vs
    SET is_available = c.correct_flag
    FROM computed c
    WHERE vs.id = c.slot_id
      AND vs.is_available IS DISTINCT FROM c.correct_flag
    RETURNING
        vs.id           AS slot_id,
        c.current_flag  AS old_available,
        c.correct_flag  AS new_available;
$$;
-- No GRANT to anon — admin SQL Editor use only.
