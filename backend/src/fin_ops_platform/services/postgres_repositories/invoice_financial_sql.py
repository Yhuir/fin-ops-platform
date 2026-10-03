"""Canonical 财务表达式；税率只解释来源，金额只做同票加减。"""


def _source_rate_sql(raw: str, inferred: str) -> str:
    number = f"rtrim({raw}, '%%')::numeric"
    return f"""case
        when {inferred} ? 'tax_rate' or {raw} in ('', 'mixed', '未提供', '无法确定')
             or {raw} like '%%（推算）%%' then null
        when {raw} ~ '^[0-9]+([.][0-9]+)?%%?$' then
            trim_scale(case when right({raw}, 1) <> '%%' and {number} <= 1
                then {number} * 100 else {number} end)::text || '%%'
        else {raw} end"""


def _money_sql(a: str, t: str, g: str) -> dict[str, str]:
    amounts = {"amount": f"coalesce({a}, round({g} - {t}, 2))",
               "tax_amount": f"coalesce({t}, round({g} - {a}, 2))",
               "total_with_tax": f"coalesce({g}, round({a} + {t}, 2))"}
    # An aggregate invoice is not one tax line after per-line rounding.
    valid = f"(round({amounts['amount']} + {amounts['tax_amount']}, 2) = round({amounts['total_with_tax']}, 2) and {amounts['amount']} * {amounts['tax_amount']} >= 0 and {amounts['amount']} * {amounts['total_with_tax']} >= 0)"
    return {key: f"case when {raw} is not null then {raw} when {valid} then {amounts[key]} end"
            for key, raw in zip(amounts, (a, t, g), strict=True)}


def invoice_financial_sql(alias: str) -> dict[str, str]:
    a, t, g = (f"{alias}.{field}" for field in ("amount", "tax_amount", "total_with_tax"))
    amounts = _money_sql(a, t, g)
    payload = f"coalesce({alias}.raw_payload->'normalized_payload', {alias}.raw_payload, '{{}}'::jsonb)"
    inferred = f"coalesce({payload}->'inferred_fields', '[]'::jsonb)"
    lines = f"coalesce(nullif({payload}->'source_line_items', 'null'::jsonb), '[]'::jsonb)"
    header = _source_rate_sql(f"btrim(coalesce({alias}.tax_rate, ''))", inferred)
    line_rate = _source_rate_sql("btrim(coalesce(line->>'tax_rate', ''))", "coalesce(line->'inferred_fields', '[]'::jsonb)")
    line_money = _money_sql("la", "lt", "lg")
    # Embedded source rows require no additional database round trips.
    amounts["tax_rate"] = f"""case when jsonb_array_length({lines}) = 0
        then coalesce({header}, '无法确定') else (
            select case
                when header.rate is not null and header.rate <> '多税率'
                    and bool_or(detail.rate is not null and detail.rate <> header.rate)
                    then '无法确定'
                when header.rate is not null and header.rate <> '多税率' then header.rate
                when bool_or(detail.rate = '多税率') or count(distinct detail.rate) >= 2 then '多税率'
                when count(distinct detail.rate) = 1 and bool_and(detail.rate is not null)
                    and bool_and(detail.valid_money)
                    and (header.amount is not null or header.tax_amount is not null or header.total_with_tax is not null)
                    and (header.amount is null or (bool_and(detail.amount is not null) and round(sum(detail.amount), 2) = round(header.amount, 2)))
                    and (header.tax_amount is null or (bool_and(detail.tax_amount is not null) and round(sum(detail.tax_amount), 2) = round(header.tax_amount, 2)))
                    and (header.total_with_tax is null or (bool_and(detail.total_with_tax is not null) and round(sum(detail.total_with_tax), 2) = round(header.total_with_tax, 2)))
                    then min(detail.rate)
                else '无法确定' end
            from (select {header} as rate, {amounts['amount']} as amount,
                {amounts['tax_amount']} as tax_amount, {amounts['total_with_tax']} as total_with_tax) header
            cross join lateral (
                select {line_rate} as rate, money.*,
                    case when ca is null or ct is null or cg is null
                        then true else round(ca + ct, 2) = round(cg, 2)
                            and ca * ct >= 0 and ca * cg >= 0 end as valid_money
                from jsonb_array_elements({lines}) line
                cross join lateral (select nullif(replace(btrim(line->>'amount'), ',', ''), '')::numeric as la,
                    nullif(replace(btrim(line->>'tax_amount'), ',', ''), '')::numeric as lt,
                    nullif(replace(btrim(line->>'total_with_tax'), ',', ''), '')::numeric as lg) original
                cross join lateral (select coalesce(la, round(lg-lt, 2)) as ca,
                    coalesce(lt, round(lg-la, 2)) as ct, coalesce(lg, round(la+lt, 2)) as cg) proposal
                cross join lateral (select {line_money['amount']} as amount,
                    {line_money['tax_amount']} as tax_amount, {line_money['total_with_tax']} as total_with_tax) money
            ) detail
            group by header.rate, header.amount, header.tax_amount, header.total_with_tax
        ) end"""
    return amounts
