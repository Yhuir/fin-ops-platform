-- Keep the existing revision when a manual decision returns to automatic calculation.
ALTER TABLE app.cost_statistics_manual_allocations
    ADD COLUMN decision_mode text NOT NULL DEFAULT 'manual'
    CHECK (decision_mode IN ('manual', 'automatic'));
COMMENT ON COLUMN app.cost_statistics_manual_allocations.decision_mode IS
    'Only manual rows supply allocation decisions; automatic rows retain the monotonic CAS revision.';
