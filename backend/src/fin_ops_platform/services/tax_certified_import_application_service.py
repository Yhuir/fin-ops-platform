from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.tax_certified_import_service import UploadedCertifiedImportFile


class TaxCertifiedImportApplicationService:
    def __init__(self, *, certified_import_service: Any) -> None:
        self._service = certified_import_service

    def preview_payload(self, *, imported_by: str, uploads: list[UploadedCertifiedImportFile],
                        month: str | None = None, buyer_tax_no: str | None = None) -> dict[str, Any]:
        session = self._service.preview_files(imported_by=imported_by, uploads=uploads,
                                             month=month, buyer_tax_no=buyer_tax_no)
        all_rows = [serialize_value(row) for file in session.files for row in file.rows]
        classifications = self._service.classify_rows(all_rows)
        summary = {key: 0 for key in ("recognized_count", "invalid_count", "ignored_count", "matched_invoice_count",
                                     "outside_invoices_count", "conflict_count", "duplicate_count", "blocking_count")}
        files = []
        for file in session.files:
            rows = []
            counts = dict.fromkeys(summary, 0)
            for row in file.row_results:
                payload = {"blocking": False, **serialize_value(row)}
                if row["row_status"] == "recognized":
                    payload.update(classifications[row["unique_key"]])
                    if payload["blocking"]:
                        payload["row_status"] = "invalid"
                        counts["invalid_count"] += 1
                        counts["blocking_count"] += 1
                        rows.append(payload)
                        continue
                    counts["recognized_count"] += 1
                    counts["matched_invoice_count" if payload["match_status"] == "matched_invoice" else "outside_invoices_count"] += 1
                    if payload["dedupe_status"] in {"conflict", "duplicate"}:
                        counts[f'{payload["dedupe_status"]}_count'] += 1
                else:
                    counts["ignored_count" if row["row_status"] == "ignored" else "invalid_count"] += 1
                rows.append(payload)
            files.append({"id": file.id, "file_name": file.file_name, "month": file.month, "rows": rows, **counts})
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
