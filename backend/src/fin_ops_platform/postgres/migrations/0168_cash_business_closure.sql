-- Cash-only ownership and category facts. Existing unknown classifications stay NULL.
ALTER TABLE cash.settings ADD COLUMN personal_counterparty text
 CHECK (personal_counterparty IS NULL OR length(btrim(personal_counterparty)) BETWEEN 1 AND 120);
ALTER TABLE cash.items ADD COLUMN category_id uuid REFERENCES cash.categories(id);
ALTER TABLE cash.items ADD CONSTRAINT cash_item_category_scope
 CHECK (category_id IS NULL OR type IN ('expense','ticket_source'));
ALTER TABLE cash.settlements ADD COLUMN category_id uuid REFERENCES cash.categories(id);
ALTER TABLE cash.settlements ADD CONSTRAINT cash_settlement_category_scope
 CHECK (category_id IS NULL OR (kind='non_ticket_offset' AND source_item_id IS NULL));
