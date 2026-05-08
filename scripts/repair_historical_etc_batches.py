#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
from time import monotonic
from typing import Iterable

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.historical_etc_repair_service import DEFAULT_HISTORICAL_ETC_REPAIR_SPECS
from fin_ops_platform.services.etc_service import UploadedEtcZipFile, parse_etc_xml


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".runtime" / "fin_ops_platform"
SOURCE_DIR = Path("/Users/yu/Desktop/sy/财务运营平台/1-4月etc发票批次")


@dataclass(frozen=True)
class HistoricalEtcBatchSpec:
    label: str
    zip_path: Path
    case_id: str
    external_batch_id: str
    oa_row_id: str
    oa_amount: Decimal
    excluded_invoice_numbers: frozenset[str] = frozenset()


SPECS = [
    HistoricalEtcBatchSpec(
        label="2026年1月",
        zip_path=SOURCE_DIR / "2026年1月.zip",
        case_id="etc-historical-2026-01",
        external_batch_id="ETC-HIST-2026-01",
        oa_row_id="oa-exp-1994",
        oa_amount=Decimal("1549.00"),
    ),
    HistoricalEtcBatchSpec(
        label="2026年2月",
        zip_path=SOURCE_DIR / "2026年2月.zip",
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
    ),
    HistoricalEtcBatchSpec(
        label="2026年3月",
        zip_path=SOURCE_DIR / "2026年3月.zip",
        case_id="etc-historical-2026-03",
        external_batch_id="ETC-HIST-2026-03",
        oa_row_id="oa-exp-2080",
        oa_amount=Decimal("2411.25"),
    ),
]

SERVICE_SPECS_BY_BUNDLE_ID = {spec.bundle_id: spec for spec in DEFAULT_HISTORICAL_ETC_REPAIR_SPECS}


def load_upload(spec: HistoricalEtcBatchSpec) -> UploadedEtcZipFile:
    if not spec.zip_path.exists():
        raise FileNotFoundError(spec.zip_path)
    return UploadedEtcZipFile(spec.zip_path.name, spec.zip_path.read_bytes())


def parse_unique_zip_invoices(app, upload: UploadedEtcZipFile) -> list[object]:
    parsed_by_number: OrderedDict[str, object] = OrderedDict()
    entries = app._etc_service._extract_archive_entries(upload.file_name, upload.content)
    for entry in entries:
        if not app._etc_service._is_xml_entry(entry.path):
            continue
        parsed = parse_etc_xml(entry.content)
        parsed_by_number.setdefault(parsed.invoice_number, parsed)
    return list(parsed_by_number.values())


def selected_invoice_numbers(parsed_invoices: Iterable[object], spec: HistoricalEtcBatchSpec) -> list[str]:
    return [
        str(invoice.invoice_number)
        for invoice in parsed_invoices
        if str(invoice.invoice_number) not in spec.excluded_invoice_numbers
    ]


def date_range(values: Iterable[str | None]) -> str:
    normalized = sorted(str(value) for value in values if value)
    if not normalized:
        return "-"
    if normalized[0] == normalized[-1]:
        return normalized[0]
    return f"{normalized[0]} 至 {normalized[-1]}"


def print_batch_preview(app, spec: HistoricalEtcBatchSpec, parsed_invoices: list[object], invoice_numbers: list[str]) -> None:
    selected = [invoice for invoice in parsed_invoices if str(invoice.invoice_number) in set(invoice_numbers)]
    total = sum((invoice.total_amount for invoice in selected), Decimal("0.00")).quantize(Decimal("0.01"))
    existing_numbers = {
        invoice.invoice_number
        for invoice in app._etc_service.list_invoices_by_numbers(invoice_numbers)
    }
    missing_numbers = [invoice_number for invoice_number in invoice_numbers if invoice_number not in existing_numbers]
    plate_totals: dict[str, dict[str, object]] = {}
    for invoice in selected:
        plate = str(invoice.plate_number or "未识别车牌")
        item = plate_totals.setdefault(plate, {"count": 0, "total": Decimal("0.00")})
        item["count"] = int(item["count"]) + 1
        item["total"] = (Decimal(str(item["total"])) + invoice.total_amount).quantize(Decimal("0.01"))

    print(f"\n{spec.label} / {spec.external_batch_id}")
    print(f"  OA: {spec.oa_row_id} amount={spec.oa_amount}")
    print(f"  invoices={len(selected)} total={total} delta={(spec.oa_amount - total).quantize(Decimal('0.01'))}")
    print(f"  issue={date_range(invoice.issue_date for invoice in selected)}")
    print(f"  passage={date_range(value for invoice in selected for value in (invoice.passage_start_date, invoice.passage_end_date))}")
    print(f"  missing={len(missing_numbers)} {', '.join(missing_numbers) if missing_numbers else '-'}")
    if spec.excluded_invoice_numbers:
        print(f"  excluded={len(spec.excluded_invoice_numbers)} {', '.join(sorted(spec.excluded_invoice_numbers))}")
    for plate, item in plate_totals.items():
        print(f"  plate {plate}: {item['count']} 张 / {item['total']}")


