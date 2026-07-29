from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchService,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
)
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
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
    categories = bank_flow_rule_batch_effective_categories(source)
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


def bank_flow_rule_batch_effective_categories(
    source: dict[str, object],
) -> dict[str, dict[str, Any]]:
    rows = [
        dict(row)
        for row in list(source.get("candidate_rows") or source.get("rows") or [])
        if isinstance(row, dict)
    ]
    manual_categories: dict[str, dict[str, Any]] = {}
    for row in rows:
        transaction_id = str(
            row.get("id") or row.get("transaction_id") or ""
        ).strip()
        category_code = str(row.get("category_code") or "").strip()
        if not transaction_id or not category_code:
            continue
        category_source = str(row.get("category_source") or "").strip()
        manual_categories[transaction_id] = {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "source": category_source,
            "manual_assignment": category_source == "manual",
            "version": int(row.get("category_version") or 0),
        }
    tag_dictionary = source.get("tag_dictionary")
    category_service = BankTransactionCategoryService(
        categories=manual_categories,
        tag_dictionary=tag_dictionary if isinstance(tag_dictionary, dict) else None,
    )
    return BankTransactionEffectiveCategoryProvider(
        category_service=category_service,
        auto_category_service=BankTransactionAutoCategoryService(
            category_service=category_service,
        ),
    ).bulk_get_for_rows(rows)


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


def bank_flow_rule_batch_selected_row_proofs(
    rows: list[dict[str, object]],
    categories_by_transaction_id: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    categories = categories_by_transaction_id or {}
    proofs: list[dict[str, str]] = []
    for row in rows:
        row_id = str(row.get("id") or row.get("transaction_id") or "").strip()
        if not row_id:
            continue
        category = categories.get(row_id) or {}
        amount = BankBatchService._amount(row)
        if amount is None:
            raise ValueError(
                "bank_flow_rule_batch_selection_invalid_amount"
            )
        direction = BankBatchService._direction(row)
        if not direction:
            raise ValueError(
                "bank_flow_rule_batch_selection_invalid_direction"
            )
        raw_month = str(
            row.get("scope_month")
            or row.get("month")
            or row.get("txn_month")
            or row.get("trade_time")
            or row.get("txn_date")
            or ""
        ).strip()
        proofs.append(
            {
                "row_id": row_id,
                "scope_month": raw_month[:7],
                "category_code": str(
                    category.get("effective_category_code")
                    or category.get("category_code")
                    or row.get("category_code")
                    or ""
                ).strip(),
                "amount": BankBatchService._format_amount(amount),
                "direction": "income" if direction == "inflow" else "expense",
                "account_key": str(row.get("account_key") or "").strip(),
                "trade_time": str(
                    row.get("trade_time")
                    or row.get("pay_receive_time")
                    or row.get("txn_date")
                    or ""
                ).strip(),
            }
        )
    return sorted(proofs, key=lambda proof: proof["row_id"])
