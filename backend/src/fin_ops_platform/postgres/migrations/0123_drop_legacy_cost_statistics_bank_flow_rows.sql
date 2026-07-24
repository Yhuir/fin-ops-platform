-- Cost time/tag queries now read the canonical Bank Detail projection directly.
-- Keeping a second copy makes freshness ambiguous and adds write/audit I/O.

drop table if exists read_model.cost_statistics_bank_flow_rows;