def apply_batch(app, spec: HistoricalEtcBatchSpec, upload: UploadedEtcZipFile, invoice_numbers: list[str]) -> None:
    existing_numbers = {
        invoice.invoice_number
        for invoice in app._etc_service.list_invoices_by_numbers(invoice_numbers)
    }
    missing_numbers = [invoice_number for invoice_number in invoice_numbers if invoice_number not in existing_numbers]
    if missing_numbers:
        result = app._etc_service.import_missing_invoices_from_zips(
            invoice_numbers=missing_numbers,
            uploads=[upload],
        )
        changed_months = app._sync_etc_import_result_to_canonical_invoices(result)
        app._refresh_after_etc_invoice_sync(changed_months, reason="historical_etc_missing_invoice_import")

    batch = app._etc_service.create_historical_submitted_batch(
        case_id=spec.case_id,
        external_batch_id=spec.external_batch_id,
        invoice_numbers=invoice_numbers,
        linked_oa_row_id=spec.oa_row_id,
        oa_amount=spec.oa_amount,
        note=f"{spec.label} ETC 历史 OA 已提交补关联；用户确认金额差异可接受。",
    )
    invoices = app._etc_service.list_invoices_by_ids(list(batch.invoice_ids))
    changed_months = app._sync_etc_invoices_to_canonical_invoices(invoices)
    app._refresh_after_etc_invoice_sync(changed_months, reason="historical_etc_batch_link")

    relation = app._workbench_pair_relation_service.create_active_relation(
        case_id=spec.case_id,
        row_ids=[spec.oa_row_id],
        row_types=["oa"],
        relation_mode="etc_batch_invoice_link",
        created_by="system_historical_repair",
        month_scope="all",
        note=f"{spec.label} ETC 历史补关联",
        amount_check={
            "status": "matched" if batch.amount_delta == Decimal("0.00") else "mismatch",
            "oa_amount": f"{spec.oa_amount:.2f}",
            "invoice_total": f"{batch.total_amount:.2f}",
            "delta": f"{batch.amount_delta:.2f}",
            "etc_batch_id": batch.id,
            "external_etc_batch_id": batch.etc_batch_id,
            "source": "historical_repair",
        },
    )
    app._persist_workbench_pair_relations(changed_case_ids=[str(relation["case_id"])])
    app._invalidate_workbench_read_model_scopes(["all", *changed_months])
    if app._state_store is not None:
        app._state_store.save_etc_state(app._etc_service.snapshot())


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair 2026 Jan-Mar historical ETC batches.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only. This is the default.")
    parser.add_argument("--apply", action="store_true", help="Write repaired batches into the app state.")
    parser.add_argument("--seed-mongo", action="store_true", help="Store the three historical ETC zip bundles in the configured app Mongo/GridFS store.")
    parser.add_argument("--reconcile", action="store_true", help="Run the production historical ETC repair reconcile service.")
    args = parser.parse_args()

    if args.seed_mongo or args.reconcile:
        os.environ["FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR"] = "1"

    app = build_application(data_dir=DATA_DIR)
    plan: list[tuple[HistoricalEtcBatchSpec, UploadedEtcZipFile, list[str]]] = []
    needs_local_zip_plan = args.seed_mongo or args.apply or args.dry_run or not args.reconcile
    if needs_local_zip_plan:
        for spec in SPECS:
            upload = load_upload(spec)
            parsed_invoices = parse_unique_zip_invoices(app, upload)
            invoice_numbers = selected_invoice_numbers(parsed_invoices, spec)
            print_batch_preview(app, spec, parsed_invoices, invoice_numbers)
            plan.append((spec, upload, invoice_numbers))

    seeded_any = False
    if args.seed_mongo:
        if app._historical_etc_repair_service is None:
            raise RuntimeError("Historical ETC repair service is not available.")
        for spec, upload, _invoice_numbers in plan:
            service_spec = SERVICE_SPECS_BY_BUNDLE_ID[spec.external_batch_id]
            saved = app._historical_etc_repair_service.seed_bundle_from_upload(service_spec, upload)
            print(f"Seeded {spec.label}: {saved.get('bundle_id') or saved.get('_id')} sha256={saved.get('sha256')}")
        seeded_any = True

    if args.reconcile:
        if app._historical_etc_repair_service is None:
            raise RuntimeError("Historical ETC repair service is not available.")
        started_at = monotonic()
        result = app._historical_etc_repair_service.reconcile(reason="maintenance_script")
        payload = app._serialize_value(result.to_payload())
        payload["duration_seconds"] = round(monotonic() - started_at, 2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if seeded_any and not args.apply:
        print("\nSeed completed. Re-run with --reconcile to execute the production repair service.")
        return 0

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write app state.")
        return 0

    for spec, upload, invoice_numbers in plan:
        apply_batch(app, spec, upload, invoice_numbers)
        print(f"Applied {spec.label}: {spec.external_batch_id} -> {spec.oa_row_id}")
    print("\nHistorical ETC repair completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
