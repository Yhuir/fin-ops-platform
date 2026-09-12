"""Presentation-only bank folds inside proven relation display areas."""

from copy import deepcopy
from decimal import Decimal
from typing import Any


def apply_bank_folds(groups: list[dict[str, Any]]) -> None:
    for group in groups:
        group.pop("bank_folds", None)
        banks = group.get("bank_rows", [])
        oa = group.get("oa_rows", [])
        if len(banks) < 4 or not group.get("formal_member_ids"):
            continue
        parts = group.get("display_subgroups", [])
        if parts:
            areas = [p["bank_row_ids"] for p in parts if p["resolved"] and p["oa_row_ids"]]
        elif len(oa) <= 1:
            # A single OA or a relation without OA shares its existing bank pane.
            areas = [[r["id"] for r in banks]]
        else:
            continue
        by_id = {r["id"]: r for r in banks}
        folds = []
        for ids in areas:
            if len(ids) < 4:
                continue
            rows = [by_id[k] for k in ids]
            classifications = {(r.get("category_code"), r.get("txn_direction"), r.get("currency")) for r in rows}
            if len(classifications) != 1:
                continue
            code, direction, currency = next(iter(classifications))
            if not code or direction not in ("inflow", "outflow") or not currency:
                continue
            amount = sum((abs(Decimal(str(r["amount"]))) for r in rows), Decimal(0))
            fold_id = f"{group['group_id']}:bank:{min(ids)}"
            summary = deepcopy(rows[0])
            summary.update({
                "id": f"bank_fold_summary:{fold_id}",
                "source_kind": "bank_fold_summary",
                "amount": str(amount),
                "debit_amount": str(amount) if direction == "outflow" else "",
                "credit_amount": str(amount) if direction == "inflow" else "",
                "available_actions": [],
                "special_metadata": {},
            })
            for key, multiple in (("counterparty_name", "多个对方"), ("payment_account_label", "多个账户")):
                if len({r.get(key) for r in rows}) > 1:
                    summary[key] = multiple
            if len({r.get("trade_time") for r in rows}) > 1:
                summary["trade_time"] = ""
            for key in ("bank_text_fields", "remark", "detail_fields", "summary_fields"):
                if any(r.get(key) != rows[0].get(key) for r in rows[1:]):
                    summary[key] = [] if key == "bank_text_fields" else {} if key.endswith("fields") else ""
            folds.append({"fold_id": fold_id, "member_ids": ids, "summary_row": summary})
        if folds:
            group["bank_folds"] = folds
