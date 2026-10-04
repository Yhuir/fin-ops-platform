-- 原件未提供未税金额时保留 NULL，不能用含税金额或零代填。
alter table app.invoices alter column amount drop not null;
alter table app.invoices alter column signed_amount drop not null;
-- ETC 原件的非数字税额（例如 *）只保留原文，不存为零。
alter table app.etc_invoices alter column tax_amount drop not null;
