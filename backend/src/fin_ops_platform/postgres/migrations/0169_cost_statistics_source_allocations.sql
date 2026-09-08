-- Preserve historical per-unit amounts. NULL explicitly means no saved source decision.
ALTER TABLE app.cost_statistics_manual_allocations
    ADD COLUMN source_allocations jsonb,
    ADD CONSTRAINT cost_statistics_source_allocations_object
        CHECK (source_allocations IS NULL OR jsonb_typeof(source_allocations) = 'object');
COMMENT ON COLUMN app.cost_statistics_manual_allocations.source_allocations IS
    'Explicit cost_lines, refund_links and non_cost_lines; account/tag/date come from bank source';
