from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fin_ops_platform.services.tax_certified_import_service import (
    TaxCertifiedImportPreviewRowResult,
    UploadedCertifiedImportFile,
)


class TaxCertifiedImportApplicationService:
    def __init__(
        self,
        *,
        certified_import_service: Any,
        tax_offset_service: Any,
    ) -> None:
        self._certified_import_service = certified_import_service
        self._tax_offset_service = tax_offset_service

    def preview_payload(
        self,
        *,
        imported_by: str,
        uploads: list[UploadedCertifiedImportFile],
    ) -> dict[str, object]:
        if self._certified_import_service is None:
            raise RuntimeError("Tax certified import service is not configured.")
        if self._tax_offset_service is None:
            raise RuntimeError("Tax offset service is not configured.")
        session = self._certified_import_service.preview_files(imported_by=imported_by, uploads=uploads)
        preview_files: list[dict[str, object]] = []
        summary = {
            "recognized_count": 0,
            "invalid_count": 0,
            "matched_plan_count": 0,
            "outside_plan_count": 0,
        }
        for preview_file in session.files:
            matched_rows = self._tax_offset_service.classify_certified_preview_rows(
                preview_file.month,
                preview_file.rows,
            )
            matches_by_key = {
                str(item.get("unique_key") or ""): item
                for item in matched_rows
                if str(item.get("unique_key") or "")
            }
            row_payloads: list[dict[str, object]] = []
            matched_plan_count = 0
            outside_plan_count = 0
            for row_result in preview_file.row_results:
                row_payload = self._row_payload(row_result)
                if row_result.row_status == "recognized":
                    match = matches_by_key.get(str(row_result.unique_key or ""))
                    match_status = str(match.get("match_status") if match else "outside_plan")
                    matched_plan_id = match.get("matched_plan_id") if match else None
                    row_payload["match_status"] = match_status
                    row_payload["matched_plan_id"] = matched_plan_id
                    if match_status == "matched_plan":
                        matched_plan_count += 1
                    else:
                        outside_plan_count += 1
                row_payloads.append(row_payload)

            file_payload = {
                "id": preview_file.id,
                "file_name": preview_file.file_name,
                "month": preview_file.month,
                "recognized_count": preview_file.recognized_count,
                "invalid_count": preview_file.invalid_count,
                "matched_plan_count": matched_plan_count,
                "outside_plan_count": outside_plan_count,
                "rows": row_payloads,
            }
            preview_files.append(file_payload)
            summary["recognized_count"] += preview_file.recognized_count
            summary["invalid_count"] += preview_file.invalid_count
            summary["matched_plan_count"] += matched_plan_count
            summary["outside_plan_count"] += outside_plan_count

        return {
            "session": {
                "id": session.id,
                "imported_by": session.imported_by,
                "file_count": session.file_count,
                "status": session.status,
            },
            "files": preview_files,
            "summary": summary,
        }

    def records_payload(self, month: str) -> dict[str, object]:
        if self._certified_import_service is None:
            raise RuntimeError("Tax certified import service is not configured.")
        return {
            "month": month,
            "records": self._certified_import_service.list_records_for_month(month),
        }

    @staticmethod
    def _row_payload(row: TaxCertifiedImportPreviewRowResult) -> dict[str, object]:
        payload = asdict(row)
        payload.setdefault("match_status", "unknown")
        payload.setdefault("matched_plan_id", None)
        payload.setdefault("dedupe_status", "not_applicable")
        return payload
