from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


def eligible_bank_flow_rule_batch_codes(tag_policy: dict[str, object]) -> set[str]:
    requirements = tag_policy.get("requirements_by_tag_code")
    requirements = requirements if isinstance(requirements, dict) else {}
    return {
        code
        for tag in list(tag_policy.get("active_tags") or [])
        if isinstance(tag, dict)
        and (code := str(tag.get("code") or "").strip())
        and isinstance(requirements.get(code), dict)
        and requirements[code].get("requires_oa") is False
        and requirements[code].get("requires_invoice") is False
    }


def build_live_bank_flow_rule_batch_service(
    source: dict[str, object],
    *,
    eligible_tag_codes: set[str] | None = None,
) -> BankBatchService:
    rows = [
        dict(row)
        for row in list(source.get("candidate_rows") or [])
        if isinstance(row, dict)
    ]
    active_relations = [
        dict(relation)
        for relation in list(source.get("active_relations") or [])
        if isinstance(relation, dict)
    ]
    formal_batches = {
        str(batch.get("batch_id") or ""): dict(batch)
        for batch in list(source.get("formal_items") or [])
        if isinstance(batch, dict) and str(batch.get("batch_id") or "").strip()
    }
    tag_policy = source.get("tag_policy")
    tag_policy = tag_policy if isinstance(tag_policy, dict) else {}
    definitions = {
        str(definition.get("code") or "").strip(): dict(definition)
        for definition in list(tag_policy.get("active_tags") or [])
        if isinstance(definition, dict) and str(definition.get("code") or "").strip()
    }
    categories = {
        str(row.get("id") or row.get("transaction_id") or ""): {
            "transaction_id": str(row.get("id") or row.get("transaction_id") or ""),
            "category_code": str(row.get("category_code") or ""),
            "category_label": str(
                definitions.get(str(row.get("category_code") or ""), {}).get("label")
                or row.get("category_label")
                or row.get("category_code")
                or ""
            ),
            "category_primary_label": str(
                definitions.get(str(row.get("category_code") or ""), {}).get(
                    "output_primary_label"
                )
                or row.get("category_primary_label")
                or ""
            ),
            "category_sub_label": str(
                definitions.get(str(row.get("category_code") or ""), {}).get(
                    "output_sub_label"
                )
                or row.get("category_sub_label")
                or ""
            ),
            "category_source": str(row.get("category_source") or ""),
        }
        for row in rows
        if str(row.get("id") or row.get("transaction_id") or "").strip()
    }
    pair_service = WorkbenchPairRelationService.from_snapshot(
        {
            "pair_relations": {
                str(relation.get("case_id") or ""): relation
                for relation in active_relations
                if str(relation.get("case_id") or "").strip()
            }
        }
    )
    batch_service = BankBatchService(
        batches=formal_batches,
        pair_relation_service=pair_service,
        schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
        batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
        relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
    )
    batch_service.build_batches(
        rows,
        categories,
        active_relations,
        {},
        eligible_batch_types=(
            eligible_tag_codes
            if eligible_tag_codes is not None
            else eligible_bank_flow_rule_batch_codes(tag_policy)
        ),
        apply_relation_repairs=False,
        relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        include_relation_backed_submitted_batches=False,
    )
    return batch_service


def bank_flow_rule_batch_candidate_guard(batch: dict[str, Any]) -> dict[str, object]:
    return {
        "batch_id": str(batch.get("batch_id") or "").strip(),
        "scope_month": str(batch.get("scope_month") or "").strip(),
        "batch_type": str(batch.get("batch_type") or "").strip(),
        "row_ids": sorted(
            {
                str(row_id).strip()
                for row_id in list(batch.get("row_ids") or [])
                if str(row_id).strip()
            }
        ),
        "total_amount": str(batch.get("total_amount") or "0"),
        "version": int(batch.get("version") or 1),
    }
