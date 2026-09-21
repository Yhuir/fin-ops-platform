-- Cost-owned classification only; existing allocation amounts and versions are untouched.
ALTER TABLE app.cost_statistics_manual_allocations
    ADD COLUMN oa_cost_tag_overrides jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(oa_cost_tag_overrides) = 'array');
COMMENT ON COLUMN app.cost_statistics_manual_allocations.oa_cost_tag_overrides IS
    'Explicit OA source-line cost tags; empty means use the source bank classification. Never writes bank facts.';
