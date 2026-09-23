"""Set-based SQL counterpart of bank_split_comparison_rows; no per-member I/O."""


def bank_split_scope_ctes(*, bank_rows_sql: str, targets_sql: str) -> str:
    """Inputs are owner SQL, never HTTP values.

    Banks: group_key, bank_id, amount, direction, is_split, turnover_role.
    Targets: group_key, target_amount. Output: scope_bank_members(group_key,bank_id).
    """
    return f"""
    scope_bank_input as materialized ({bank_rows_sql}),
    scope_bank_targets as materialized ({targets_sql}),
    scope_bank_classified as materialized (
        select *, (is_split and coalesce(turnover_role, '') = 'external_turnover') as principal
        from scope_bank_input
    ),
    scope_bank_totals as materialized (
        select group_key,
               sum(amount) filter (where principal) as principal_total,
               sum(amount) filter (where not principal) as other_total,
               count(*) filter (where principal) as principal_count,
               count(*) filter (where not principal) as other_count,
               bool_and(is_split) and count(distinct direction) = 1 and bool_and(direction in ('inflow','outflow'))
                   and count(direction) = count(*) and count(amount) = count(*) as comparable
        from scope_bank_classified group by group_key
    ),
    scope_bank_members as materialized (
        select bank.group_key, bank.bank_id
        from scope_bank_classified bank
        join scope_bank_totals totals using (group_key)
        left join scope_bank_targets target using (group_key)
        where case
            when totals.comparable and totals.principal_count > 0 and totals.other_count > 0
                 and target.target_amount > 0 then
                case when totals.principal_total = target.target_amount and totals.other_total <> target.target_amount
                          then bank.principal
                     when totals.other_total = target.target_amount and totals.principal_total <> target.target_amount
                          then not bank.principal
                     else true end
            else true end
    )
    """
