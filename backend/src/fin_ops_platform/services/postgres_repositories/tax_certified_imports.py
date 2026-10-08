from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.postgres_repositories.common import jsonb, row_payload, run_in_transaction, serialize_value
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.tax_offset import SPECIAL_INVOICE_KINDS, PostgresTaxOffsetCanonicalRepository

BATCH_FIELDS = ("id", "session_id", "imported_by", "file_count", "months", "persisted_record_count", "duplicate_count",
                "status", "version", "created_at", "revoked_record_count", "restored_record_count", "revoked_at")
RECORD_FIELDS = ("id", "unique_key", "month", "source_file_name", "source_row_number", "buyer_tax_no", "digital_invoice_no",
                 "invoice_code", "invoice_no", "issue_date", "selection_time", "amount", "tax_amount", "deductible_tax_amount",
                 "invoice_kind_label", "batch_id", "seller_name", "seller_tax_no")


def public_batch(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in BATCH_FIELDS if key in payload}


FACT_FIELDS = ("month", "buyer_tax_no", "digital_invoice_no", "invoice_code", "invoice_no", "issue_date",
               "seller_tax_no", "seller_name", "amount", "tax_amount", "deductible_tax_amount", "selection_status",
               "invoice_status", "selection_time", "invoice_source", "invoice_kind", "invoice_kind_label", "risk_level",
               "risk_status", "domestic_sales_certificate_no")


