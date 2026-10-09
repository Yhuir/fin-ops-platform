"""原件票种全池核验，复用 import-audit-repair 的恢复工件合同。"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TextIO

from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.etc_service import parse_etc_xml
from fin_ops_platform.services.import_file_service import parse_invoice_source_rows, read_xlsx_import_rows
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService
from fin_ops_platform.services.invoice_source_attribute_repair import build_source_attribute_repair_plan
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import load_original_invoice_attachments
from fin_ops_platform.services.postgres_repositories.invoice_source_attribute_repair import (
    apply_updates,
    load_etc_originals,
    load_original_files,
    load_snapshot,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository


def read_sources(
    connection: Any, snapshot: list[dict[str, Any]], store: Any
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    files = load_original_files(connection)
    sources, unavailable = [], []
    covered = set()
    identities = InvoiceIdentityService()
    for file in files:
        meta = file["raw_payload"].get("normalized_payload") or file["raw_payload"]
        if meta.get("batch_type") not in ("input_invoice", "output_invoice"):
            continue
        batches = {meta.get("batch_id"), meta.get("preview_batch_id")} - {None, ""}
        ids = [
            item["invoice_id"]
            for item in snapshot
            if any(link.get("batch_id") in batches for link in item["source_links"])
            or (item["raw_payload"].get("normalized_payload") or item["raw_payload"]).get(
                "financial_repair_source_file_id"
            )
            == file["file_id"]
        ]
        if not ids:
            continue
        try:
            content = store.read_import_file(file["stored_file_path"])
            if hashlib.sha256(content).hexdigest() != file["sha256"]:
                raise ValueError("Registered original checksum differs")
            if file["original_filename"].lower().endswith(".xlsx"):
                book = read_xlsx_import_rows(content)
                rows = parse_invoice_source_rows(book.rows)
                for row in rows:
                    row["source_sheet_name"] = book.invoice_header_sheet_name
            else:
                result = OAAttachmentInvoiceService().parse_content_result(
                    {"fileName": file["original_filename"]}, content
                )
                rows = result["evidences"]
            sources.append(
                {
                    "file_id": file["file_id"],
                    "sha256": file["sha256"],
                    "source_kind": "invoice_export"
                    if file["original_filename"].lower().endswith(".xlsx")
                    else "uploaded_invoice",
                    "invoice_ids": ids,
                    "rows": rows,
                }
            )
            row_keys = {identities.canonical_key_for_mapping(row) for row in rows}
            covered.update(
                item["invoice_id"]
                for item in snapshot
                if item["invoice_id"] in ids and identities.canonical_key_for_mapping(item) in row_keys
            )
        except (OSError, ValueError) as exc:
            unavailable.append({"file_id": file["file_id"], "reason": type(exc).__name__})
    for original in load_etc_originals(connection):
        payload = original["raw_payload"].get("normalized_payload") or original["raw_payload"]
        ids = [
            item["invoice_id"]
            for item in snapshot
            if any(
                link.get("source_type") == "etc_invoice_import" and link.get("source_id") == original["etc_invoice_id"]
                for link in item["source_links"]
            )
        ]
        if not ids:
            continue
        try:
            path = payload.get("xml_file_path")
            if not path:
                raise ValueError("ETC original registration missing")
            content = store.read_etc_invoice_file(path)
            if hashlib.sha256(content).hexdigest() != payload.get("xml_file_hash"):
                raise ValueError("ETC original checksum differs")
            parsed = parse_etc_xml(content)
            row = {
                "digital_invoice_no": parsed.invoice_number if len(parsed.invoice_number) == 20 else None,
                "invoice_no": parsed.invoice_number,
                "invoice_code": None,
                "buyer_tax_no": parsed.buyer_tax_no,
                "invoice_kind": parsed.invoice_kind,
                "invoice_date": parsed.issue_date,
            }
            sources.append(
                {
                    "file_id": original["etc_invoice_id"],
                    "sha256": payload["xml_file_hash"],
                    "source_kind": "etc_xml",
                    "invoice_ids": ids,
                    "rows": [row],
                }
            )
            if payload.get("pdf_file_path"):
                pdf = store.read_etc_invoice_file(payload["pdf_file_path"])
                if hashlib.sha256(pdf).hexdigest() != payload.get("pdf_file_hash"):
                    raise ValueError("ETC PDF original checksum differs")
                result = OAAttachmentInvoiceService().parse_content_result({"fileName": "invoice.pdf"}, pdf)
                if result["parse_status"] == "parsed":
                    sources.append(
                        {
                            "file_id": original["etc_invoice_id"] + ":pdf",
                            "sha256": payload["pdf_file_hash"],
                            "source_kind": "etc_pdf",
                            "invoice_ids": ids,
                            "rows": result["evidences"],
                        }
                    )
                else:
                    unavailable.append(
                        {"file_id": original["etc_invoice_id"] + ":pdf", "reason": result["parse_status"]}
                    )
        except (OSError, ValueError) as exc:
            unavailable.append({"file_id": original["etc_invoice_id"], "reason": type(exc).__name__})
    keys: dict[str, list[str]] = {}
    for item in snapshot:
        if item["invoice_id"] in covered:
            continue
        for link in item["source_links"]:
            if key := link.get("source_attachment_key"):
                keys.setdefault(key, []).append(item["invoice_id"])
    attachments = load_original_invoice_attachments(connection, sorted(keys))
    registered = {row["source_attachment_key"] for row in attachments}
    unavailable.extend({"file_id": key, "reason": "registration_missing"} for key in keys.keys() - registered)

    def parse_attachment(attachment):
        parser = OAAttachmentInvoiceService()
        key = attachment["source_attachment_key"]
        try:
            path = attachment["normalized_payload"]["file_path"]
            content = parser._download_content(parser.build_download_url(path))
            if not content:
                return None, {"file_id": key, "reason": "download_failed"}
            result = parser.parse_content_result({"fileName": attachment["filename"], "filePath": path}, content)
            if result["parse_status"] != "parsed":
                return None, {"file_id": key, "reason": result["parse_status"]}
            return {
                "file_id": key,
                "sha256": hashlib.sha256(content).hexdigest(),
                "source_kind": "oa_attachment",
                "invoice_ids": keys[key],
                "rows": result["evidences"],
            }, None
        except (OSError, ValueError) as exc:
            return None, {"file_id": key, "reason": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for source, error in pool.map(parse_attachment, attachments):
            if source:
                sources.append(source)
            if error:
                unavailable.append(error)
    return sources, unavailable


def run(args: Any, *, stdout: TextIO) -> int:
    from fin_ops_platform.tools.import_audit_repair_ops import (
        _argument_is_set,
        _build_bank_repair_state_store,
        _rollback_manifest_fingerprint,
        _verify_private_rollback_manifest,
        _write_private_rollback_manifest,
    )

    allowed = {
        "repair_invoice_source_attributes",
        "dry_run",
        "execute",
        "expected_fingerprint",
        "operator_id",
        "reason",
        "rollback_manifest_path",
    }
    if any(_argument_is_set(value) for key, value in vars(args).items() if key not in allowed):
        raise ValueError("Source attribute repair cannot combine modes")
    if args.execute and not all(
        (args.expected_fingerprint, args.operator_id, args.reason, args.rollback_manifest_path)
    ):
        raise ValueError("Execute requires dry-run fingerprint, operator, reason and recovery artifact")
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as tx:
            tx.execute("set transaction isolation level repeatable read read only")
            snapshot = load_snapshot(tx)
        sources, unavailable = read_sources(connection, snapshot, _build_bank_repair_state_store(connection))

        def plan_for(rows):
            plan = build_source_attribute_repair_plan(rows, sources, unavailable)
            plan["source_fingerprint"] = _rollback_manifest_fingerprint({"snapshot": rows, "sources": sources})
            plan["rollback_manifest"]["source_fingerprint"] = plan["source_fingerprint"]
            plan["rollback_manifest_fingerprint"] = _rollback_manifest_fingerprint(plan["rollback_manifest"])
            return plan

        plan = plan_for(snapshot)
        if args.rollback_manifest_path:
            if args.execute:
                _verify_private_rollback_manifest(args.rollback_manifest_path, plan)
            else:
                _write_private_rollback_manifest(args.rollback_manifest_path, plan)
        if args.execute:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Original or canonical facts changed after dry-run")
            with connection.transaction() as tx:
                current = plan_for(load_snapshot(tx, lock=True))
                if current["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError("Canonical facts changed before write")
                apply_updates(tx, current["updates"])
                if current["updates"]:
                    AuditTrailService(PostgresOperationsAuditRepository(tx)).record_action(
                        actor_id=args.operator_id,
                        action="invoice_source_attribute_repair",
                        entity_type="invoice",
                        entity_id=current["source_fingerprint"],
                        metadata={
                            "event_type": "operation.completed",
                            "page_key": "imports_invoices",
                            "reason": args.reason,
                            "outcome": "success",
                            "invoice_ids": [u["invoice_id"] for u in current["updates"]],
                            "written_invoice_count": current["update_count"],
                        },
                    )
        report = {k: v for k, v in plan.items() if k not in {"updates", "rollback_manifest"}}
        report["mode"] = "execute" if args.execute else "dry_run"
        stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
        return 0
    finally:
        connection.close()
