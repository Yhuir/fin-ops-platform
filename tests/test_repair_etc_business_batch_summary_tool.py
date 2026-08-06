from __future__ import annotations

from contextlib import contextmanager
from io import StringIO

from fin_ops_platform.tools import repair_etc_business_batch_summary
from fin_ops_platform.tools.repair_etc_business_batch_summary import (
    apply_summary_repair,
    preview_summary_repair,
)
from fin_ops_platform.tools.repair_submitted_etc_batch_members import main as submitted_member_repair_main


class SummaryRepairConnection:
    def __init__(self, *, raw_invoice_ids: list[str] | None = None) -> None:
        self.batch = {
            "business_batch_id": "etc-business-1",
            "status": "manually_marked_submitted",
            "invoice_count": 2,
            "total_amount": "1935.45",
            "version": 2,
            "raw_payload": {
                "normalized_payload": {
                    "business_batch_id": "etc-business-1",
                    "invoice_ids": raw_invoice_ids if raw_invoice_ids is not None else ["etc-invoice-1", "etc-invoice-2"],
                    "version": 2,
                    "audit_events": [],
                }
            },
        }
        self.members = [
            {"etc_invoice_id": "etc-invoice-1", "total_with_tax": "900.00"},
            {"etc_invoice_id": "etc-invoice-2", "total_with_tax": "979.45"},
        ]
        self.executed: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        _ = sql, params
        return dict(self.batch)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        _ = sql, params
        return [dict(row) for row in self.members]

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    @contextmanager
    def transaction(self):
        yield self


def test_summary_repair_preview_uses_exact_member_count_and_total() -> None:
    report = preview_summary_repair(SummaryRepairConnection(), "etc-business-1")

    assert report["status"] == "ready"
    assert report["stored_total_amount"] == "1935.45"
    assert report["actual_invoice_count"] == 2
    assert report["actual_total_amount"] == "1879.45"


def test_summary_repair_apply_is_fingerprint_guarded_and_audited() -> None:
    connection = SummaryRepairConnection()
    preview = preview_summary_repair(connection, "etc-business-1")

    result = apply_summary_repair(
        connection,
        "etc-business-1",
        expected_fingerprint=preview["fingerprint"],
        operator="codex-production-repair",
        reason="restore ETC invoice summary semantics",
    )

    assert result["status"] == "repaired"
    assert result["new_version"] == 3
    assert len(connection.executed) == 2
    assert "update app.etc_business_batches" in connection.executed[0][0]
    assert connection.executed[0][1][:2] == (2, "1879.45")
    assert "insert into audit.events" in connection.executed[1][0]


def test_summary_repair_blocks_when_raw_and_formal_members_differ() -> None:
    report = preview_summary_repair(
        SummaryRepairConnection(raw_invoice_ids=["etc-invoice-1"]),
        "etc-business-1",
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"] == ["business_batch_member_facts_mismatch"]


def test_existing_submitted_member_repair_command_delegates_summary_only(monkeypatch) -> None:
    received: list[str] = []

    def fake_main(argv, *, stdout):
        _ = stdout
        received.extend(argv)
        return 0

    monkeypatch.setattr(repair_etc_business_batch_summary, "main", fake_main)

    exit_code = submitted_member_repair_main(
        ["--business-batch-id", "etc-business-1", "--summary-only", "--dry-run"],
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert received == ["--business-batch-id", "etc-business-1", "--dry-run"]
