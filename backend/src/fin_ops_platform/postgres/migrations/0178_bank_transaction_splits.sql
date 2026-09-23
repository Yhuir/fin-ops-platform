-- Bank source facts stay unchanged. Explicit use allocations belong to the bank owner.
CREATE TABLE app.bank_transaction_split_sets (
    bank_transaction_id uuid PRIMARY KEY REFERENCES app.bank_transactions(id) ON DELETE CASCADE,
    version bigint NOT NULL CHECK (version > 0),
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.bank_transaction_split_items (
    id uuid PRIMARY KEY,
    bank_transaction_id uuid NOT NULL REFERENCES app.bank_transaction_split_sets(bank_transaction_id) ON DELETE CASCADE,
    category_code text NOT NULL CHECK (category_code <> ''),
    amount numeric(20, 2) NOT NULL CHECK (amount > 0),
    position integer NOT NULL CHECK (position >= 0),
    UNIQUE (bank_transaction_id, position) DEFERRABLE INITIALLY DEFERRED
);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_ops_app_runtime') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON app.bank_transaction_split_sets, app.bank_transaction_split_items TO fin_ops_app_runtime;
        GRANT DELETE ON app.cost_statistics_manual_allocations TO fin_ops_app_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_ops_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON app.bank_transaction_split_sets, app.bank_transaction_split_items TO fin_ops_api;
        GRANT DELETE ON app.cost_statistics_manual_allocations TO fin_ops_api;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_ops_worker') THEN
        GRANT SELECT ON app.bank_transaction_split_sets, app.bank_transaction_split_items TO fin_ops_worker;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin_ops_readonly') THEN
        GRANT SELECT ON app.bank_transaction_split_sets, app.bank_transaction_split_items TO fin_ops_readonly;
    END IF;
END $$;
