from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb, row_payload


_SUBMITTED_STATUSES = {"submitted", "manually_marked_submitted"}


def preview_summary_repair(executor: Any, business_batch_id: str, *, lock: bool = False) -> dict[str, Any]:
    state = _load_state(executor, business_batch_id, lock=lock)
    return _build_report(state, business_batch_id)


def apply_summary_repair(
    connection: Any,
    business_batch_id: str,
    *,
    expected_fingerprint: str,
    operator: str,
    reason: str,
) -> dict[str, Any]:
    transaction = connection.transaction() if callable(getattr(connection, "transaction", None)) else nullcontext(connection)
    with transaction as executor:
        state = _load_state(executor, business_batch_id, lock=True)
        report = _build_report(state, business_batch_id)
        if report["fingerprint"] != expected_fingerprint:
            raise RuntimeError("ETC business batch summary changed after dry-run.")
        if report["status"] == "already_correct":
            return {**report, "applied": False}
        if report["status"] != "ready":
            raise RuntimeError(f"ETC business batch summary repair is blocked: {report['blocking_reasons']}")

        batch = state["batch"]
        payload = dict(state["payload"])
        audit_events = list(payload.get("audit_events") or [])
        repaired_at = datetime.now(UTC).isoformat()
        next_version = int(batch.get("version") or 0) + 1
        event = {
            "event_id": f"etc_business_audit_{expected_fingerprint[:12]}",
            "event_type": "business_batch_summary_repaired",
            "source": "ops_tool",
            "created_at": repaired_at,
            "before_status": batch.get("status"),
            "after_status": batch.get("status"),
            "actual_version": next_version,
            "business_batch_id": business_batch_id,
            "operator": operator,
            "reason": reason,
            "before_invoice_count": report["stored_invoice_count"],
            "before_total_amount": report["stored_total_amount"],
            "after_invoice_count": report["actual_invoice_count"],
            "after_total_amount": report["actual_total_amount"],
        }
        audit_events.append(event)
        payload.update({"version": next_version, "updated_at": repaired_at, "audit_events": audit_events})
        affected = executor.execute(
            """
            update app.etc_business_batches
            set invoice_count = %s,
                total_amount = %s,
                audit_events = %s,
                version = version + 1,
                raw_payload = %s,
                updated_at = now()
            where business_batch_id = %s and version = %s
            """,
            (
                report["actual_invoice_count"],
                report["actual_total_amount"],
                jsonb(audit_events),
                jsonb({"normalized_payload": payload}),
                business_batch_id,
                batch["version"],
            ),
        )
        if affected != 1:
            raise RuntimeError("ETC business batch version changed during summary repair.")
        executor.execute(
            """
            insert into audit.events(
                event_type, object_type, object_id, actor_id, scope, trace_id, payload, raw_payload
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "etc.business_batch.summary_repaired",
                "etc_business_batch",
                business_batch_id,
                operator,
                "etc_tickets",
                expected_fingerprint,
                jsonb(event),
                jsonb({"normalized_payload": event}),
            ),
        )
        return {**report, "status": "repaired", "applied": True, "new_version": next_version}


def _load_state(executor: Any, business_batch_id: str, *, lock: bool) -> dict[str, Any]:
    batch = executor.fetch_one(
        """
        select business_batch_id, status, invoice_count, total_amount, version, raw_payload
        from app.etc_business_batches
        where business_batch_id = %s
        """
        + (" for update" if lock else ""),
        (business_batch_id,),
    )
    members = executor.fetch_all(
        """
        select etc_invoice_id, total_with_tax
        from app.etc_invoices
        where business_batch_id = %s and status <> 'deleted'
        order by etc_invoice_id
        """,
        (business_batch_id,),
    )
    return {
        "batch": dict(batch or {}),
        "payload": row_payload(batch, "raw_payload") or {},
        "members": [dict(row) for row in members],
    }


def _build_report(state: dict[str, Any], business_batch_id: str) -> dict[str, Any]:
    batch = state["batch"]
    payload = state["payload"]
    members = state["members"]
    blocking_reasons: list[str] = []
    if not batch:
        blocking_reasons.append("business_batch_missing")
    elif batch.get("status") not in _SUBMITTED_STATUSES:
        blocking_reasons.append("business_batch_not_submitted")
    raw_ids = sorted(str(value) for value in list(payload.get("invoice_ids") or []))
    actual_ids = sorted(str(row.get("etc_invoice_id") or "") for row in members)
    if raw_ids != actual_ids:
        blocking_reasons.append("business_batch_member_facts_mismatch")
    actual_total = sum((Decimal(str(row.get("total_with_tax") or "0")) for row in members), Decimal("0"))
    stored_total = Decimal(str(batch.get("total_amount") or "0"))
    evidence = {
        "business_batch_id": business_batch_id,
        "business_batch_version": batch.get("version"),
        "business_batch_status": batch.get("status"),
        "stored_invoice_count": int(batch.get("invoice_count") or 0),
        "stored_total_amount": _money(stored_total),
        "actual_invoice_count": len(members),
        "actual_total_amount": _money(actual_total),
        "raw_invoice_ids": raw_ids,
        "actual_invoice_ids": actual_ids,
        "blocking_reasons": blocking_reasons,
    }
    already_correct = (
        not blocking_reasons
        and evidence["stored_invoice_count"] == evidence["actual_invoice_count"]
        and evidence["stored_total_amount"] == evidence["actual_total_amount"]
    )
    status = "blocked" if blocking_reasons else "already_correct" if already_correct else "ready"
    fingerprint = hashlib.sha256(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**evidence, "status": status, "fingerprint": fingerprint}


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description="Repair one submitted ETC business batch summary.")
    parser.add_argument("--business-batch-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(list(argv or sys.argv[1:]))
    if args.execute and not all((args.expected_fingerprint.strip(), args.operator.strip(), args.reason.strip())):
        parser.error("--execute requires --expected-fingerprint, --operator, and --reason")

    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        report = (
            apply_summary_repair(
                connection,
                args.business_batch_id,
                expected_fingerprint=args.expected_fingerprint.strip(),
                operator=args.operator.strip(),
                reason=args.reason.strip(),
            )
            if args.execute
            else preview_summary_repair(connection, args.business_batch_id)
        )
    except (RuntimeError, ValueError) as exc:
        report = {"status": "blocked", "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report.get("status") in {"ready", "already_correct", "repaired"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
