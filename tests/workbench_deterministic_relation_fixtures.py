from __future__ import annotations

from datetime import date

from fin_ops_platform.services.workbench_free_matching_engine import (
    ActiveFormalRelationAnchor,
    FormalRelationFact,
    FormalRelationFactBatch,
)


YUNNAN_LIFU_CASE_ID = (
    "case:decision:2026-05:oa_invoice_exact_amount:"
    "oa-pay-2169:inv_imported_0369"
)
YUNNAN_LIFU_INVOICE_NO = "26532000000716859331"


def yunnan_lifu_520_fixture() -> FormalRelationFactBatch:
    facts = (
        FormalRelationFact(
            row_type="oa",
            canonical_object_identity="oa-pay-2169",
            row_id="oa-pay-2169",
            amount_minor=52_000,
            currency="CNY",
            direction="expenditure",
            fact_date=date(2026, 5, 7),
            evidence_keys=(("counterparty", "云南立孚科技有限公司"),),
            source_version="oa:2169",
        ),
        FormalRelationFact(
            row_type="invoice",
            canonical_object_identity="inv_imported_0369",
            row_id="inv_imported_0369",
            amount_minor=52_000,
            currency="CNY",
            direction="expenditure",
            fact_date=date(2026, 5, 7),
            evidence_keys=(
                ("counterparty", "云南立孚科技有限公司"),
                ("invoice_number", YUNNAN_LIFU_INVOICE_NO),
            ),
            source_version="invoice:0369",
        ),
    )
    return FormalRelationFactBatch(
        facts=facts,
        active_relations=(
            ActiveFormalRelationAnchor(
                case_id=YUNNAN_LIFU_CASE_ID,
                member_keys=(facts[0].member_key, facts[1].member_key),
            ),
        ),
        affected_scopes=("2026-05", "all"),
        source_versions=(("oa", "oa:2169"), ("invoice", "invoice:0369")),
    )


def omitted_thirteen_invoice_fixture() -> FormalRelationFactBatch:
    amounts = [10_000] * 12 + [50_949]
    facts = tuple(
        FormalRelationFact(
            row_type="invoice",
            canonical_object_identity=f"inv_omitted_{index:02d}",
            row_id=f"inv_omitted_{index:02d}",
            amount_minor=amount_minor,
            currency="CNY",
            direction="expenditure",
            fact_date=date(2026, 1 + ((index - 1) % 5), index),
            source_version=f"invoice:omitted:{index:02d}",
        )
        for index, amount_minor in enumerate(amounts, start=1)
    )
    return FormalRelationFactBatch(
        facts=facts,
        affected_scopes=("2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "all"),
        source_versions=(("invoice", "omitted-thirteen-v1"),),
    )
