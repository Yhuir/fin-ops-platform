"""Canonical 查询的四要素表达式；由 PostgreSQL/Python 对照测试约束相同口径。"""


def invoice_financial_sql(alias: str) -> dict[str, str]:
    a, t, g = (f"{alias}.{field}" for field in ("amount", "tax_amount", "total_with_tax"))
    amounts = {"amount": f"coalesce({a}, round({g} - {t}, 2))",
               "tax_amount": f"coalesce({t}, round({g} - {a}, 2))",
               "total_with_tax": f"coalesce({g}, round({a} + {t}, 2))"}
    raw = f"btrim(coalesce({alias}.tax_rate, ''))"
    number = f"rtrim({raw}, '%%')::numeric"
    special = f"coalesce({alias}.raw_payload->'normalized_payload'->>'specific_business_type', {alias}.raw_payload->>'specific_business_type', '')"
    # A missing operand stays null; known zero is never treated as missing.
    rate = f"case when right({raw}, 1) <> '%%' and {number} <= 1 then {number} else {number} / 100 end"
    rate_valid = f"case when btrim({special}) = '' and {raw} ~ '^[0-9]+([.][0-9]+)?%%?$' then abs({amounts['amount']} * ({rate}) - {amounts['tax_amount']}) <= 0.01 else true end"
    valid = f"({amounts['amount']} * {amounts['tax_amount']} >= 0 and {amounts['amount']} * {amounts['total_with_tax']} >= 0 and ({rate_valid}))"
    for field, expression in list(amounts.items()):
        amounts[field] = f"case when {alias}.{field} is not null then {alias}.{field} when {valid} then {expression} end"
    inferred = f"coalesce({alias}.raw_payload->'normalized_payload'->'inferred_fields', '[]'::jsonb)"
    amounts['tax_rate'] = f"""case
        when {raw} = '' and {a} <> 0 and {t} <> 0 and {a} * {t} > 0
             and round({a} + {t}, 2) = round({g}, 2)
             and btrim({special}) = '' and not ({inferred} ?| array['amount','tax_amount','total_with_tax'])
            then trim_scale(case when round({a} * round({t} / nullif({a}, 0) * 100, 2) / 100, 2) = round({t}, 2)
                then round({t} / nullif({a}, 0) * 100, 2) else round({t} / nullif({a}, 0) * 100, 6) end)::text || '%%（推算）'
        when {raw} = '' then '未提供'
        when {raw} = 'mixed' then '多税率'
        when {raw} ~ '^[0-9]+([.][0-9]+)?%%?$' then
            trim_scale(case when right({raw}, 1) <> '%%' and {number} <= 1
                then {number} * 100 else {number} end)::text || '%%'
        else {raw} end"""
    return amounts
