from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.tax_certified_import_service import SOURCE_COLUMNS, UploadedCertifiedImportFile

FACT_LABELS = {**{field: label for label, field in SOURCE_COLUMNS.items()}, "month": "所属期", "buyer_tax_no": "买方税号"}


class TaxCertifiedImportApplicationService:
    def __init__(self, *, certified_import_service: Any) -> None:
        self._service = certified_import_service

    def preview_payload(self, *, imported_by: str, uploads: list[UploadedCertifiedImportFile],
                        month: str | None = None, buyer_tax_no: str | None = None) -> dict[str, Any]:
        session = self._service.preview_files(imported_by=imported_by, uploads=uploads,
                                             month=month, buyer_tax_no=buyer_tax_no)
        all_rows = [serialize_value(row) for file in session.files for row in file.rows]
        classifications = self._service.classify_rows(all_rows)
        summary = {key: 0 for key in ("source_count", "recognized_count", "invalid_count", "ignored_count", "matched_invoice_count",
                                     "outside_invoices_count", "conflict_count", "duplicate_count", "blocking_count", "new_count", "relink_count")}
        files = []
        seen = set()
        for file in session.files:
            rows = []
            counts = dict.fromkeys(summary, 0)
            missing_metadata = [field for field in ("month", "buyer_tax_no")
                                if any(not getattr(row, field) for row in file.rows)]
            for row in file.row_results:
                counts["source_count"] += 1
                payload = {"blocking": False, **row}
                if row["row_status"] == "recognized":
                    payload.update(classifications[row["unique_key"]])
                    if payload["blocking"]:
                        payload["row_status"] = "invalid"
                        counts["invalid_count"] += 1
                        counts["blocking_count"] += 1
                    else:
                        counts["recognized_count"] += 1
                        counts["matched_invoice_count" if payload["match_status"] == "matched_invoice" else "outside_invoices_count"] += 1
                        key = row["unique_key"]
                        if key in seen:
                            counts["duplicate_count"] += 1
                            continue
                        seen.add(key)
                        counts[f'{payload["dedupe_status"]}_count'] += 1
                else:
                    counts["ignored_count" if row["row_status"] == "ignored" else "invalid_count"] += 1
                if payload["row_status"] == "invalid" or payload["dedupe_status"] == "conflict":
                    payload.pop("source_fields", None)
                    if payload["dedupe_status"] == "conflict":
                        payload["correction_changes"] = [{**change, "label": FACT_LABELS[change["field"]]}
                                                         for change in payload["correction_changes"]]
                    rows.append(serialize_value(payload))
            files.append({"id": file.id, "file_name": file.file_name, "month": file.month,
                          "missing_metadata": missing_metadata, "rows": rows, **counts})
            for key in summary:
                summary[key] += counts[key]
        return {"session": {"id": session.id, "imported_by": session.imported_by,
                            "file_count": session.file_count, "status": session.status},
                "files": files, "summary": summary}

    def records_payload(self, month: str | None = None, *, records_page: int = 1, batches_page: int = 1,
                        page_size: int = 20) -> dict[str, Any]:
        return self._service.records_payload(month, records_page=records_page, batches_page=batches_page, page_size=page_size)

    def revoke_batch(self, batch_id: str, *, actor_id: str, expected_version: int) -> dict[str, Any]:
        return self._service.revoke_batch(batch_id, actor_id=actor_id, expected_version=expected_version)
