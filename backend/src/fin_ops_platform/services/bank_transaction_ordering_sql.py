"""Request-local bank order evidence. No writes, identity generation or I/O.

The repository supplies complete candidate days in ordering_input, complete time
groups in ordering_target_groups, and history in balance_identity_rows.
All amounts remain PostgreSQL numeric.
"""

BANK_NORMALIZED_CURRENCY_SQL = """case
  when currency is null or btrim(currency::text) = '' then 'CNY'
  when upper(btrim(currency::text)) in ('CNY', 'RMB') then 'CNY'
  when btrim(currency::text) in ('人民币', '人民币元', '元') then 'CNY'
  else upper(btrim(currency::text))
end"""

BANK_TRANSACTION_ORDERING_CTES = """
ordering_day_rows as (
  select input.*,
    count(*) over (
      partition by account_identity, normalized_currency, txn_date
    ) > 1 and bool_or(trade_time is null) over (
      partition by account_identity, normalized_currency, txn_date
    ) as day_ambiguous
  from ordering_input input
),
order_rows as materialized (
  select days.*,
    dense_rank() over (
      order by days.account_identity, days.normalized_currency, days.trade_time_sort
    ) as order_group
  from ordering_day_rows days
  join ordering_target_groups targets using (account_identity, trade_time_sort)
),
order_groups as materialized (
  select order_group, account_identity, normalized_currency, trade_time_sort,
    count(*)::integer as member_count,
    bool_or(day_ambiguous) as day_ambiguous,
    bool_and(balance is not null and amount > 0 and signed_amount is not null
      and ((txn_direction = 'inflow' and signed_amount = amount)
        or (txn_direction = 'outflow' and signed_amount = -amount))
      and normalized_account_no is not null) as valid_edges,
    count(balance)::integer as balance_count,
    min(balance) as single_balance,
    min(row_id) as single_row_id
  from order_rows
  group by order_group, account_identity, normalized_currency, trade_time_sort
),
order_edges as materialized (
  select rows.order_group, rows.row_id,
    rows.balance - rows.signed_amount as before_balance,
    rows.balance as after_balance
  from order_rows rows
  join order_groups groups using (order_group)
  where groups.member_count > 1 and groups.valid_edges
    and not groups.day_ambiguous
),
order_degrees as materialized (
  select order_group, balance, sum(outgoing)::integer as outgoing,
    sum(incoming)::integer as incoming
  from (
    select order_group, before_balance as balance, 1 as outgoing, 0 as incoming
    from order_edges
    union all
    select order_group, after_balance, 0, 1 from order_edges
  ) edges
  group by order_group, balance
),
order_shapes as materialized (
  select order_group, count(*)::integer as vertex_count,
    min(balance) as any_balance,
    min(balance) filter (where outgoing - incoming = 1) as start_balance,
    min(balance) filter (where incoming - outgoing = 1) as end_balance,
    bool_and(outgoing = incoming) as closed,
    (count(*) filter (where outgoing - incoming = 1) = 1
      and count(*) filter (where incoming - outgoing = 1) = 1
      and bool_and(abs(outgoing - incoming) <= 1)) as open,
    -- ponytail: branches remain unconfirmed; never enumerate alternative trails.
    max(outgoing) <= 1 as unbranched
  from order_degrees group by order_group
),
order_neighbors as materialized (
  select order_group, before_balance as balance, after_balance as neighbor
  from order_edges
  union
  select order_group, after_balance, before_balance from order_edges
),
order_reachable(order_group, balance) as (
  select order_group, any_balance from order_shapes where open or closed
  union
  select reach.order_group, edge.neighbor
  from order_reachable reach join order_neighbors edge
    on edge.order_group = reach.order_group and edge.balance = reach.balance
),
order_connected as (
  select order_group, count(*)::integer as reached_count
  from order_reachable group by order_group
),
order_starts as materialized (
  select shape.*, groups.member_count,
    case when shape.open then shape.start_balance
      when anchor.member_count = 1 and exists (
        select 1 from order_degrees vertex where vertex.order_group = shape.order_group
          and vertex.balance = anchor.balance
      ) then anchor.balance end as proven_start,
    case when shape.open then shape.end_balance
      when anchor.member_count = 1 and exists (
        select 1 from order_degrees vertex where vertex.order_group = shape.order_group
          and vertex.balance = anchor.balance
      ) then anchor.balance end as proven_end
  from order_shapes shape
  join order_connected connected using (order_group)
  join order_groups groups using (order_group)
  left join lateral (
    select count(*) as member_count,
      case when bool_and(previous.trade_time is not null)
        then min(previous.balance) end as balance
    from (
      select history.balance, history.trade_time_sort, history.trade_time,
        rank() over (order by history.trade_time_sort desc) as time_rank
      from balance_identity_rows history
      where shape.closed
        and history.account_identity = groups.account_identity
        and history.normalized_currency = groups.normalized_currency
        and history.trade_time_sort < groups.trade_time_sort
    ) previous where previous.time_rank = 1
  ) anchor on shape.closed
  where connected.reached_count = shape.vertex_count
    and (shape.open or shape.closed)
),
order_walk(order_group, position, row_id, after_balance) as (
  select starts.order_group, 1, edge.row_id, edge.after_balance
  from order_starts starts join order_edges edge
    on edge.order_group = starts.order_group
    and edge.before_balance = starts.proven_start
  where starts.unbranched
  union all
  select walk.order_group, walk.position + 1, edge.row_id, edge.after_balance
  from order_walk walk
  join order_starts starts using (order_group)
  join order_edges edge on edge.order_group = walk.order_group
    and edge.before_balance = walk.after_balance
  where walk.position < starts.member_count
),
order_complete as materialized (
  select walk.order_group
  from order_walk walk join order_groups groups using (order_group)
  group by walk.order_group, groups.member_count
  having count(*) = groups.member_count
    and count(distinct walk.row_id) = groups.member_count
),
order_end_ids as (
  select edge.order_group, min(edge.row_id) as row_id
  from order_edges edge join order_starts starts using (order_group)
  where edge.after_balance = starts.proven_end
  group by edge.order_group having count(*) = 1
),
order_group_results as materialized (
  select groups.*,
    case when groups.day_ambiguous then 'unresolved'
      when groups.member_count = 1 then 'time'
      when complete.order_group is not null then 'balance_chain'
      else 'unresolved' end as same_time_order_status,
    case when groups.day_ambiguous then null
      when groups.member_count = 1 then groups.single_balance
      else starts.proven_end end as end_balance,
    case when groups.day_ambiguous then null
      when groups.member_count = 1 and groups.single_balance is not null
        then groups.single_row_id
      when complete.order_group is not null then last_step.row_id
      else end_ids.row_id end as end_row_id
  from order_groups groups
  left join order_starts starts using (order_group)
  left join order_complete complete using (order_group)
  left join order_walk last_step on last_step.order_group = complete.order_group
    and last_step.position = groups.member_count
  left join order_end_ids end_ids on end_ids.order_group = groups.order_group
),
order_results as (
  select rows.row_id, rows.account_identity, rows.normalized_currency,
    groups.same_time_order_status,
    case when groups.same_time_order_status = 'balance_chain'
      then walk.position end as order_in_group
  from order_rows rows join order_group_results groups using (order_group)
  left join order_complete complete using (order_group)
  left join order_walk walk on walk.order_group = complete.order_group
    and walk.row_id = rows.row_id
)
"""
