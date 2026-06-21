from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from threading import Lock
from typing import Any, Callable, Iterable

from fin_ops_platform.services.etc_service import (
    EtcService,
    UploadedEtcZipFile,
    parse_etc_xml,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


HISTORICAL_ETC_REPAIR_RELATION_MODE = "etc_batch_invoice_link"
HISTORICAL_ETC_PARSED_SEED_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class HistoricalEtcRepairBatchSpec:
    label: str
    bundle_id: str
    case_id: str
    external_batch_id: str
    oa_row_id: str
    oa_amount: Decimal
    excluded_invoice_numbers: frozenset[str] = frozenset()
    stable_oa_hints: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class HistoricalEtcRepairBatchResult:
    bundle_id: str
    label: str
    status: str
    message: str
    invoice_count: int = 0
    imported_count: int = 0
    batch_id: str | None = None
    relation_case_id: str | None = None
    amount_delta: Decimal | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "invoice_count": self.invoice_count,
            "imported_count": self.imported_count,
            "batch_id": self.batch_id,
            "relation_case_id": self.relation_case_id,
            "amount_delta": f"{self.amount_delta:.2f}" if self.amount_delta is not None else None,
        }


@dataclass(slots=True)
class HistoricalEtcRepairResult:
    status: str
    message: str
    batches: list[HistoricalEtcRepairBatchResult]
    dirty_rerun: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "dirty_rerun": self.dirty_rerun,
            "batches": [batch.to_payload() for batch in self.batches],
        }


DEFAULT_HISTORICAL_ETC_REPAIR_SPECS: tuple[HistoricalEtcRepairBatchSpec, ...] = (
    HistoricalEtcRepairBatchSpec(
        label="2026年1月",
        bundle_id="ETC-HIST-2026-01",
        case_id="etc-historical-2026-01",
        external_batch_id="ETC-HIST-2026-01",
        oa_row_id="oa-exp-1994",
        oa_amount=Decimal("1549.00"),
        stable_oa_hints={"amount": "1549.00", "month": "2026-02"},
    ),
    HistoricalEtcRepairBatchSpec(
        label="2026年2月",
        bundle_id="ETC-HIST-2026-02",
        case_id="etc-historical-2026-02",
        external_batch_id="ETC-HIST-2026-02",
        oa_row_id="oa-exp-2045",
        oa_amount=Decimal("1935.45"),
        excluded_invoice_numbers=frozenset(
            {
                "26537912570200055449",
                "26537912430200039797",
                "26537911970200072984",
                "26537911580200081351",
            }
        ),
        stable_oa_hints={"amount": "1935.45", "month": "2026-03"},
    ),
    HistoricalEtcRepairBatchSpec(
        label="2026年3月",
        bundle_id="ETC-HIST-2026-03",
        case_id="etc-historical-2026-03",
        external_batch_id="ETC-HIST-2026-03",
        oa_row_id="oa-exp-2080",
        oa_amount=Decimal("2411.25"),
        stable_oa_hints={"amount": "2411.25", "month": "2026-04"},
    ),
)


