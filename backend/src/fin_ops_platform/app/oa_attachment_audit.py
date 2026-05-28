from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_attachment_audit import (
    AUDIT_START_DATE,
    audit_oa_attachment_records,
    write_oa_attachment_audit_report,
)
from fin_ops_platform.services.state_store import ApplicationStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit OA attachment formal invoice parsing status.")
    parser.add_argument("--data-dir", default=".runtime/fin_ops_platform")
    parser.add_argument("--output-dir", default="tmp/oa_attachment_invoice_audit")
    parser.add_argument("--from-date", default=AUDIT_START_DATE.isoformat())
    parser.add_argument("--force-parse", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    settings = load_mongo_oa_settings(data_dir)
    if settings is None:
        raise SystemExit("OA Mongo settings are missing.")
    start_date = datetime.strptime(str(args.from_date)[:10], "%Y-%m-%d").date()
    start_month = start_date.strftime("%Y-%m")
    cache = ApplicationStateStore(data_dir)
    adapter = MongoOAAdapter(settings=settings, attachment_invoice_cache=cache)
    months = [
        month
        for month in adapter.list_available_months()
        if len(str(month)) == 7 and str(month) >= start_month
    ]
    records = []
    context = adapter.force_attachment_invoice_reparse() if args.force_parse else adapter.force_attachment_invoice_sync_parse()
    with context:
        for month in months:
            records.extend(adapter.list_application_records(month))
    report = audit_oa_attachment_records(records, start_date=start_date)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    paths = write_oa_attachment_audit_report(
        report,
        Path(args.output_dir),
        stem=f"oa_attachment_formal_invoice_audit_since_{start_date.isoformat()}_{timestamp}",
    )
    print(f"JSON: {paths['json']}")
    print(f"CSV: {paths['csv']}")
    print(report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
