"""Canonical 原始财务表达式；不计算缺失金额或税率。"""


def _source_rate_sql(raw: str) -> str:
    number = f"rtrim({raw}, '%%')::numeric"
    return f"""case
        when {raw} in ('', '—') then null
        when {raw} = 'mixed' then '多税率'
        when {raw} ~ '^[0-9]+([.][0-9]+)?%%?$' then
            trim_scale(case when right({raw}, 1) <> '%%' and {number} <= 1
                then {number} * 100 else {number} end)::text || '%%'
        else {raw} end"""


def invoice_financial_sql(alias: str) -> dict[str, str]:
    amounts = {field: f"{alias}.{field}" for field in ("amount", "tax_amount", "total_with_tax")}
    payload = f"coalesce({alias}.raw_payload->'normalized_payload', {alias}.raw_payload, '{{}}'::jsonb)"
    lines = f"coalesce(nullif({payload}->'source_line_items', 'null'::jsonb), '[]'::jsonb)"
    header = _source_rate_sql(f"btrim(coalesce({alias}.tax_rate, ''))")
    line_rate = _source_rate_sql("btrim(coalesce(line->>'tax_rate', ''))")
    amounts["tax_amount_text"] = f"nullif(btrim({payload}->>'tax_amount_text'), '')"
    # 明细税率是来源字段；未印逐行价税合计不影响它的展示。
    amounts["tax_rate"] = f"""(
            select case
                when header.rate is not null and header.rate <> '多税率'
                    and bool_or(detail.rate is not null and detail.rate <> header.rate)
                    then '—'
                when header.rate is not null then header.rate
                when bool_or(detail.rate = '多税率') or count(distinct detail.rate) >= 2 then '多税率'
                when count(distinct detail.rate) = 1 and bool_and(detail.rate is not null)
                    then min(detail.rate)
                else '—' end
            from (select {header} as rate) header
            left join lateral (
                select {line_rate} as rate from jsonb_array_elements({lines}) line
                where line->>'source_sheet_role' is distinct from 'invoice_header'
            ) detail on true
            group by header.rate
        )"""
    return amounts