class HistoricalEtcRepairService:
    def __init__(
        self,
        *,
        state_store: Any,
        etc_service: EtcService,
        relation_command_service: Any | None = None,
        specs: Iterable[HistoricalEtcRepairBatchSpec] = DEFAULT_HISTORICAL_ETC_REPAIR_SPECS,
        oa_row_exists: Callable[[str], bool] | None = None,
        link_import_result_to_existing_invoices: Callable[[Any], list[str]] | None = None,
        link_etc_invoices_to_existing_invoices: Callable[[list[Any]], list[str]] | None = None,
        refresh_after_etc_invoice_link: Callable[[list[str], str], None] | None = None,
        persist_pair_relations: Callable[[list[str]], None] | None = None,
        invalidate_workbench_scopes: Callable[[list[str]], None] | None = None,
        persist_etc_state: Callable[[], None] | None = None,
    ) -> None:
        self._state_store = state_store
        self._etc_service = etc_service
        self._relation_command_service = relation_command_service
        self._specs = list(specs)
        self._oa_row_exists = oa_row_exists or (lambda _row_id: True)
        self._link_import_result_to_existing_invoices = link_import_result_to_existing_invoices or (lambda _result: [])
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices or (lambda _invoices: [])
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link or (lambda _months, _reason: None)
        self._persist_pair_relations = persist_pair_relations or (lambda _case_ids: None)
        self._invalidate_workbench_scopes = invalidate_workbench_scopes or (lambda _scopes: None)
        self._persist_etc_state = persist_etc_state or (lambda: None)
        self._lock = Lock()
        self._dirty_rerun = False

    def seed_bundle_from_upload(self, spec: HistoricalEtcRepairBatchSpec, upload: UploadedEtcZipFile) -> dict[str, Any]:
        parsed_invoices = self._parse_unique_zip_invoices(upload)
        invoice_numbers = self._selected_invoice_numbers(parsed_invoices, spec)
        content_sha256 = hashlib.sha256(bytes(upload.content)).hexdigest()
        metadata = {
            "label": spec.label,
            "case_id": spec.case_id,
            "external_batch_id": spec.external_batch_id,
            "oa_row_id": spec.oa_row_id,
            "oa_amount": f"{spec.oa_amount:.2f}",
            "excluded_invoice_numbers": sorted(spec.excluded_invoice_numbers),
            "invoice_numbers": invoice_numbers,
            "stable_oa_hints": dict(spec.stable_oa_hints),
        }
        bundle = self._state_store.save_historical_etc_repair_bundle(
            bundle_id=spec.bundle_id,
            file_name=upload.file_name,
            content=upload.content,
            metadata=metadata,
        )
        parsed_seed = self._build_parsed_seed(
            spec=spec,
            source_sha256=content_sha256,
            parsed_invoices=parsed_invoices,
            invoice_numbers=invoice_numbers,
        )
        self._state_store.save_historical_etc_repair_parsed_seed(
            bundle_id=spec.bundle_id,
            parsed_seed=parsed_seed,
        )
        return bundle

    def seed_bundles_from_uploads(self, uploads_by_bundle_id: dict[str, UploadedEtcZipFile]) -> list[dict[str, Any]]:
        saved: list[dict[str, Any]] = []
        specs_by_id = {spec.bundle_id: spec for spec in self._specs}
        for bundle_id, upload in uploads_by_bundle_id.items():
            spec = specs_by_id.get(str(bundle_id))
            if spec is None:
                raise ValueError(f"Unsupported historical ETC bundle id: {bundle_id}")
            saved.append(self.seed_bundle_from_upload(spec, upload))
        return saved

    def reconcile(self, *, reason: str = "manual") -> HistoricalEtcRepairResult:
        if not self._lock.acquire(blocking=False):
            self._dirty_rerun = True
            return HistoricalEtcRepairResult(
                status="running",
                message="历史 ETC 修复正在运行，已标记需要再次检查。",
                batches=[],
                dirty_rerun=True,
            )
        try:
            return self._reconcile_locked(reason=reason)
        finally:
            self._lock.release()

    def _reconcile_locked(self, *, reason: str) -> HistoricalEtcRepairResult:
        states = self._state_store.load_historical_etc_repair_states()
        batch_results: list[HistoricalEtcRepairBatchResult] = []
        dirty_rerun = self._dirty_rerun
        self._dirty_rerun = False

        for spec in self._specs:
            result = self._reconcile_batch(spec, reason=reason)
            batch_results.append(result)
            states[spec.bundle_id] = {
                **result.to_payload(),
                "reason": reason,
                "updated_at": datetime.now(UTC).isoformat(),
            }

        self._state_store.save_historical_etc_repair_states(states)
        statuses = {result.status for result in batch_results}
        if "attention" in statuses or "waiting_seed" in statuses or "waiting_oa" in statuses:
            status = "attention"
            message = "历史 ETC 修复需要人工确认或等待前置数据。"
        elif "failed" in statuses:
            status = "attention"
            message = "历史 ETC 修复失败，需要重试或确认。"
        else:
            status = "ok"
            message = "历史 ETC 批次已恢复。"
        return HistoricalEtcRepairResult(
            status=status,
            message=message,
            batches=batch_results,
            dirty_rerun=dirty_rerun,
        )

    def _reconcile_batch(self, spec: HistoricalEtcRepairBatchSpec, *, reason: str) -> HistoricalEtcRepairBatchResult:
        seed = self._load_or_rebuild_parsed_seed(spec)
        if seed is None:
            return HistoricalEtcRepairBatchResult(
                bundle_id=spec.bundle_id,
                label=spec.label,
                status="waiting_seed",
                message=f"{spec.label} 历史 ETC parsed seed 尚未写入 Mongo。",
            )
        invoice_numbers = [
            str(invoice_number).strip()
            for invoice_number in list(seed.get("selected_invoice_numbers") or [])
            if str(invoice_number).strip()
        ]
        if not invoice_numbers:
            return HistoricalEtcRepairBatchResult(
                bundle_id=spec.bundle_id,
                label=spec.label,
                status="attention",
                message=f"{spec.label} 历史 ETC parsed seed 未包含可修复发票。",
            )

        if not self._oa_row_exists(spec.oa_row_id):
            return HistoricalEtcRepairBatchResult(
                bundle_id=spec.bundle_id,
                label=spec.label,
                status="waiting_oa",
                message=f"{spec.label} 等待 OA 重建后定位 {spec.oa_row_id}。",
                invoice_count=len(invoice_numbers),
            )

        imported_count = 0
        existing_numbers = {
            invoice.invoice_number
            for invoice in self._etc_service.list_invoices_by_numbers(invoice_numbers)
        }
        missing_numbers = [invoice_number for invoice_number in invoice_numbers if invoice_number not in existing_numbers]
        existing_batch = self._existing_historical_batch(spec)
        existing_relation = self._active_relation_by_case_id(spec.case_id)
        if existing_batch is not None and isinstance(existing_relation, dict) and not missing_numbers:
            return HistoricalEtcRepairBatchResult(
                bundle_id=spec.bundle_id,
                label=spec.label,
                status="ok",
                message=f"{spec.label} 历史 ETC 批次已存在。",
                invoice_count=len(invoice_numbers),
                imported_count=0,
                batch_id=str(existing_batch.id),
                relation_case_id=str(existing_relation.get("case_id") or spec.case_id),
                amount_delta=existing_batch.amount_delta,
            )

        if missing_numbers:
            missing_records = self._missing_invoice_records_from_seed(seed, missing_numbers)
            if len(missing_records) != len(missing_numbers):
                return HistoricalEtcRepairBatchResult(
                    bundle_id=spec.bundle_id,
                    label=spec.label,
                    status="attention",
                    message=f"{spec.label} parsed seed 缺少部分发票结构化记录。",
                    invoice_count=len(invoice_numbers),
                )
        command_confirm = self._relation_confirm_command()
        if missing_numbers:
            import_result = self._etc_service.import_historical_invoices_from_records(
                records=missing_records,
                source_name=f"{spec.bundle_id}.parsed_seed",
            )
            imported_count = int(getattr(import_result, "imported", 0) or 0)
            changed_months = self._link_import_result_to_existing_invoices(import_result)
            self._refresh_after_etc_invoice_link(changed_months, f"historical_etc_repair_import:{reason}")

        batch = self._etc_service.create_historical_submitted_batch(
            case_id=spec.case_id,
            external_batch_id=spec.external_batch_id,
            invoice_numbers=invoice_numbers,
            linked_oa_row_id=spec.oa_row_id,
            oa_amount=spec.oa_amount,
            note=f"{spec.label} ETC 历史 OA 已提交补关联；自动修复原因：{reason}。",
        )
        invoices = self._etc_service.list_invoices_by_ids(list(batch.invoice_ids))
        changed_months = self._link_etc_invoices_to_existing_invoices(invoices)
        self._refresh_after_etc_invoice_link(changed_months, f"historical_etc_repair_link:{reason}")

        amount_check = {
            "status": "matched" if batch.amount_delta == Decimal("0.00") else "mismatch",
            "oa_amount": f"{spec.oa_amount:.2f}",
            "invoice_total": f"{batch.total_amount:.2f}",
            "delta": f"{batch.amount_delta:.2f}",
            "etc_batch_id": batch.id,
            "external_etc_batch_id": batch.etc_batch_id,
            "source": "historical_repair",
        }
        command_result = command_confirm(
            case_id=spec.case_id,
            row_ids=[spec.oa_row_id],
            row_types=["oa"],
            relation_mode=HISTORICAL_ETC_REPAIR_RELATION_MODE,
            actor_id="system_historical_repair",
            month_scope="all",
            note=f"{spec.label} ETC 历史补关联",
            amount_check=amount_check,
            history_operation_type="historical_etc_repair_confirm",
        )
        relation = command_result.get("relation") if isinstance(command_result, dict) else None
        if not isinstance(relation, dict):
            relation = {"case_id": spec.case_id}
        self._persist_pair_relations([str(relation["case_id"])])
        self._invalidate_workbench_scopes(["all", *changed_months])
        self._persist_etc_state()
        return HistoricalEtcRepairBatchResult(
            bundle_id=spec.bundle_id,
            label=spec.label,
            status="ok",
            message=f"{spec.label} 历史 ETC 批次已恢复。",
            invoice_count=len(invoice_numbers),
            imported_count=imported_count,
            batch_id=batch.id,
            relation_case_id=str(relation["case_id"]),
            amount_delta=batch.amount_delta,
        )

    def _relation_confirm_command(self) -> Callable[..., dict[str, Any]]:
        command_confirm = (
            getattr(self._relation_command_service, "confirm_relation", None)
            if self._relation_command_service is not None
            else None
        )
        if not callable(command_confirm):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Historical ETC repair requires WorkbenchRelationCommandService.confirm_relation.",
        )
        return command_confirm

    def _active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        get_relation = getattr(self._relation_command_service, "get_active_relation_by_case_id", None)
        if not callable(get_relation):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Historical ETC repair requires WorkbenchRelationCommandService.get_active_relation_by_case_id.",
            )
        try:
            relation = get_relation(case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return None
            raise
        return relation if isinstance(relation, dict) else None

    def _parse_unique_zip_invoices(self, upload: UploadedEtcZipFile) -> list[Any]:
        parsed_by_number: OrderedDict[str, Any] = OrderedDict()
        entries = self._etc_service._extract_archive_entries(upload.file_name, upload.content)
        for entry in entries:
            if not self._etc_service._is_xml_entry(entry.path):
                continue
            parsed = parse_etc_xml(entry.content)
            parsed_by_number.setdefault(parsed.invoice_number, parsed)
        return list(parsed_by_number.values())

    def _load_or_rebuild_parsed_seed(self, spec: HistoricalEtcRepairBatchSpec) -> dict[str, Any] | None:
        seed = self._state_store.load_historical_etc_repair_parsed_seed(spec.bundle_id)
        if self._parsed_seed_is_usable(seed, spec):
            return seed
        bundle = self._state_store.read_historical_etc_repair_bundle(spec.bundle_id)
        if bundle is None:
            return None
        upload = UploadedEtcZipFile(str(bundle.get("file_name") or f"{spec.bundle_id}.zip"), bytes(bundle["content"]))
        parsed_invoices = self._parse_unique_zip_invoices(upload)
        invoice_numbers = self._selected_invoice_numbers(parsed_invoices, spec)
        metadata = bundle.get("metadata") if isinstance(bundle.get("metadata"), dict) else {}
        source_sha256 = str(metadata.get("sha256") or hashlib.sha256(bytes(upload.content)).hexdigest())
        rebuilt_seed = self._build_parsed_seed(
            spec=spec,
            source_sha256=source_sha256,
            parsed_invoices=parsed_invoices,
            invoice_numbers=invoice_numbers,
        )
        return self._state_store.save_historical_etc_repair_parsed_seed(
            bundle_id=spec.bundle_id,
            parsed_seed=rebuilt_seed,
        )

    def _existing_historical_batch(self, spec: HistoricalEtcRepairBatchSpec) -> Any | None:
        for batch in self._etc_service.list_batches(status="submitted"):
            if str(getattr(batch, "linked_oa_case_id", "") or "") == spec.case_id:
                return batch
            if str(getattr(batch, "etc_batch_id", "") or "") == spec.external_batch_id:
                return batch
        return None

    @staticmethod
    def _parsed_seed_is_usable(seed: dict[str, Any] | None, spec: HistoricalEtcRepairBatchSpec) -> bool:
        if not isinstance(seed, dict):
            return False
        if int(seed.get("parsed_schema_version") or 0) != HISTORICAL_ETC_PARSED_SEED_SCHEMA_VERSION:
            return False
        if str(seed.get("external_batch_id") or "") != spec.external_batch_id:
            return False
        invoice_numbers = list(seed.get("selected_invoice_numbers") or [])
        invoice_records = list(seed.get("invoice_records") or seed.get("selected_invoice_records") or [])
        return bool(invoice_numbers) and len(invoice_numbers) == len(invoice_records)

    @staticmethod
    def _missing_invoice_records_from_seed(seed: dict[str, Any], missing_numbers: list[str]) -> list[dict[str, object]]:
        missing_set = set(missing_numbers)
        records = list(seed.get("selected_invoice_records") or seed.get("invoice_records") or [])
        records_by_number = {
            str(record.get("invoice_number") or "").strip(): dict(record)
            for record in records
            if isinstance(record, dict)
        }
        return [
            records_by_number[invoice_number]
            for invoice_number in missing_numbers
            if invoice_number in missing_set and invoice_number in records_by_number
        ]

    def _build_parsed_seed(
        self,
        *,
        spec: HistoricalEtcRepairBatchSpec,
        source_sha256: str,
        parsed_invoices: list[Any],
        invoice_numbers: list[str],
    ) -> dict[str, Any]:
        selected_number_set = set(invoice_numbers)
        selected_invoices = [
            invoice
            for invoice in parsed_invoices
            if str(invoice.invoice_number) in selected_number_set
        ]
        invoice_records = [self._parsed_invoice_record(invoice) for invoice in selected_invoices]
        total_amount = sum((Decimal(str(record["total_amount"])) for record in invoice_records), Decimal("0.00")).quantize(Decimal("0.01"))
        issue_dates = sorted(str(record["issue_date"]) for record in invoice_records if record.get("issue_date"))
        passage_dates = sorted(
            str(value)
            for record in invoice_records
            for value in (record.get("passage_start_date"), record.get("passage_end_date"))
            if value
        )
        plate_summary: dict[str, dict[str, object]] = {}
        for record in invoice_records:
            plate = str(record.get("plate_number") or "未识别车牌")
            summary = plate_summary.setdefault(plate, {"plate_number": plate, "invoice_count": 0, "total_amount": Decimal("0.00")})
            summary["invoice_count"] = int(summary["invoice_count"]) + 1
            summary["total_amount"] = (Decimal(str(summary["total_amount"])) + Decimal(str(record["total_amount"]))).quantize(Decimal("0.01"))
        return {
            "bundle_id": spec.bundle_id,
            "label": spec.label,
            "case_id": spec.case_id,
            "external_batch_id": spec.external_batch_id,
            "oa_row_id": spec.oa_row_id,
            "oa_amount": f"{spec.oa_amount:.2f}",
            "source_sha256": source_sha256,
            "parsed_schema_version": HISTORICAL_ETC_PARSED_SEED_SCHEMA_VERSION,
            "selected_invoice_numbers": invoice_numbers,
            "excluded_invoice_numbers": sorted(spec.excluded_invoice_numbers),
            "invoice_count": len(invoice_records),
            "total_amount": f"{total_amount:.2f}",
            "totals": {
                "invoice_count": len(invoice_records),
                "total_amount": f"{total_amount:.2f}",
                "oa_amount": f"{spec.oa_amount:.2f}",
                "amount_delta": f"{(spec.oa_amount - total_amount).quantize(Decimal('0.01')):.2f}",
            },
            "issue_start_date": issue_dates[0] if issue_dates else None,
            "issue_end_date": issue_dates[-1] if issue_dates else None,
            "issue_range": {
                "start": issue_dates[0] if issue_dates else None,
                "end": issue_dates[-1] if issue_dates else None,
            },
            "passage_start_date": passage_dates[0] if passage_dates else None,
            "passage_end_date": passage_dates[-1] if passage_dates else None,
            "passage_range": {
                "start": passage_dates[0] if passage_dates else None,
                "end": passage_dates[-1] if passage_dates else None,
            },
            "plate_summary": [
                {
                    "plate_number": item["plate_number"],
                    "invoice_count": item["invoice_count"],
                    "total_amount": f"{Decimal(str(item['total_amount'])):.2f}",
                }
                for item in sorted(plate_summary.values(), key=lambda item: -int(item["invoice_count"]))
            ],
            "invoice_records": invoice_records,
            "selected_invoice_records": invoice_records,
            "created_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _parsed_invoice_record(invoice: Any) -> dict[str, object]:
        return {
            "invoice_number": str(invoice.invoice_number),
            "issue_date": invoice.issue_date,
            "passage_start_date": invoice.passage_start_date,
            "passage_end_date": invoice.passage_end_date,
            "plate_number": invoice.plate_number,
            "vehicle_type": invoice.vehicle_type,
            "seller_name": invoice.seller_name,
            "seller_tax_no": invoice.seller_tax_no,
            "buyer_name": invoice.buyer_name,
            "buyer_tax_no": invoice.buyer_tax_no,
            "amount_without_tax": f"{invoice.amount_without_tax:.2f}",
            "tax_amount": f"{invoice.tax_amount:.2f}",
            "total_amount": f"{invoice.total_amount:.2f}",
            "tax_rate": invoice.tax_rate,
        }

    @staticmethod
    def _selected_invoice_numbers(
        parsed_invoices: Iterable[Any],
        spec: HistoricalEtcRepairBatchSpec,
    ) -> list[str]:
        return [
            str(invoice.invoice_number)
            for invoice in parsed_invoices
            if str(invoice.invoice_number) not in spec.excluded_invoice_numbers
        ]
