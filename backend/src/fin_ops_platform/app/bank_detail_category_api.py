from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryValidationError
from fin_ops_platform.services.bank_turnover_tag_semantics import normalize_external_third_label


def selected_category_code(payload: dict[str, Any]) -> str:
    return str(
        payload.get("category_code")
        or payload.get("selected_category_code")
        or payload.get("selectedCategoryCode")
        or ""
    ).strip()


def manual_assignment_selection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_code": selected_category_code(payload),
        "category_primary_label": payload.get("category_primary_label"),
        "category_sub_label": payload.get("category_sub_label"),
        "category_third_label": payload.get("category_third_label"),
        "category_label_path": [
            str(item).strip()
            for item in list(payload.get("category_label_path") or [])
            if str(item).strip()
        ],
        "turnover_action_type": payload.get("turnover_action_type"),
        "turnover_family": payload.get("turnover_family"),
    }


def confirmation_selection(
    *,
    payload: dict[str, Any],
    suggestion: dict[str, Any] | None,
    active_rule_codes: set[str],
    transaction_id: str,
) -> dict[str, Any]:
    selected_code = selected_category_code(payload)
    selected_third_label = normalize_external_third_label(
        payload.get("category_third_label") or payload.get("selectedCategoryThirdLabel")
    )
    if not isinstance(suggestion, dict) or str(suggestion.get("category_resolution_status") or "") != "needs_confirmation":
        raise BankTransactionCategoryValidationError(
            "invalid_category_confirmation_candidate",
            "当前流水没有需要确认的自动标签候选。",
            transaction_id=transaction_id,
        )
    candidate_payloads = [
        dict(candidate)
        for candidate in list(suggestion.get("auto_candidate_categories") or [])
        if isinstance(candidate, dict)
        and str(candidate.get("category_code") or "").strip() in active_rule_codes
    ]
    candidate_codes: list[str] = []
    seen_codes: set[str] = set()
    for raw_code in [
        *[candidate.get("category_code") for candidate in candidate_payloads],
        *list(suggestion.get("auto_candidate_category_codes") or []),
    ]:
        code = str(raw_code or "").strip()
        if not code or code in seen_codes or code not in active_rule_codes:
            continue
        seen_codes.add(code)
        candidate_codes.append(code)
    if not candidate_payloads:
        if len(candidate_codes) < 2:
            raise BankTransactionCategoryValidationError(
                "invalid_category_confirmation_candidate",
                "当前流水没有多个可确认的自动标签候选。",
                transaction_id=transaction_id,
            )
        if selected_code not in seen_codes:
            raise BankTransactionCategoryValidationError(
                "invalid_category_confirmation_candidate",
                "只能选择当前自动规则命中的候选标签。",
                transaction_id=transaction_id,
            )
        return {"category_code": selected_code, "candidate_category_codes": candidate_codes}

    selected_candidate = _match_candidate(
        candidates=candidate_payloads,
        selected_code=selected_code,
        selected_third_label=selected_third_label,
    )
    if selected_candidate is None:
        raise BankTransactionCategoryValidationError(
            "invalid_category_confirmation_candidate",
            "只能选择当前自动规则命中的候选标签。",
            transaction_id=transaction_id,
        )
    if len(candidate_payloads) < 2 and len(candidate_codes) < 2:
        raise BankTransactionCategoryValidationError(
            "invalid_category_confirmation_candidate",
            "当前流水没有多个可确认的自动标签候选。",
            transaction_id=transaction_id,
        )
    return {
        "category_code": selected_code,
        "candidate_category_codes": candidate_codes,
        "category_primary_label": selected_candidate.get("category_primary_label"),
        "category_sub_label": selected_candidate.get("category_sub_label"),
        "category_third_label": selected_candidate.get("category_third_label"),
        "category_label_path": list(selected_candidate.get("category_label_path") or []),
        "turnover_action_type": selected_candidate.get("turnover_action_type"),
        "turnover_family": selected_candidate.get("turnover_family"),
    }


def _match_candidate(
    *,
    candidates: list[dict[str, Any]],
    selected_code: str,
    selected_third_label: str,
) -> dict[str, Any] | None:
    matches = [
        candidate
        for candidate in candidates
        if str(candidate.get("category_code") or "").strip() == selected_code
    ]
    if selected_third_label:
        matches = [
            candidate
            for candidate in matches
            if normalize_external_third_label(candidate.get("category_third_label")) == selected_third_label
        ]
    if len(matches) == 1:
        return matches[0]
    if matches and not selected_third_label:
        no_third_matches = [
            candidate
            for candidate in matches
            if not normalize_external_third_label(candidate.get("category_third_label"))
        ]
        if len(no_third_matches) == 1:
            return no_third_matches[0]
    return None
