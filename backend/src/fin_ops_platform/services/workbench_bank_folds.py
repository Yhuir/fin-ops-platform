"""Presentation-only batch and correspondence folds; never changes membership."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

BANK_FOLD_MIN_ROWS = 3


def apply_bank_folds(groups: list[dict[str, Any]]) -> None:
    for group in groups:
        group.pop("bank_folds", None)
        banks = group.get("bank_rows", [])
        oa = group.get("oa_rows", [])
        if len(banks) < BANK_FOLD_MIN_ROWS or not group.get("formal_member_ids"):
            continue
        batches: dict[str, list[str]] = {}
        for row in banks:
            if source := row.get("display_batch_id"):
                batches.setdefault(source, []).append(row["id"])
        batch_members = {member for ids in batches.values() for member in ids}
        parts = group.get("display_subgroups", [])
        if parts:
            areas = [p["bank_row_ids"] for p in parts if p["resolved"] and p["oa_row_ids"]]
        elif len(oa) <= 1:
            # A single OA or a relation without OA shares its existing bank pane.
            areas = [[r["id"] for r in banks]]
        else:
            areas = []
        # Batch provenance is independent of inferred OA ownership. Keep existing
        # correspondence folding for ordinary rows, without absorbing other batches.
        areas = [*batches.values(), *[[k for k in ids if k not in batch_members] for ids in areas]]
        by_id = {r["id"]: r for r in banks}
        folds = []
        for ids in areas:
            if len(ids) < BANK_FOLD_MIN_ROWS:
                continue
            rows = [by_id[k] for k in ids]
            classifications = {(r.get("category_code"), r.get("txn_direction"), r.get("currency")) for r in rows}
            batch_owned = all(k in batch_members for k in ids)
            if not batch_owned and (len(classifications) != 1 or not next(iter(classifications))[0]):
                continue
            totals: dict[tuple[str, str], Decimal] = {}
            for row in rows:
                direction, currency = row.get("txn_direction"), row.get("currency")
                if direction not in ("inflow", "outflow") or not currency:
                    raise ValueError("Bank fold requires canonical currency and direction.")
                key = (direction, currency)
                totals[key] = totals.get(key, Decimal(0)) + abs(Decimal(str(row["amount"])))
            single_total = len(totals) == 1
            direction, currency = next(iter(totals)) if single_total else ("", "")
            amount = str(next(iter(totals.values()))) if single_total else None
            fold_id = f"{group['group_id']}:bank:{min(ids)}"
            summary = deepcopy(rows[0])
            summary.update({
                "id": f"bank_fold_summary:{fold_id}",
                "source_kind": "bank_fold_summary",
                "amount": amount,
                "txn_direction": direction,
                "currency": currency,
                "debit_amount": amount if direction == "outflow" else "",
                "credit_amount": amount if direction == "inflow" else "",
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
            if len({r.get("category_code") for r in rows}) > 1:
                for key in list(summary):
                    if key.startswith("category_"):
                        summary.pop(key)
                summary["tags"] = []
            amount_totals = [{"direction": d, "currency": c, "amount": str(value)} for (d, c), value in totals.items()]
            if not single_total:
                summary["bank_text_fields"] = [{"label": "摘要", "value": "；".join(
                    f"{'收入' if d == 'inflow' else '支出'} {c} {value:.2f}" for (d, c), value in totals.items()
                )}]
            folds.append({"fold_id": fold_id, "member_ids": ids, "summary_row": summary, "amount_totals": amount_totals})
        if folds:
            group["bank_folds"] = folds
