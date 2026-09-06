-- Cash is a separate fact owner in the existing PostgreSQL database.
-- No app/audit/job foreign keys, triggers, financial rows or sample business data.
CREATE SCHEMA cash;
REVOKE ALL ON SCHEMA cash FROM PUBLIC;

CREATE TABLE cash.accounts (
 id uuid PRIMARY KEY, name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
 kind text NOT NULL CHECK (kind IN ('cash','savings')),
 opening_date date NOT NULL,
 opening_amount numeric(18,2) NOT NULL CHECK (opening_amount BETWEEN -9999999999999999.99 AND 9999999999999999.99),
 enabled boolean NOT NULL DEFAULT true, remark text CHECK (length(remark)<=2000),
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE cash.categories (
 id uuid PRIMARY KEY, name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
 "group" text NOT NULL CHECK ("group" IN ('receipt','payment','turnover')),
 enabled boolean NOT NULL DEFAULT true, remark text CHECK (length(remark)<=2000),
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE cash.bill_labels (
 id uuid PRIMARY KEY, bank_name text NOT NULL CHECK (length(btrim(bank_name)) BETWEEN 1 AND 120),
 label text NOT NULL CHECK (length(btrim(label)) BETWEEN 1 AND 120), enabled boolean NOT NULL DEFAULT true,
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE cash.settings (
 id smallint PRIMARY KEY CHECK (id=1),
 allowed_project_stage_codes text[] NOT NULL DEFAULT '{}',
 project_selection_configured boolean NOT NULL DEFAULT false, personal_opening_date date,
 version integer NOT NULL DEFAULT 1 CHECK (version>0), updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO cash.settings(id) VALUES (1);
CREATE TABLE cash.task_templates (
 id uuid PRIMARY KEY, title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 120),
 kind text NOT NULL CHECK (kind IN ('receipt','payment','check')),
 execution_day smallint NOT NULL CHECK (execution_day BETWEEN 1 AND 31),
 remind_days smallint NOT NULL CHECK (remind_days BETWEEN 0 AND 31),
 effective_from_month date NOT NULL CHECK (extract(day FROM effective_from_month)=1),
 effective_to_month date CHECK (extract(day FROM effective_to_month)=1 AND effective_to_month>=effective_from_month),
 enabled boolean NOT NULL DEFAULT true,
 default_account_id uuid REFERENCES cash.accounts(id), default_category_id uuid REFERENCES cash.categories(id),
 default_amount numeric(18,2) CHECK (default_amount BETWEEN 0.01 AND 9999999999999999.99),
 instructions text CHECK (length(instructions)<=2000),
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (kind<>'check' OR (default_account_id IS NULL AND default_category_id IS NULL AND default_amount IS NULL))
);
CREATE TABLE cash.task_occurrences (
 id uuid PRIMARY KEY, template_id uuid NOT NULL REFERENCES cash.task_templates(id),
 month date NOT NULL CHECK (extract(day FROM month)=1), due_on date NOT NULL,
 planned_amount numeric(18,2) CHECK (planned_amount BETWEEN 0.01 AND 9999999999999999.99),
 processing_state text NOT NULL DEFAULT 'pending' CHECK (processing_state IN ('pending','unpaid','checked')),
 template_values_snapshot jsonb NOT NULL CHECK (jsonb_typeof(template_values_snapshot)='object'
   AND template_values_snapshot ?& ARRAY['template_version','title','kind','remind_days','instructions','default_account_id','default_category_id']
   AND template_values_snapshot->>'kind' IS NOT NULL),
 note text CHECK (length(note)<=2000), version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(template_id,month),
 CHECK (due_on>=month-31 AND due_on<=(month+interval '1 month'-interval '1 day')::date+31),
 CHECK ((template_values_snapshot->>'kind'='check' AND planned_amount IS NULL AND processing_state IN ('pending','checked'))
     OR (template_values_snapshot->>'kind' IN ('receipt','payment') AND processing_state IN ('pending','unpaid')))
);
CREATE TABLE cash.flows (
 id uuid PRIMARY KEY, occurred_on date NOT NULL,
 kind text NOT NULL CHECK (kind IN ('receipt','payment','transfer')),
 amount numeric(18,2) NOT NULL CHECK (amount BETWEEN 0.01 AND 9999999999999999.99),
 from_account_id uuid REFERENCES cash.accounts(id), to_account_id uuid REFERENCES cash.accounts(id),
 category_id uuid REFERENCES cash.categories(id), oa_project_id text, project_name_snapshot text,
 person_name text CHECK (length(btrim(person_name)) BETWEEN 1 AND 120),
 content text NOT NULL CHECK (length(btrim(content)) BETWEEN 1 AND 1000), remark text CHECK (length(remark)<=2000),
 source_kind text NOT NULL CHECK (source_kind IN ('manual','monthly_task')),
 task_occurrence_id uuid REFERENCES cash.task_occurrences(id), created_by_account text NOT NULL,
 created_by_name text, version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((oa_project_id IS NULL)=(project_name_snapshot IS NULL)),
 CHECK (source_kind<>'monthly_task' OR task_occurrence_id IS NOT NULL),
 CHECK ((kind='receipt' AND from_account_id IS NULL AND to_account_id IS NOT NULL AND category_id IS NOT NULL)
     OR (kind='payment' AND from_account_id IS NOT NULL AND to_account_id IS NULL AND category_id IS NOT NULL)
     OR (kind='transfer' AND from_account_id IS NOT NULL AND to_account_id IS NOT NULL AND from_account_id<>to_account_id AND category_id IS NULL AND task_occurrence_id IS NULL))
);
CREATE TABLE cash.items (
 id uuid PRIMARY KEY, type text NOT NULL CHECK (type IN ('loan','company_receivable','expense','ticket_source')),
 origin_date date NOT NULL, original_amount numeric(18,2) NOT NULL CHECK (original_amount BETWEEN 0.01 AND 9999999999999999.99),
 is_opening boolean NOT NULL DEFAULT false, obligation_direction text, ledger_group text, counterparty text,
 oa_project_id text, project_name_snapshot text, origin_flow_id uuid REFERENCES cash.flows(id), origin_mode text,
 bill_label_id uuid REFERENCES cash.bill_labels(id), bill_month date CHECK (extract(day FROM bill_month)=1),
 ticket_provider text, ticket_provided_on date, ticket_description text,
 related_obligation_id uuid REFERENCES cash.items(id), ticket_source_id uuid REFERENCES cash.items(id),
 content text NOT NULL CHECK (length(btrim(content)) BETWEEN 1 AND 1000), remark text CHECK (length(remark)<=2000),
 version integer NOT NULL DEFAULT 1 CHECK (version>0), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((oa_project_id IS NULL)=(project_name_snapshot IS NULL)),
 CHECK ((bill_label_id IS NULL)=(bill_month IS NULL)),
 CHECK ((origin_flow_id IS NULL)=(origin_mode IS NULL)),
 CHECK (origin_mode IN ('created','linked')),
 CHECK (NOT is_opening OR (type IN ('loan','company_receivable') AND origin_flow_id IS NULL)),
 CHECK (origin_flow_id IS NULL OR type IN ('loan','expense')),
 CHECK (bill_label_id IS NULL OR type IN ('loan','expense')),
 CHECK (related_obligation_id IS NULL OR (type='expense' AND related_obligation_id<>id)),
 CHECK (ticket_source_id IS NULL OR (type='company_receivable' AND ticket_source_id<>id)),
 CHECK ((type='loan' AND obligation_direction IS NOT NULL AND obligation_direction IN ('receivable','payable') AND ledger_group IS NOT NULL AND ledger_group IN ('company','external_person','personal') AND counterparty IS NOT NULL)
     OR (type='company_receivable' AND obligation_direction IS NOT NULL AND obligation_direction='receivable' AND ledger_group IS NOT NULL AND ledger_group='company' AND counterparty IS NOT NULL)
     OR (type IN ('expense','ticket_source') AND obligation_direction IS NULL AND ledger_group IS NULL AND counterparty IS NULL)),
 CHECK (ledger_group<>'personal' OR obligation_direction='receivable'),
 CHECK (counterparty IS NULL OR length(btrim(counterparty)) BETWEEN 1 AND 120),
 CHECK ((type='ticket_source' AND ticket_provider IS NOT NULL AND ticket_provided_on IS NOT NULL AND ticket_description IS NOT NULL AND origin_date=ticket_provided_on)
     OR (type<>'ticket_source' AND ticket_provider IS NULL AND ticket_provided_on IS NULL AND ticket_description IS NULL)),
 CHECK (ticket_provider IS NULL OR length(btrim(ticket_provider)) BETWEEN 1 AND 120),
 CHECK (ticket_description IS NULL OR length(btrim(ticket_description)) BETWEEN 1 AND 1000)
);
CREATE TABLE cash.settlements (
 id uuid PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('cash_repayment','company_collection','expense_payment','expense_refund','ticket_use','ticket_offset','non_ticket_offset')),
 amount numeric(18,2) NOT NULL CHECK (amount BETWEEN 0.01 AND 9999999999999999.99), occurred_on date NOT NULL,
 item_id uuid REFERENCES cash.items(id), flow_id uuid REFERENCES cash.flows(id), source_item_id uuid REFERENCES cash.items(id),
 remark text CHECK (length(remark)<=2000), version integer NOT NULL DEFAULT 1 CHECK (version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(flow_id,item_id,kind), CHECK (item_id IS NULL OR source_item_id IS NULL OR item_id<>source_item_id),
 CHECK ((kind IN ('cash_repayment','company_collection','expense_payment','expense_refund') AND item_id IS NOT NULL AND flow_id IS NOT NULL AND source_item_id IS NULL)
     OR (kind='ticket_use' AND item_id IS NULL AND flow_id IS NULL AND source_item_id IS NOT NULL AND remark IS NOT NULL AND length(btrim(remark))>0)
     OR (kind='ticket_offset' AND item_id IS NOT NULL AND flow_id IS NULL AND source_item_id IS NOT NULL)
     OR (kind='non_ticket_offset' AND item_id IS NOT NULL AND flow_id IS NULL AND (source_item_id IS NOT NULL OR (remark IS NOT NULL AND length(btrim(remark))>0))))
);
CREATE TABLE cash.deleted_submission_ids (
 entity_type text NOT NULL CHECK (entity_type IN ('flow','item')), id uuid NOT NULL, PRIMARY KEY(entity_type,id)
);
CREATE INDEX cash_flows_date_idx ON cash.flows(occurred_on,created_at,id);
CREATE INDEX cash_flows_from_idx ON cash.flows(from_account_id,occurred_on,id);
CREATE INDEX cash_flows_to_idx ON cash.flows(to_account_id,occurred_on,id);
CREATE INDEX cash_flows_task_idx ON cash.flows(task_occurrence_id);
CREATE INDEX cash_occurrences_month_idx ON cash.task_occurrences(month,due_on,id);
CREATE INDEX cash_items_origin_idx ON cash.items(origin_flow_id);
CREATE INDEX cash_items_type_date_idx ON cash.items(type,origin_date,id);
CREATE INDEX cash_items_bill_idx ON cash.items(bill_label_id,origin_date,id);
CREATE INDEX cash_items_ticket_idx ON cash.items(ticket_source_id);
CREATE INDEX cash_items_obligation_idx ON cash.items(related_obligation_id);
CREATE INDEX cash_settlements_item_idx ON cash.settlements(item_id,occurred_on,id);
CREATE INDEX cash_settlements_flow_idx ON cash.settlements(flow_id);
CREATE INDEX cash_settlements_source_idx ON cash.settlements(source_item_id);
REVOKE ALL ON ALL TABLES IN SCHEMA cash FROM PUBLIC;
-- Deployment provisions a dedicated cash role and grants only cash DML.
-- No runtime role names or passwords are inferred by a schema migration.
