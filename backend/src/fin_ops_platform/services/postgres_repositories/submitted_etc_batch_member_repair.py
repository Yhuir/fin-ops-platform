from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb, row_payload
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository

_SUBMITTED_BUSINESS_BATCH_STATUSES = {"oa_submitted", "manually_marked_submitted", "closed"}


class SubmittedEtcBatchMemberRepairRepository:
    """Fail-closed maintenance boundary for one already-submitted ETC batch."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview(
        self,
        *,
        business_batch_id: str,
        submission_batch_id: str,
        external_etc_batch_id: str,
        invoice_specs: list[dict[str, str]],
        expected_target_total: Decimal,
        expected_result_count: int,
        expected_result_total: Decimal,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot(
            self._connection,
            business_batch_id=business_batch_id,
            submission_batch_id=submission_batch_id,
            invoice_numbers=[spec["invoice_number"] for spec in invoice_specs],
            lock=False,
        )
        return build_submitted_etc_batch_member_repair_plan(
            snapshot,
            business_batch_id=business_batch_id,
            submission_batch_id=submission_batch_id,
            external_etc_batch_id=external_etc_batch_id,
            invoice_specs=invoice_specs,
            expected_target_total=expected_target_total,
            expected_result_count=expected_result_count,
            expected_result_total=expected_result_total,
        )

    def apply(
        self,
        *,
        business_batch_id: str,
        submission_batch_id: str,
        external_etc_batch_id: str,
        invoice_specs: list[dict[str, str]],
        expected_target_total: Decimal,
        expected_result_count: int,
        expected_result_total: Decimal,
        expected_fingerprint: str,
        operator: str,
        reason: str,
    ) -> dict[str, Any]:
        normalized_operator = str(operator or "").strip()
        normalized_reason = str(reason or "").strip()
        if not normalized_operator or not normalized_reason:
            raise ValueError("operator and reason are required")

        with self._connection.transaction() as transaction:
            transaction.fetch_one(
                """
                select
                    pg_advisory_xact_lock(hashtextextended(%s, 0)),
                    pg_advisory_xact_lock(hashtextextended('etc_invoice_id_allocator', 0))
                """,
                (f"submitted_etc_batch_member_repair:{business_batch_id}",),
            )
            snapshot = self._load_snapshot(
                transaction,
                business_batch_id=business_batch_id,
                submission_batch_id=submission_batch_id,
                invoice_numbers=[spec["invoice_number"] for spec in invoice_specs],
                lock=True,
            )
            plan = build_submitted_etc_batch_member_repair_plan(
                snapshot,
                business_batch_id=business_batch_id,
                submission_batch_id=submission_batch_id,
                external_etc_batch_id=external_etc_batch_id,
                invoice_specs=invoice_specs,
                expected_target_total=expected_target_total,
                expected_result_count=expected_result_count,
                expected_result_total=expected_result_total,
            )
            if plan["fingerprint"] != str(expected_fingerprint or "").strip():
                raise ValueError("fingerprint_mismatch")
            if plan["status"] == "already_repaired":
                return {**plan, "applied": False, "updated_count": 0}
            if plan["status"] != "ready":
                raise ValueError(f"repair_not_ready:{','.join(plan['blocking_reasons'])}")

            now_row = transaction.fetch_one("select now()::text as value") or {}
            repaired_at = str(now_row.get("value") or "")
            target_by_number = {
                str(row["invoice_number"]): row for row in snapshot["canonical_targets"]
            }
            created_invoice_ids: list[str] = []
            core_repository = PostgresCoreRepository(transaction)
            for item in plan["planned_invoices"]:
                invoice_number = str(item["invoice_number"])
                canonical = target_by_number[invoice_number]
                etc_invoice_id = str(item["etc_invoice_id"])
                payload = _new_etc_invoice_payload(
                    canonical,
                    etc_invoice_id=etc_invoice_id,
                    submission_batch_id=submission_batch_id,
                    business_batch_id=business_batch_id,
                    task_id=str(snapshot["business_batch"]["task_id"]),
                    plate_number=str(item["plate_number"]),
                    repaired_at=repaired_at,
                )
                inserted = transaction.execute(
                    """
                    insert into app.etc_invoices(
                        legacy_mongo_id, etc_invoice_id, invoice_no, invoice_code, invoice_date,
                        scope_month, seller_name, buyer_name, amount, tax_amount, total_with_tax,
                        status, batch_id, task_id, business_batch_id, version, raw_payload
                    )
                    values (
                        %s, %s, %s, %s, %s::date,
                        date_trunc('month', %s::date)::date, %s, %s, %s, %s, %s,
                        'submitted', %s, %s, %s, 1, %s
                    )
                    """,
                    (
                        etc_invoice_id,
                        etc_invoice_id,
                        invoice_number,
                        canonical.get("invoice_code"),
                        canonical.get("invoice_date"),
                        canonical.get("invoice_date"),
                        canonical.get("seller_name"),
                        canonical.get("buyer_name"),
                        canonical.get("amount"),
                        canonical.get("tax_amount"),
                        canonical.get("total_with_tax"),
                        submission_batch_id,
                        snapshot["business_batch"]["task_id"],
                        business_batch_id,
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                if inserted != 1:
                    raise RuntimeError(f"failed to insert ETC invoice {invoice_number}")
                link = core_repository.upsert_etc_batch_invoice_link(
                    invoice_id=str(canonical["invoice_id"]),
                    business_batch_id=business_batch_id,
                    etc_invoice_id=etc_invoice_id,
                    invoice_no=invoice_number,
                    invoice_code=canonical.get("invoice_code"),
                    digital_invoice_no=canonical.get("digital_invoice_no"),
                    invoice_date=str(canonical.get("invoice_date") or ""),
                    link_source="submitted_batch_member_repair",
                    confidence="strict",
                    raw_payload={
                        "repair_reason": normalized_reason,
                        "operator": normalized_operator,
                        "submission_batch_id": submission_batch_id,
                    },
                )
                if not link:
                    raise RuntimeError(f"failed to link canonical invoice {invoice_number}")
                updated = core_repository.repair_submitted_etc_invoice_overlap(
                    invoice_id=str(canonical["invoice_id"]),
                    etc_invoice_id=etc_invoice_id,
                    etc_batch_id=submission_batch_id,
                    reason=normalized_reason,
                    operator=normalized_operator,
                )
                if updated != 1:
                    raise RuntimeError(f"canonical invoice changed during repair: {invoice_number}")
                created_invoice_ids.append(etc_invoice_id)

            all_invoice_rows = list(snapshot["current_etc_invoices"]) + [
                {
                    "etc_invoice_id": item["etc_invoice_id"],
                    "invoice_number": item["invoice_number"],
                    "invoice_date": target_by_number[str(item["invoice_number"])]["invoice_date"],
                    "amount": target_by_number[str(item["invoice_number"])]["amount"],
                    "tax_amount": target_by_number[str(item["invoice_number"])]["tax_amount"],
                    "total_with_tax": target_by_number[str(item["invoice_number"])]["total_with_tax"],
                    "plate_number": item["plate_number"],
                }
                for item in plan["planned_invoices"]
            ]
            all_invoice_rows.sort(key=lambda row: str(row["etc_invoice_id"]))
            all_invoice_ids = [str(row["etc_invoice_id"]) for row in all_invoice_rows]
            plate_summary = _plate_summary(all_invoice_rows)
            issue_dates = sorted(
                str(row.get("invoice_date") or "")[:10]
                for row in all_invoice_rows
                if str(row.get("invoice_date") or "").strip()
            )
            self._update_submission_batch(
                transaction,
                snapshot=snapshot,
                invoice_ids=all_invoice_ids,
                plate_summary=plate_summary,
                issue_dates=issue_dates,
                expected_result_count=expected_result_count,
                expected_result_total=expected_result_total,
            )
            self._update_business_batch(
                transaction,
                snapshot=snapshot,
                invoice_ids=all_invoice_ids,
                expected_result_count=expected_result_count,
                expected_result_total=expected_result_total,
                operator=normalized_operator,
                reason=normalized_reason,
                repaired_at=repaired_at,
            )

            post_snapshot = self._load_snapshot(
                transaction,
                business_batch_id=business_batch_id,
                submission_batch_id=submission_batch_id,
                invoice_numbers=[spec["invoice_number"] for spec in invoice_specs],
                lock=True,
            )
            post_plan = build_submitted_etc_batch_member_repair_plan(
                post_snapshot,
                business_batch_id=business_batch_id,
                submission_batch_id=submission_batch_id,
                external_etc_batch_id=external_etc_batch_id,
                invoice_specs=invoice_specs,
                expected_target_total=expected_target_total,
                expected_result_count=expected_result_count,
                expected_result_total=expected_result_total,
            )
            if post_plan["status"] != "already_repaired":
                raise RuntimeError(f"repair postcondition failed: {post_plan['blocking_reasons']}")
            return {
                **post_plan,
                "applied": True,
                "updated_count": len(created_invoice_ids),
                "created_etc_invoice_ids": created_invoice_ids,
                "pre_apply_fingerprint": plan["fingerprint"],
            }

    def _load_snapshot(
        self,
        executor: Any,
        *,
        business_batch_id: str,
        submission_batch_id: str,
        invoice_numbers: list[str],
        lock: bool,
    ) -> dict[str, Any]:
        lock_sql = " for update" if lock else ""
        business_batch = executor.fetch_one(
            """
            select business_batch_id, task_id, status, scope_month::text as scope_month,
                   invoice_count, total_amount, version, raw_payload, audit_events
            from app.etc_business_batches
            where business_batch_id = %s
            """
            + lock_sql,
            (business_batch_id,),
        )
        submission_batch = executor.fetch_one(
            """
            select submission_batch_id, status, scope_month::text as scope_month,
                   invoice_ids, version, raw_payload
            from app.etc_submission_batches
            where submission_batch_id = %s
            """
            + lock_sql,
            (submission_batch_id,),
        )
        task_id = str((business_batch or {}).get("task_id") or "")
        reconciliation_task = (
            executor.fetch_one(
                """
                select task_id, status, result_summary, version, raw_payload
                from app.etc_reconciliation_tasks
                where task_id = %s
                """
                + (" for key share" if lock else ""),
                (task_id,),
            )
            if task_id
            else None
        )
        canonical_targets = executor.fetch_all(
            """
            select id::text as invoice_id,
                   coalesce(legacy_mongo_id, id::text) as legacy_invoice_id,
                   invoice_no as invoice_number, invoice_code, digital_invoice_no,
                   invoice_date::text as invoice_date, seller_name, seller_tax_no,
                   buyer_name, buyer_tax_no, amount, tax_amount, total_with_tax,
                   status, etc_invoice_id, workbench_visibility, raw_payload
            from app.invoices
            where coalesce(digital_invoice_no, invoice_no) = any(%s)
              and invoice_type = 'input'
              and status <> 'deleted'
            order by coalesce(digital_invoice_no, invoice_no), id
            """
            + lock_sql,
            (invoice_numbers,),
        )
        current_etc_invoices = executor.fetch_all(
            """
            select etc_invoice_id, invoice_no as invoice_number, invoice_date::text as invoice_date,
                   amount, tax_amount, total_with_tax,
                   nullif(raw_payload->'normalized_payload'->>'plate_number', '') as plate_number
            from app.etc_invoices
            where business_batch_id = %s and status <> 'deleted'
            order by etc_invoice_id
            """
            + lock_sql,
            (business_batch_id,),
        )
        target_etc_invoices = executor.fetch_all(
            """
            select etc_invoice_id, invoice_no as invoice_number, invoice_date::text as invoice_date,
                   amount, tax_amount, total_with_tax, status, batch_id, business_batch_id
            from app.etc_invoices
            where invoice_no = any(%s) and status <> 'deleted'
            order by invoice_no, etc_invoice_id
            """
            + lock_sql,
            (invoice_numbers,),
        )
        invoice_ids = [str(row["invoice_id"]) for row in canonical_targets]
        active_links = (
            executor.fetch_all(
                """
                select invoice_id::text as invoice_id, business_batch_id, etc_invoice_id,
                       identity_key, invoice_no, confidence, link_source
                from app.etc_batch_invoice_links
                where invoice_id::text = any(%s) and link_status = 'active'
                order by invoice_id, business_batch_id
                """
                + lock_sql,
                (invoice_ids,),
            )
            if invoice_ids
            else []
        )
        max_row = executor.fetch_one(
            """
            select coalesce(max((substring(etc_invoice_id from '([0-9]+)$'))::integer), 0) as value
            from app.etc_invoices
            """
        )
        return {
            "business_batch": _row_with_payload(business_batch),
            "submission_batch": _row_with_payload(submission_batch),
            "reconciliation_task": _row_with_payload(reconciliation_task),
            "canonical_targets": [_canonical_row(row) for row in canonical_targets],
            "current_etc_invoices": [dict(row) for row in current_etc_invoices],
            "target_etc_invoices": [dict(row) for row in target_etc_invoices],
            "active_links": [dict(row) for row in active_links],
            "max_etc_invoice_counter": int((max_row or {}).get("value") or 0),
        }

    @staticmethod
    def _update_submission_batch(
        transaction: Any,
        *,
        snapshot: dict[str, Any],
        invoice_ids: list[str],
        plate_summary: list[dict[str, object]],
        issue_dates: list[str],
        expected_result_count: int,
        expected_result_total: Decimal,
    ) -> None:
        row = snapshot["submission_batch"]
        payload = dict(row["payload"])
        payload.update(
            {
                "invoice_ids": invoice_ids,
                "invoice_count": expected_result_count,
                "etc_invoice_count": expected_result_count,
                "total_amount": _money(expected_result_total),
                "oa_total_amount": _money(expected_result_total),
                "etc_invoice_amount": _money(expected_result_total),
                "plate_summary": plate_summary,
                "issue_start_date": issue_dates[0] if issue_dates else None,
                "issue_end_date": issue_dates[-1] if issue_dates else None,
            }
        )
        affected = transaction.execute(
            """
            update app.etc_submission_batches
            set invoice_ids = %s,
                version = version + 1,
                raw_payload = %s,
                updated_at = now()
            where submission_batch_id = %s and version = %s
            """,
            (
                invoice_ids,
                jsonb({"normalized_payload": payload}),
                row["submission_batch_id"],
                row["version"],
            ),
        )
        if affected != 1:
            raise RuntimeError("submission batch version changed during repair")

    @staticmethod
    def _update_business_batch(
        transaction: Any,
        *,
        snapshot: dict[str, Any],
        invoice_ids: list[str],
        expected_result_count: int,
        expected_result_total: Decimal,
        operator: str,
        reason: str,
        repaired_at: str,
    ) -> None:
        row = snapshot["business_batch"]
        payload = dict(row["payload"])
        audit_events = list(payload.get("audit_events") or [])
        event_key = f"{row['business_batch_id']}:{row['version']}:{','.join(invoice_ids)}:{operator}:{reason}"
        event = {
            "event_id": f"etc_business_audit_{hashlib.sha256(event_key.encode()).hexdigest()[:12]}",
            "event_type": "submitted_batch_members_repaired",
            "source": "ops_tool",
            "created_at": repaired_at,
            "before_status": row["status"],
            "after_status": row["status"],
            "actual_version": int(row["version"]) + 1,
            "business_batch_id": row["business_batch_id"],
            "submission_batch_id": payload.get("submission_batch_id"),
            "external_etc_batch_id": payload.get("external_etc_batch_id"),
            "task_id": row.get("task_id"),
            "operator": operator,
            "reason": reason,
        }
        audit_events.append(event)
        payload.update(
            {
                "invoice_ids": invoice_ids,
                "version": int(row["version"]) + 1,
                "updated_at": repaired_at,
                "audit_events": audit_events,
            }
        )
        affected = transaction.execute(
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
                expected_result_count,
                _money(expected_result_total),
                jsonb(audit_events),
                jsonb({"normalized_payload": payload}),
                row["business_batch_id"],
                row["version"],
            ),
        )
        if affected != 1:
            raise RuntimeError("business batch version changed during repair")


def build_submitted_etc_batch_member_repair_plan(
    snapshot: dict[str, Any],
    *,
    business_batch_id: str,
    submission_batch_id: str,
    external_etc_batch_id: str,
    invoice_specs: list[dict[str, str]],
    expected_target_total: Decimal,
    expected_result_count: int,
    expected_result_total: Decimal,
) -> dict[str, Any]:
    reasons: list[str] = []
    business = snapshot.get("business_batch") or {}
    submission = snapshot.get("submission_batch") or {}
    task = snapshot.get("reconciliation_task") or {}
    canonical_rows = list(snapshot.get("canonical_targets") or [])
    current_rows = list(snapshot.get("current_etc_invoices") or [])
    target_etc_rows = list(snapshot.get("target_etc_invoices") or [])
    active_links = list(snapshot.get("active_links") or [])
    invoice_numbers = [spec["invoice_number"] for spec in invoice_specs]
    spec_by_number = {spec["invoice_number"]: spec for spec in invoice_specs}

    if not business:
        reasons.append("business_batch_missing")
    if not submission:
        reasons.append("submission_batch_missing")
    if business and business.get("status") not in _SUBMITTED_BUSINESS_BATCH_STATUSES:
        reasons.append("business_batch_not_submitted")
    if submission and submission.get("status") != "submitted_confirmed":
        reasons.append("submission_batch_not_submitted")
    business_payload = business.get("payload") if isinstance(business.get("payload"), dict) else {}
    submission_payload = submission.get("payload") if isinstance(submission.get("payload"), dict) else {}
    if business_payload.get("submission_batch_id") != submission_batch_id:
        reasons.append("business_submission_batch_mismatch")
    if business_payload.get("external_etc_batch_id") != external_etc_batch_id:
        reasons.append("external_etc_batch_mismatch")
    if submission_payload.get("etc_batch_id") != external_etc_batch_id:
        reasons.append("submission_external_etc_batch_mismatch")
    if business_payload.get("oa_draft_id") != submission_payload.get("oa_draft_id"):
        reasons.append("oa_draft_identity_mismatch")
    if not task or task.get("status") != "closed":
        reasons.append("reconciliation_task_not_closed")
    task_summary = task.get("result_summary") if isinstance(task.get("result_summary"), dict) else {}
    if int(task_summary.get("etc_invoice_count") or 0) != expected_result_count:
        reasons.append("reconciliation_task_count_mismatch")
    if _decimal(task_summary.get("etc_invoice_amount")) != expected_result_total:
        reasons.append("reconciliation_task_total_mismatch")

    rows_by_number: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_rows:
        rows_by_number.setdefault(str(row.get("invoice_number") or ""), []).append(row)
    if set(rows_by_number) != set(invoice_numbers) or any(len(rows_by_number[number]) != 1 for number in invoice_numbers):
        reasons.append("canonical_invoice_identity_not_unique")
    target_total = sum((_decimal(row.get("total_with_tax")) for row in canonical_rows), Decimal("0"))
    if target_total != expected_target_total:
        reasons.append("target_invoice_total_mismatch")

    current_ids = [str(row.get("etc_invoice_id") or "") for row in current_rows]
    business_ids = [str(value) for value in list(business_payload.get("invoice_ids") or [])]
    submission_ids = [str(value) for value in list(submission.get("invoice_ids") or [])]
    submission_payload_ids = [str(value) for value in list(submission_payload.get("invoice_ids") or [])]
    if sorted(current_ids) != sorted(business_ids):
        reasons.append("business_member_facts_mismatch")
    if sorted(current_ids) != sorted(submission_ids) or sorted(current_ids) != sorted(submission_payload_ids):
        reasons.append("submission_member_facts_mismatch")

    current_total = sum((_decimal(row.get("total_with_tax")) for row in current_rows), Decimal("0"))
    target_etc_by_number = {
        str(row.get("invoice_number") or ""): row for row in target_etc_rows
    }
    link_by_invoice_id = {
        str(row.get("invoice_id") or ""): row for row in active_links
    }
    fully_repaired = bool(canonical_rows) and all(
        (
            str(row.get("etc_invoice_id") or "")
            and row.get("workbench_visibility") == "hidden_after_etc_submission"
            and str(row.get("invoice_number") or "") in target_etc_by_number
            and target_etc_by_number[str(row.get("invoice_number"))].get("business_batch_id")
            == business_batch_id
            and link_by_invoice_id.get(str(row.get("invoice_id") or ""), {}).get("business_batch_id")
            == business_batch_id
        )
        for row in canonical_rows
    )
    any_repaired = bool(target_etc_rows or active_links) or any(
        str(row.get("etc_invoice_id") or "") or row.get("workbench_visibility") != "visible"
        for row in canonical_rows
    )
    if any_repaired and not fully_repaired:
        reasons.append("partial_repair_state")

    if fully_repaired:
        if len(current_rows) != expected_result_count or current_total != expected_result_total:
            reasons.append("repaired_result_mismatch")
    else:
        if len(current_rows) + len(invoice_specs) != expected_result_count:
            reasons.append("result_invoice_count_mismatch")
        if current_total + expected_target_total != expected_result_total:
            reasons.append("result_invoice_total_mismatch")
        for row in canonical_rows:
            if row.get("status") == "deleted":
                reasons.append("canonical_invoice_deleted")
            if row.get("workbench_visibility") != "visible" or str(row.get("etc_invoice_id") or ""):
                reasons.append("canonical_invoice_not_available")

    if business and (
        int(business.get("invoice_count") or 0) != expected_result_count
        or _decimal(business.get("total_amount")) != expected_result_total
    ):
        reasons.append("business_control_summary_mismatch")

    next_counter = int(snapshot.get("max_etc_invoice_counter") or 0)
    planned_invoices = []
    for offset, number in enumerate(invoice_numbers, start=1):
        row = rows_by_number.get(number, [{}])[0]
        planned_invoices.append(
            {
                "invoice_number": number,
                "plate_number": spec_by_number[number]["plate_number"],
                "canonical_invoice_id": row.get("invoice_id"),
                "total_with_tax": _money(_decimal(row.get("total_with_tax"))),
                "etc_invoice_id": (
                    str(row.get("etc_invoice_id"))
                    if fully_repaired
                    else f"etc_invoice_{next_counter + offset:04d}"
                ),
            }
        )

    status = "blocked" if reasons else ("already_repaired" if fully_repaired else "ready")
    evidence = {
        "business_batch_id": business_batch_id,
        "submission_batch_id": submission_batch_id,
        "external_etc_batch_id": external_etc_batch_id,
        "business_batch_version": business.get("version"),
        "submission_batch_version": submission.get("version"),
        "reconciliation_task_id": task.get("task_id"),
        "reconciliation_task_version": task.get("version"),
        "oa_draft_id": business_payload.get("oa_draft_id"),
        "current_invoice_ids": current_ids,
        "current_invoice_count": len(current_rows),
        "current_invoice_total": _money(current_total),
        "target_invoice_numbers": invoice_numbers,
        "target_invoice_total": _money(target_total),
        "planned_invoices": planned_invoices,
        "expected_result_count": expected_result_count,
        "expected_result_total": _money(expected_result_total),
        "business_raw_hash": _payload_hash(business.get("raw_payload")),
        "submission_raw_hash": _payload_hash(submission.get("raw_payload")),
        "reconciliation_task_raw_hash": _payload_hash(task.get("raw_payload")),
        "status": status,
        "blocking_reasons": sorted(set(reasons)),
    }
    return {
        **evidence,
        "fingerprint": _payload_hash(evidence),
        "scope_months": sorted(
            {
                str(value)[:7]
                for value in [
                    business.get("scope_month"),
                    *(row.get("invoice_date") for row in canonical_rows),
                ]
                if str(value or "").strip()
            }
        ),
    }


def _new_etc_invoice_payload(
    canonical: dict[str, Any],
    *,
    etc_invoice_id: str,
    submission_batch_id: str,
    business_batch_id: str,
    task_id: str,
    plate_number: str,
    repaired_at: str,
) -> dict[str, Any]:
    return {
        "id": etc_invoice_id,
        "invoice_number": canonical["invoice_number"],
        "issue_date": canonical["invoice_date"],
        "passage_start_date": None,
        "passage_end_date": None,
        "plate_number": plate_number,
        "vehicle_type": None,
        "seller_name": canonical.get("seller_name"),
        "seller_tax_no": canonical.get("seller_tax_no"),
        "buyer_name": canonical.get("buyer_name"),
        "buyer_tax_no": canonical.get("buyer_tax_no"),
        "amount_without_tax": _money(_decimal(canonical.get("amount"))),
        "tax_amount": _money(_decimal(canonical.get("tax_amount"))),
        "total_amount": _money(_decimal(canonical.get("total_with_tax"))),
        "tax_rate": canonical.get("tax_rate"),
        "zip_source_name": f"canonical_invoice:{canonical['legacy_invoice_id']}",
        "xml_file_path": None,
        "xml_file_hash": None,
        "pdf_file_path": None,
        "pdf_file_hash": None,
        "status": "submitted",
        "import_batch_id": None,
        "import_session_id": None,
        "business_batch_id": business_batch_id,
        "current_batch_id": submission_batch_id,
        "last_batch_id": submission_batch_id,
        "task_id": task_id,
        "created_at": repaired_at,
        "updated_at": repaired_at,
    }


def _plate_summary(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        plate = str(row.get("plate_number") or "").strip() or "未识别车牌"
        entry = grouped.setdefault(
            plate,
            {"plate_number": plate, "invoice_count": 0, "total_amount": Decimal("0")},
        )
        entry["invoice_count"] = int(entry["invoice_count"]) + 1
        entry["total_amount"] = _decimal(entry["total_amount"]) + _decimal(row.get("total_with_tax"))
    return [
        {
            "plate_number": plate,
            "invoice_count": int(payload["invoice_count"]),
            "total_amount": _money(_decimal(payload["total_amount"])),
        }
        for plate, payload in sorted(grouped.items())
    ]


def _row_with_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    result = dict(row)
    result["payload"] = row_payload(row, "raw_payload") or {}
    return result


def _canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    payload = row_payload(row, "raw_payload")
    result["tax_rate"] = (payload or {}).get("tax_rate")
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
