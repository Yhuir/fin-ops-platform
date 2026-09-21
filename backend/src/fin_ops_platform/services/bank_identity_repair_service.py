from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy


def build_bank_identity_repair_plan(
    rows: list[dict[str, Any]], *, transaction_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Plan an in-place v2 identity migration; never alter transaction facts."""
    policy = FinancialObjectIdentityPolicy()
    by_id = {row["transaction_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("Bank transaction identities are not unique.")
    targets = sorted(set(transaction_ids)) if transaction_ids is not None else sorted(
        row["transaction_id"] for row in rows
        if str(row.get("source_unique_key") or "").startswith("bank-v2:")
    )
    if set(targets) - by_id.keys():
        raise ValueError("An explicit bank identity repair target is missing.")
    computed = {key: policy.identify_bank_transaction_mapping(row) for key, row in by_id.items()}
    canonical_counts = Counter(identity.canonical_key for identity in computed.values() if identity.canonical_key)
    stored_counts = Counter(row["source_unique_key"] for row in rows if row.get("source_unique_key"))
    updates = []
    for transaction_id in targets:
        row = by_id[transaction_id]
        identity = computed[transaction_id]
        before_key = str(row.get("source_unique_key") or "")
        after_key = identity.canonical_key or ""
        payload = row.get("raw_payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("normalized_payload"), dict):
            raise ValueError(f"Missing bank identity payload: {transaction_id}")
        normalized = payload["normalized_payload"]
        payload_identity = policy.identify_bank_transaction_mapping(normalized)
        if (payload_identity.canonical_key != after_key
                or payload_identity.suspected_key != identity.suspected_key
                or normalized.get("source_unique_key") != before_key
                or normalized.get("data_fingerprint") != row.get("data_fingerprint")):
            raise ValueError(f"Bank identity payload disagrees with canonical facts: {transaction_id}")
        if not after_key.startswith("bank-v3:") or not identity.suspected_key:
            raise ValueError(f"Bank identity lacks complete migration evidence: {transaction_id}")
        if row.get("data_fingerprint") != identity.suspected_key:
            raise ValueError(f"Bank fingerprint disagrees with canonical facts: {transaction_id}")
        if canonical_counts[after_key] != 1:
            raise ValueError(f"Bank target identity is ambiguous: {transaction_id}")
        if before_key == after_key:
            continue
        if (not before_key.startswith("bank-v2:")
                or before_key.replace("bank-v2:", "bank-v3:", 1) != after_key.rsplit(":", 1)[0]
                or stored_counts[after_key]):
            raise ValueError(f"Bank identity is not an unoccupied v2 migration: {transaction_id}")
        after_payload = deepcopy(payload)
        after_payload["normalized_payload"]["source_unique_key"] = after_key
        updates.append({"id": row["id"], "transaction_id": transaction_id,
                        "before_key": before_key, "after_key": after_key,
                        "before_payload": payload, "after_payload": after_payload,
                        "before_updated_at": row["updated_at"]})
    evidence = {"transaction_ids": targets, "rows": [by_id[key] for key in targets]}
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()
    return {"transaction_ids": targets, "source_fingerprint": fingerprint,
            "planned_count": len(updates), "unchanged_count": len(targets) - len(updates),
            "updates": updates,
            "rollback_manifest": {"source_fingerprint": fingerprint, "updates": updates}}
