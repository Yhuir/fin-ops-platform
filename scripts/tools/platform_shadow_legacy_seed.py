#!/usr/bin/env python3
"""Seed isolated legacy Python state with deterministic P0 platform shadow facts."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.domain.enums import LedgerStatus, LedgerType, ReminderStatus, TransactionDirection, TransactionStatus
from fin_ops_platform.domain.models import BankTransaction, FollowUpLedger, Reminder
from fin_ops_platform.services.background_job_service import BackgroundJob
from fin_ops_platform.services.state_store import ApplicationStateStore


DEFAULT_OUTPUT_DIR = ROOT / "docs" / "operations" / "backend-refactor"
SEED_DATE = "2026-05-17"
SEED_TS = "2026-05-17T01:00:00+00:00"
ACCEPTED_OA_IDENTITY_SOURCES = {
    "staging_oa": "staging",
    "test_oa": "staging",
    "production_oa_test_user": "production",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.environ.get("SHADOW_RUN_ID"))
    parser.add_argument("--actor-id", default=os.environ.get("FIN_OPS_SHADOW_OA_USER_ID"))
    parser.add_argument("--user-id", default=os.environ.get("FIN_OPS_SHADOW_OA_USER_ID"))
    parser.add_argument("--username", default=os.environ.get("FIN_OPS_SHADOW_OA_USERNAME"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-date", default=datetime.now(UTC).strftime("%Y%m%d"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = (args.run_id or "").strip()
    if not run_id:
        raise SystemExit("--run-id or SHADOW_RUN_ID is required")
    username = str(args.username or "").strip()
    if not username:
        raise SystemExit("--username or FIN_OPS_SHADOW_OA_USERNAME is required")
    user_id = str(args.user_id or args.actor_id or "").strip()
    if not user_id:
        raise SystemExit("--user-id or FIN_OPS_SHADOW_OA_USER_ID is required")
    seed = load_platform_shadow_seed_module()
    plan = seed.build_seed_plan(run_id=run_id, actor_id=username, user_id=user_id)
    payload = build_legacy_seed_payload(plan=plan, username=username, user_id=user_id)

    args.data_dir.mkdir(parents=True, exist_ok=True)
    apply_legacy_seed(data_dir=args.data_dir, payload=payload)

    report = build_report(
        plan=plan,
        payload=payload,
        data_dir=args.data_dir,
        report_date=args.report_date,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / f"p0-platform-legacy-shadow-seed-{safe_name(args.report_date)}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), **report}, ensure_ascii=False, indent=2))
    return 0


def load_platform_shadow_seed_module():
    path = ROOT / "scripts" / "tools" / "platform_shadow_seed.py"
    spec = importlib.util.spec_from_file_location("platform_shadow_seed_for_legacy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_legacy_seed_payload(*, plan: Any, username: str, user_id: str) -> dict[str, Any]:
    username = str(username).strip()
    user_id = str(user_id).strip()
    return {
        "run_id": plan.run_id,
        "runtime_variables": dict(plan.runtime_variables),
        "identity": {"username": username, "user_id": user_id},
        "app_settings": app_settings_payload(plan=plan, username=username),
        "background_jobs": {
            plan.background_job_id: background_job_payload(plan=plan, user_id=user_id),
        },
        "imports": imports_payload(plan=plan),
        "platform_shadow_legacy_seed": ledger_seed_payload(plan=plan, user_id=user_id),
    }


def apply_legacy_seed(*, data_dir: Path, payload: dict[str, Any]) -> None:
    previous_storage_mode = os.environ.get("FIN_OPS_STORAGE_MODE")
    os.environ["FIN_OPS_STORAGE_MODE"] = "auto"
    try:
        store = ApplicationStateStore(data_dir)
        store.save_app_settings(payload["app_settings"])
        store.save_background_jobs(payload["background_jobs"])
        current_state = store.load()
        current_state["imports"] = payload["imports"]
        current_state["platform_shadow_legacy_seed"] = payload["platform_shadow_legacy_seed"]
        store.save(current_state)
    finally:
        if previous_storage_mode is None:
            os.environ.pop("FIN_OPS_STORAGE_MODE", None)
        else:
            os.environ["FIN_OPS_STORAGE_MODE"] = previous_storage_mode


def app_settings_payload(*, plan: Any, username: str) -> dict[str, Any]:
    return {
        "completed_project_ids": [],
        "manual_projects": [
            project_payload(
                project_id=plan.project_id,
                project_code=f"SHADOW-{safe_code(plan.run_id)}-MAIN",
                project_name="平台 Shadow 项目",
            ),
            project_payload(
                project_id=plan.project_delete_id,
                project_code=f"SHADOW-{safe_code(plan.run_id)}-DELETE",
                project_name="平台 Shadow 待删除项目",
            ),
        ],
        "synced_projects": [],
        "bank_account_mappings": [
            {
                "bank_name": "Shadow Bank",
                "last4": "0001",
                "account_no": "6222000000000000001",
                "account_name": "平台 Shadow 账户",
            }
        ],
        "allowed_usernames": [username],
        "readonly_export_usernames": [],
        "admin_usernames": [username],
        "workbench_column_layouts": {
            "oa": ["applicant", "projectName", "amount", "counterparty", "reason"],
            "bank": ["counterparty", "amount", "loanRepaymentDate", "note"],
            "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
        },
        "oa_retention": {"cutoff_date": "2026-01-01"},
        "oa_import": {"form_types": ["payment_request", "expense_claim"], "statuses": ["completed"]},
        "oa_invoice_offset": {"applicant_names": ["周洁莹"]},
    }


def project_payload(*, project_id: str, project_code: str, project_name: str) -> dict[str, Any]:
    return {
        "id": project_id,
        "project_code": project_code,
        "project_name": project_name,
        "project_status": "active",
        "department_name": "平台 Shadow",
        "owner_name": "Shadow Owner",
    }


def background_job_payload(*, plan: Any, user_id: str) -> dict[str, Any]:
    job = BackgroundJob(
        job_id=plan.background_job_id,
        type="platform_shadow_background_job",
        label="Platform shadow background job",
        short_label="Platform shadow",
        owner_user_id=user_id,
        visibility="system",
        status="failed",
        phase="failed",
        current=1,
        total=1,
        percent=100,
        message="Platform shadow attention job ready for acknowledge.",
        result_summary={"fixture": "platform_shadow", "run_id": plan.run_id},
        error="platform_shadow_ack_fixture",
        idempotency_key=f"platform-shadow:{plan.run_id}:background-job",
        source={"fixture": "platform_shadow", "run_id": plan.run_id},
        affected_scopes=["platform_shadow"],
        affected_months=[],
        created_at=SEED_TS,
        started_at=SEED_TS,
        updated_at=SEED_TS,
        finished_at=SEED_TS,
        acknowledged_at=None,
        superseded_by_job_id=None,
        superseded_at=None,
    )
    return job.to_payload()


def imports_payload(*, plan: Any) -> dict[str, Any]:
    transaction = BankTransaction(
        id=plan.bank_transaction_id,
        account_no="6222000000000000001",
        txn_direction=TransactionDirection.INFLOW,
        counterparty_name_raw="平台 Shadow 往来单位",
        amount=Decimal("1288.00"),
        signed_amount=Decimal("1288.00"),
        bank_serial_no=f"SHADOW-{safe_code(plan.run_id)}-BANK",
        source_unique_key=f"platform-shadow:{plan.run_id}:bank-transaction",
        data_fingerprint=f"platform-shadow:{plan.run_id}:bank-transaction",
        written_off_amount=Decimal("0.00"),
        txn_date=SEED_DATE,
        trade_time=f"{SEED_DATE}T09:00:00+08:00",
        counterparty_id="platform-shadow-counterparty",
        project_id=None,
        source_batch_id=f"platform-shadow-batch-{safe_code(plan.run_id)}",
        account_name="平台 Shadow 账户",
        currency="CNY",
        summary="平台 Shadow 银行流水",
        status=TransactionStatus.PENDING,
    )
    return {
        "batch_counter": 1,
        "row_counter": 1,
        "invoice_counter": 0,
        "txn_counter": 1,
        "counterparty_counter": 0,
        "batches": {},
        "invoices": [],
        "transactions": [transaction],
    }


def ledger_seed_payload(*, plan: Any, user_id: str) -> dict[str, Any]:
    return {
        "schema": "p0-platform-legacy-shadow-seed-v1",
        "run_id": plan.run_id,
        "ledgers": [
            {
                "id": plan.ledger_id,
                "ledger_type": LedgerType.PAYMENT_COLLECTION.value,
                "source_object_type": "bank_transaction",
                "source_object_id": plan.bank_transaction_id,
                "counterparty_id": "platform-shadow-counterparty",
                "open_amount": "1288.00",
                "expected_date": SEED_DATE,
                "owner_id": user_id,
                "status": LedgerStatus.OPEN.value,
                "source_case_id": None,
                "project_id": plan.project_id,
                "latest_note": "平台 Shadow 台账",
                "created_at": SEED_TS,
            }
        ],
        "reminders": [
            {
                "id": plan.reminder_id,
                "ledger_id": plan.ledger_id,
                "remind_at": SEED_DATE,
                "channel": "in_app",
                "status": ReminderStatus.PENDING.value,
                "created_at": SEED_TS,
            }
        ],
    }


def build_report(*, plan: Any, payload: dict[str, Any], data_dir: Path, report_date: str) -> dict[str, Any]:
    token_present = bool(os.environ.get("FIN_OPS_SHADOW_OA_TOKEN"))
    password_present = bool(os.environ.get("FIN_OPS_SHADOW_OA_PASSWORD"))
    identity_source = os.environ.get("FIN_OPS_SHADOW_OA_IDENTITY_SOURCE", "").strip()
    identity_source_environment = ACCEPTED_OA_IDENTITY_SOURCES.get(identity_source)
    identity_source_status = "GO" if identity_source_environment else "NO_GO"
    secret_status = "GO" if token_present and password_present and identity_source_status == "GO" else "NO_GO"
    blocking_items: list[str] = []
    if not token_present:
        blocking_items.append(
            "FIN_OPS_SHADOW_OA_TOKEN is missing; export a real token for the accepted OA identity source before runtime shadow."
        )
    if not password_present:
        blocking_items.append(
            "FIN_OPS_SHADOW_OA_PASSWORD is missing; export the matching password for settings data reset runtime samples."
        )
    if identity_source_status != "GO":
        blocking_items.append(
            "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE is missing or unsupported; accepted values are "
            + ", ".join(sorted(ACCEPTED_OA_IDENTITY_SOURCES))
            + "."
        )
    return {
        "report": f"p0-platform-legacy-shadow-seed-{report_date}",
        "report_date": report_date,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "GO" if secret_status == "GO" else "NO_GO",
        "scope": "Isolated legacy Python state seed for P0 platform runtime shadow.",
        "data_dir": str(data_dir),
        "run_id": plan.run_id,
        "runtime_variables": dict(plan.runtime_variables),
        "legacy_python_seed": {
            "status": "GO",
            "storage_mode": "auto",
            "state_files": ["app_settings.json", "background_jobs.pkl", "state.pkl"],
            "runtime_reload_required": "restart_or_reload_required",
            "reload_note": (
                "LedgerReminderService loads platform_shadow_legacy_seed from the isolated data-dir "
                "during Application startup; an already-running legacy Python process must be restarted "
                "or given an explicit non-production reload hook before ledger/reminder seed facts enter memory."
            ),
            "seeded_collections": [
                "app_settings.manual_projects",
                "background_jobs",
                "imports.transactions",
                "platform_shadow_legacy_seed.ledgers",
                "platform_shadow_legacy_seed.reminders",
            ],
        },
        "secret_requirements": {
            "status": secret_status,
            "identity_source": {
                "name": "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE",
                "value": identity_source or None,
                "status": identity_source_status,
                "accepted_values": sorted(ACCEPTED_OA_IDENTITY_SOURCES),
                "environment": identity_source_environment,
                "risk_note": (
                    "Production OA test user is accepted only as identity/password source; business writes must target isolated shadow data stores."
                    if identity_source == "production_oa_test_user"
                    else None
                ),
            },
            "required": [
                {
                    "name": "FIN_OPS_SHADOW_OA_TOKEN",
                    "present": token_present,
                    "sensitive": True,
                    "required_for": "legacy Python Authorization header",
                },
                {
                    "name": "FIN_OPS_SHADOW_OA_PASSWORD",
                    "present": password_present,
                    "sensitive": True,
                    "required_for": "settings data reset runtime samples",
                },
            ],
        },
        "go_standard": {
            "legacy_python_state_seeded": "GO",
            "same_runtime_ids_as_postgres_seed": "GO",
            "real_oa_token_password_present": secret_status,
            "oa_identity_source_accepted": identity_source_status,
            "overall": "GO" if secret_status == "GO" else "NO_GO",
        },
        "blocking_items": blocking_items,
        "non_secret_sample": {
            "manual_project_count": len(payload["app_settings"]["manual_projects"]),
            "background_job_count": len(payload["background_jobs"]),
            "bank_transaction_count": len(payload["imports"]["transactions"]),
            "ledger_count": len(payload["platform_shadow_legacy_seed"]["ledgers"]),
            "reminder_count": len(payload["platform_shadow_legacy_seed"]["reminders"]),
        },
    }


def ledger_from_seed(item: dict[str, Any]) -> FollowUpLedger:
    return FollowUpLedger(
        id=str(item["id"]),
        ledger_type=LedgerType(str(item["ledger_type"])),
        source_object_type=str(item["source_object_type"]),
        source_object_id=str(item["source_object_id"]),
        counterparty_id=str(item["counterparty_id"]),
        open_amount=Decimal(str(item["open_amount"])),
        expected_date=str(item["expected_date"]),
        owner_id=str(item["owner_id"]),
        status=LedgerStatus(str(item.get("status") or LedgerStatus.OPEN.value)),
        source_case_id=item.get("source_case_id"),
        project_id=item.get("project_id"),
        latest_note=item.get("latest_note"),
        created_at=parse_datetime(item.get("created_at")),
    )


def reminder_from_seed(item: dict[str, Any]) -> Reminder:
    return Reminder(
        id=str(item["id"]),
        ledger_id=str(item["ledger_id"]),
        remind_at=str(item["remind_at"]),
        channel=str(item.get("channel") or "in_app"),
        status=ReminderStatus(str(item.get("status") or ReminderStatus.PENDING.value)),
        sent_result=item.get("sent_result"),
        sent_at=parse_optional_datetime(item.get("sent_at")),
        created_at=parse_datetime(item.get("created_at")),
    )


def parse_datetime(value: Any) -> datetime:
    parsed = parse_optional_datetime(value)
    return parsed or datetime.now(UTC)


def parse_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value)).strip("-") or "shadow"


def safe_code(value: str) -> str:
    return safe_name(value).upper().replace("_", "-")


if __name__ == "__main__":
    raise SystemExit(main())