def same_facts(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in FACT_FIELDS:
        a, b = left.get(key), right.get(key)
        if key in {"amount", "tax_amount", "deductible_tax_amount"} and a is not None and b is not None:
            if Decimal(str(a)) != Decimal(str(b)):
                return False
        elif a != b:
            return False
    return True


class TaxCertifiedImportConflict(ValueError):
    pass


class PostgresTaxCertifiedImportRepository:
    """Targeted certification commands; source sessions and batches remain immutable evidence."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def save_session(self, session: Any) -> None:
        payload = serialize_value(session)
        self._connection.execute("""
            INSERT INTO app.tax_certified_import_sessions(session_id,status,imported_by,record_count,raw_payload)
            VALUES (%s,%s,%s,%s,%s)
        """, (session.id, session.status, session.imported_by,
              sum(file.recognized_count for file in session.files), jsonb({"normalized_payload": payload})))

    def get_session(self, session_id: str) -> Any:
        row = self._connection.fetch_one("SELECT raw_payload FROM app.tax_certified_import_sessions WHERE session_id=%s", (session_id,))
        if row is None:
            raise KeyError(session_id)
        return SimpleNamespace(**row_payload(row))

    @staticmethod
    def _current(connection: Any, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not rows:
            return {}
        records = connection.fetch_all("""
            SELECT certified_unique_key, raw_payload, version, status, invoice_id::text AS invoice_id, buyer_tax_no,
                   deductible_tax_amount::text AS deductible_tax_amount, selection_time::text AS selection_time,
                   invoice_kind_label,match_status
            FROM app.tax_certified_import_records WHERE certified_unique_key=ANY(%s::text[])
        """, (list({row["unique_key"] for row in rows}),))
        return {row["certified_unique_key"]: {"buyer_tax_no": row["buyer_tax_no"],
                    "deductible_tax_amount": row["deductible_tax_amount"], "selection_time": row["selection_time"],
                    "invoice_kind_label": row["invoice_kind_label"], **(row_payload(row) or {}),
                    "version": row["version"], "status": row["status"], "matched_invoice_id": row["invoice_id"],
                    "match_status": row["match_status"]} for row in records}


    @staticmethod
    def _match_errors(connection: Any, rows: list[dict[str, Any]], matches: dict[str, dict[str, Any]], *,
                      lock_invoices: bool = False) -> dict[str, str]:
        invoice_ids = sorted({match["matched_invoice_id"] for match in matches.values() if match["matched_invoice_id"]})
        facts = connection.fetch_all("""SELECT i.id::text AS invoice_id,i.amount,i.tax_amount,i.digital_invoice_no,
                i.invoice_code,i.invoice_no,i.buyer_tax_no,i.status,i.invoice_type,c.certified_unique_key,
                replace(replace(btrim(coalesce(i.raw_payload->'normalized_payload',i.raw_payload)->>'invoice_kind'),'（','('),'）',')') AS invoice_kind
            FROM app.invoices i LEFT JOIN app.tax_certified_import_records c ON c.invoice_id=i.id AND c.status='active'
            WHERE i.id=ANY(%s::uuid[])""" + (" FOR SHARE OF i" if lock_invoices else ""), (invoice_ids,)) if invoice_ids else []
        by_id = {row["invoice_id"]: row for row in facts}
        errors: dict[str, str] = {}
        seen_sources: dict[str, dict[str, Any]] = {}
        seen = {}
        for row in rows:
            key = row["unique_key"]
            if key in seen_sources and not same_facts(seen_sources[key], row):
                errors[key] = "同一导入批次含相同标识的冲突认证记录。"
            seen_sources[key] = row
            match = matches[key]
            if match["match_status"] == "ambiguous":
                errors[key] = "发票身份匹配不唯一。"
                continue
            invoice_id = match["matched_invoice_id"]
            if invoice_id is None:
                continue
            canonical = by_id.get(invoice_id)
            if (canonical is None or canonical["status"] == "deleted" or canonical["invoice_type"] != "input"
                    or canonical["invoice_kind"] not in SPECIAL_INVOICE_KINDS or canonical["buyer_tax_no"] != row.get("buyer_tax_no")):
                errors[key] = "发票池身份或状态已变化，请重新预览。"
                continue
            if canonical["certified_unique_key"] and canonical["certified_unique_key"] != key:
                errors[key] = "同一发票已由其他认证标识占用，请先核对并撤销原批次。"
            if invoice_id in seen and seen[invoice_id] != key:
                errors[key] = errors[seen[invoice_id]] = "多条不同认证标识指向同一发票。"
            seen[invoice_id] = key
            for field, label in (("digital_invoice_no", "数电发票号码"), ("invoice_code", "发票代码"), ("invoice_no", "发票号码")):
                if row.get(field) and canonical[field] and row[field] != canonical[field]:
                    errors[key] = f"认证文件{label}与发票池身份不一致。"
            for field, label in (("amount", "金额"), ("tax_amount", "税额")):
                if row.get(field) is not None and canonical[field] is not None and Decimal(str(row[field])) != canonical[field]:
                    errors[key] = f"认证文件{label}与发票池不一致。"
        return errors

    def classify_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        matches = PostgresTaxOffsetCanonicalRepository(self._connection).match_certified_rows(rows)
        current = self._current(self._connection, rows)
        errors = self._match_errors(self._connection, rows, matches)
        for row in rows:
            key = row["unique_key"]
            old = current.get(key)
            matches[key].update(dedupe_status="duplicate" if old and old["status"] == "active" and same_facts(old, row)
                                else "conflict" if old and old["status"] == "active" else "new",
                                expected_version=old["version"] if old else 0,
                                blocking=key in errors, error_message=errors.get(key))
        return matches

    def confirm_session(self, session_id: str, *, actor_id: str, corrections: list[dict[str, Any]]) -> dict[str, Any]:
        return run_in_transaction(self._connection, lambda tx: self._confirm(tx, session_id, actor_id, corrections))

    def _confirm(self, tx: Any, session_id: str, actor_id: str, corrections: list[dict[str, Any]]) -> dict[str, Any]:
        tx.execute("SELECT pg_advisory_xact_lock(hashtext('tax-certified-import'))")
        session_row = tx.fetch_one("SELECT id,imported_by,raw_payload FROM app.tax_certified_import_sessions WHERE session_id=%s FOR UPDATE", (session_id,))
        if session_row is None:
            raise KeyError(session_id)
        if session_row["imported_by"] != actor_id:
            raise PermissionError("不能确认其他用户的认证导入。")
        existing = tx.fetch_one("SELECT raw_payload,status,version FROM app.tax_certified_import_batches WHERE session_id=%s", (session_row["id"],))
        if existing:
            return public_batch({**row_payload(existing), "status": existing["status"], "version": existing["version"]})
        session = row_payload(session_row)
        rows_by_key: dict[str, dict[str, Any]] = {}
        for file in session["files"]:
            for row in file["rows"]:
                old = rows_by_key.get(row["unique_key"])
                if old and not same_facts(old, row):
                    raise TaxCertifiedImportConflict("同一文件批次含冲突认证记录，请更正来源文件。")
                rows_by_key[row["unique_key"]] = row
        rows = list(rows_by_key.values())
        if not rows:
            raise ValueError("没有可导入的专票认证记录。")
        correction_map = {}
        for correction in corrections:
            if (not isinstance(correction, dict) or set(correction) != {"unique_key", "expected_version"}
                    or not isinstance(correction["unique_key"], str)
                    or type(correction["expected_version"]) is not int or correction["expected_version"] < 1):
                raise ValueError("更正必须包含认证标识和有效版本。")
            if correction["unique_key"] in correction_map:
                raise ValueError("重复的更正记录。")
            correction_map[correction["unique_key"]] = correction["expected_version"]
        if set(correction_map) - set(rows_by_key):
            raise ValueError("更正记录不属于此导入。")
        matches = PostgresTaxOffsetCanonicalRepository(tx).match_certified_rows(rows)
        errors = self._match_errors(tx, rows, matches, lock_invoices=True)
        if errors:
            raise TaxCertifiedImportConflict(next(iter(errors.values())))
        current = self._current(tx, rows)
        batch_id = f"tax-certified-batch-{uuid4().hex}"
        changed, duplicates, before, links = [], 0, [], []
        invoice_ids = set()
        for source in rows:
            row = deepcopy(source)
            key = row["unique_key"]
            match = matches[key]
            if match["match_status"] == "ambiguous":
                raise TaxCertifiedImportConflict("发票身份匹配不唯一，不能确认。")
            invoice_id = match["matched_invoice_id"]
            if invoice_id and invoice_id in invoice_ids:
                raise TaxCertifiedImportConflict("多个认证标识指向同一发票。")
            if invoice_id:
                invoice_ids.add(invoice_id)
            old = current.get(key)
            if key in correction_map and (not old or old["status"] != "active" or correction_map[key] != old["version"]):
                raise TaxCertifiedImportConflict("认证记录版本已变化，请重新预览。")
            if old and old["status"] == "active" and same_facts(old, row):
                if old.get("matched_invoice_id") is None and invoice_id:
                    linked = {**old, "matched_invoice_id": invoice_id, "match_status": "matched_invoice",
                              "version": old["version"] + 1}
                    links.append(linked)
                duplicates += 1
                continue
            if old and old["status"] == "active":
                if correction_map.get(key) != old["version"]:
                    raise TaxCertifiedImportConflict("认证记录已存在冲突，请按当前版本明确更正。")
                before.append(old)
            elif key in correction_map:
                raise TaxCertifiedImportConflict("认证记录状态已变化，请重新预览。")
            row.update(batch_id=batch_id, status="active", version=old["version"]+1 if old else 1,
                       matched_invoice_id=invoice_id, match_status=match["match_status"])
            changed.append(row)
        batch = {"id": batch_id, "session_id": session_id, "imported_by": actor_id,
                 "file_count": len(session["files"]), "months": sorted({row["month"] for row in rows if row.get("month")}),
                 "persisted_record_count": len(changed), "duplicate_count": duplicates,
                 "status": "confirmed", "version": 1, "created_at": datetime.now(UTC).isoformat(),
                 "record_keys": [row["unique_key"] for row in changed], "previous_records": before}
        batch_db = tx.fetch_one("""
            INSERT INTO app.tax_certified_import_batches(batch_id,session_id,status,row_count,raw_payload)
            VALUES (%s,%s,'confirmed',%s,%s) RETURNING id
        """, (batch_id, session_row["id"], len(changed), jsonb({"normalized_payload": batch})))
        params = [(row["unique_key"], batch_db["id"], row.get("invoice_no"), row.get("invoice_code"), row.get("digital_invoice_no"),
                   row.get("seller_name"), row.get("seller_tax_no"), row.get("issue_date"),
                   f'{row["month"]}-01' if row.get("month") else None, row.get("amount"), row.get("tax_amount"),
                   row.get("matched_invoice_id"), row.get("buyer_tax_no"), row.get("deductible_tax_amount"),
                   row.get("selection_time"), row.get("invoice_kind_label"), row["match_status"], row["version"],
                   jsonb({"normalized_payload": row})) for row in changed]
        tx.execute_many_values("""
            INSERT INTO app.tax_certified_import_records(certified_unique_key,batch_id,invoice_no,invoice_code,digital_invoice_no,
                seller_name,seller_tax_no,invoice_date,scope_month,amount,tax_amount,invoice_id,buyer_tax_no,deductible_tax_amount,
                selection_time,invoice_kind_label,match_status,version,raw_payload,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active')
            ON CONFLICT(certified_unique_key) DO UPDATE SET batch_id=excluded.batch_id,invoice_no=excluded.invoice_no,
                invoice_code=excluded.invoice_code,digital_invoice_no=excluded.digital_invoice_no,seller_name=excluded.seller_name,
                seller_tax_no=excluded.seller_tax_no,invoice_date=excluded.invoice_date,scope_month=excluded.scope_month,
                amount=excluded.amount,tax_amount=excluded.tax_amount,invoice_id=excluded.invoice_id,buyer_tax_no=excluded.buyer_tax_no,
                deductible_tax_amount=excluded.deductible_tax_amount,selection_time=excluded.selection_time,
                invoice_kind_label=excluded.invoice_kind_label,match_status=excluded.match_status,version=excluded.version,
                raw_payload=excluded.raw_payload,status='active'
        """, params)
        if links:
            tx.execute("""
                UPDATE app.tax_certified_import_records c SET invoice_id=r.invoice_id::uuid,
                    match_status='matched_invoice',version=r.version,raw_payload=jsonb_build_object('normalized_payload',r.payload)
                FROM jsonb_to_recordset(%s::jsonb) AS r(unique_key text,invoice_id text,version integer,payload jsonb)
                WHERE c.certified_unique_key=r.unique_key AND c.status='active'
            """, (jsonb([{"unique_key": row["unique_key"], "invoice_id": row["matched_invoice_id"],
                           "version": row["version"], "payload": row} for row in links]),))
        session["status"] = "confirmed"
        tx.execute("UPDATE app.tax_certified_import_sessions SET status='confirmed',raw_payload=%s,updated_at=now() WHERE id=%s",
                   (jsonb({"normalized_payload": session}), session_row["id"]))
        return public_batch(batch)

    def records_payload(self, month: str | None = None, *, records_page: int = 1, batches_page: int = 1,
                        page_size: int = 20) -> dict[str, Any]:
        if any(type(value) is not int or value < 1 for value in (records_page, batches_page, page_size)) or page_size > 100:
            raise ValueError("导入记录分页参数无效。")
        def read(tx: Any) -> dict[str, Any]:
            tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            record_where = "invoice_id IS NULL AND status IS DISTINCT FROM 'revoked' AND status IS DISTINCT FROM 'deleted' AND (%s::date IS NULL OR scope_month=%s::date)"
            record_params = (f"{month}-01" if month else None,) * 2
            records_total = tx.fetch_one(f"SELECT count(*) AS total FROM app.tax_certified_import_records WHERE {record_where}", record_params)["total"]
            records = tx.fetch_all(f"""SELECT raw_payload,version,status,match_status FROM app.tax_certified_import_records
                WHERE {record_where} ORDER BY selection_time DESC NULLS LAST,created_at DESC,id DESC LIMIT %s OFFSET %s""",
                (*record_params, page_size, (records_page-1)*page_size))
            batch_where = "(%s::text IS NULL OR raw_payload->'normalized_payload'->'months' ? %s)"
            batches_total = tx.fetch_one(f"SELECT count(*) AS total FROM app.tax_certified_import_batches WHERE {batch_where}", (month,month))["total"]
            batches = tx.fetch_all(f"""SELECT raw_payload,status,version FROM app.tax_certified_import_batches WHERE {batch_where}
                ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s""", (month,month,page_size,(batches_page-1)*page_size))
            return {"month": month, "records_page": records_page, "batches_page": batches_page, "page_size": page_size,
                    "records_total": records_total, "batches_total": batches_total,
                    "records": [{**{key: value for key,value in (row_payload(row) or {}).items() if key in RECORD_FIELDS},
                        "version": row["version"], "status": row["status"], "match_status": row["match_status"],
                        "matched_invoice_id": None, "needs_review": True} for row in records],
                    "batches": [public_batch({**row_payload(row), "status": row["status"], "version": row["version"]}) for row in batches]}
        return run_in_transaction(self._connection, read)

    def revoke_batch(self, batch_id: str, *, actor_id: str, expected_version: int) -> dict[str, Any]:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("批次版本无效。")
        def command(tx: Any) -> dict[str, Any]:
            tx.execute("SELECT pg_advisory_xact_lock(hashtext('tax-certified-import'))")
            batch = tx.fetch_one("""SELECT b.id,b.raw_payload,b.status,b.version,s.imported_by
                FROM app.tax_certified_import_batches b JOIN app.tax_certified_import_sessions s ON s.id=b.session_id
                WHERE b.batch_id=%s FOR UPDATE OF b""", (batch_id,))
            if batch is None:
                raise KeyError(batch_id)
            if batch["imported_by"] != actor_id:
                raise PermissionError("不能撤销其他用户的认证导入。")
            if batch["status"] == "revoked":
                return public_batch({**row_payload(batch), "status": "revoked", "version": batch["version"]})
            if batch["version"] != expected_version:
                raise TaxCertifiedImportConflict("批次已变化，请刷新后重试。")
            original = row_payload(batch)
            keys = original.get("record_keys") or []
            later = tx.fetch_one("""SELECT 1 AS found FROM app.tax_certified_import_records
                WHERE certified_unique_key=ANY(%s::text[]) AND status='active' AND batch_id IS DISTINCT FROM %s LIMIT 1""",
                (keys, batch["id"]))
            if later:
                raise TaxCertifiedImportConflict("批次记录已被后续更正替代，请先撤销后续更正批次。")
            current = tx.fetch_all("SELECT certified_unique_key,version FROM app.tax_certified_import_records WHERE batch_id=%s AND status='active'", (batch["id"],))
            versions = {row["certified_unique_key"]: row["version"] for row in current}
            restore = [{**old, "version": versions[old["unique_key"]]+1} for old in original.get("previous_records", [])
                       if old["unique_key"] in versions]
            if restore:
                owners = [row["batch_id"] for row in restore if row.get("batch_id")]
                revoked_owner = tx.fetch_one("SELECT 1 AS found FROM app.tax_certified_import_batches WHERE batch_id=ANY(%s::text[]) AND status='revoked' LIMIT 1", (owners,))
                if revoked_owner:
                    raise TaxCertifiedImportConflict("原认证批次已撤销，不能恢复，请核对批次记录。")
                tx.execute("""UPDATE app.tax_certified_import_records c SET
                    batch_id=b.id,invoice_no=p->>'invoice_no',invoice_code=p->>'invoice_code',digital_invoice_no=p->>'digital_invoice_no',
                    seller_name=p->>'seller_name',seller_tax_no=p->>'seller_tax_no',invoice_date=(p->>'issue_date')::date,
                    scope_month=(p->>'month'||'-01')::date,amount=(p->>'amount')::numeric,tax_amount=(p->>'tax_amount')::numeric,
                    invoice_id=(p->>'matched_invoice_id')::uuid,buyer_tax_no=p->>'buyer_tax_no',
                    deductible_tax_amount=(p->>'deductible_tax_amount')::numeric,selection_time=(p->>'selection_time')::timestamp,
                    invoice_kind_label=p->>'invoice_kind_label',match_status=coalesce(p->>'match_status','unresolved'),
                    status=p->>'status',version=(p->>'version')::integer,raw_payload=jsonb_build_object('normalized_payload',p)
                    FROM jsonb_array_elements(%s::jsonb) AS evidence(p)
                    LEFT JOIN app.tax_certified_import_batches b ON b.batch_id=p->>'batch_id'
                    WHERE c.certified_unique_key=p->>'unique_key' AND c.batch_id=%s
                """, (jsonb(restore), batch["id"]))
            count = tx.execute("UPDATE app.tax_certified_import_records SET status='revoked',version=version+1 WHERE batch_id=%s AND status='active'", (batch["id"],))
            payload = {**original, "status": "revoked", "version": batch["version"]+1,
                       "revoked_record_count": count, "restored_record_count": len(restore), "revoked_at": datetime.now(UTC).isoformat()}
            tx.execute("UPDATE app.tax_certified_import_batches SET status='revoked',version=version+1,raw_payload=%s WHERE id=%s",
                       (jsonb({"normalized_payload": payload}), batch["id"]))
            AuditTrailService(PostgresOperationsAuditRepository(tx)).record_action(actor_id=actor_id,
                action="tax_certified_import.revoke", entity_type="tax_certified_import_batch", entity_id=batch_id,
                metadata={"page_key": "tax-offset", "event_type": "operation.completed", "result": public_batch(payload)})
            return public_batch(payload)
        return run_in_transaction(self._connection, command)
