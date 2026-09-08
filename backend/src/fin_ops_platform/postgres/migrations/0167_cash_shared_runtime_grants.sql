-- Cash uses the existing App database login, not a new cash login or database.
-- This runtime role is already required by 0157 and verified in production.
-- Keep 0166 immutable; its earlier dedicated-role deployment comment is superseded.
GRANT USAGE ON SCHEMA cash TO fin_ops_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    cash.accounts, cash.bill_labels, cash.categories, cash.deleted_submission_ids,
    cash.flows, cash.items, cash.settings, cash.settlements,
    cash.task_occurrences, cash.task_templates
TO fin_ops_app_runtime;
