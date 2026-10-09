-- Runtime contract boundary: persisted payment rules may now contain inclusive
-- operators. Older readers reject these values, so release activation is forward
-- only. Register the boundary without rewriting any rule or source invoice.
select 1;
