ALTER TABLE app.cost_statistics_manual_allocations ADD COLUMN manual_items jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(manual_items) = 'array');
