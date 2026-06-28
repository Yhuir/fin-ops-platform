-- Hot-path read model indexes for production growth.
--
-- These indexes keep API reads SQL-native as row counts grow. They do not
-- change source-of-truth semantics: PostgreSQL read_model/job tables remain
-- authoritative, Redis remains a short TTL cache, and RabbitMQ remains only a
-- wake-up transport for outbox events.

create index if not exists workbench_groups_scope_zone_default_sort_idx
    on read_model.workbench_groups (
        scope_key,
        zone,
        scope_month desc nulls last,
        updated_at desc,
        group_id
    );

create index if not exists workbench_rows_scope_kind_month_updated_idx
    on read_model.workbench_rows (
        scope_key,
        source_kind,
        scope_month,
        updated_at desc
    );

create index if not exists workbench_rows_bank_counterparty_scope_idx
    on read_model.workbench_rows (
        source_kind,
        counterparty_name,
        scope_month,
        row_id
    )
    where source_kind = 'bank';

create index if not exists pending_invoice_rows_direction_page_idx
    on read_model.pending_invoice_rows (
        direction,
        trade_date desc,
        row_id
    );

create index if not exists pending_invoice_rows_direction_month_page_idx
    on read_model.pending_invoice_rows (
        direction,
        scope_month,
        trade_date desc,
        row_id
    );
