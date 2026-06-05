from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app import bank_account_balance_backfill
from fin_ops_platform.app import bank_detail_backfill


class BankdetailBackfillCliTests(unittest.TestCase):
    def test_bank_account_balance_backfill_dry_run_does_not_open_postgres(self) -> None:
        with patch.object(bank_account_balance_backfill, "PostgresConnection", side_effect=AssertionError("no db")):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = bank_account_balance_backfill.main(["--dry-run"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["plan"]["scope_type"], "bank_account_balance")
        self.assertEqual(payload["plan"]["scope_key"], "all")
        self.assertFalse(payload["enqueued"])

    def test_bank_detail_backfill_explicit_scope_dry_run_does_not_open_postgres(self) -> None:
        with patch.object(bank_detail_backfill, "PostgresConnection", side_effect=AssertionError("no db")):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = bank_detail_backfill.main(["--dry-run", "--scope-key", "2026-05"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["plan"]["scope_keys"], ["2026-05"])
        self.assertEqual(payload["enqueued_scope_keys"], [])
        self.assertEqual(payload["drain_result"], [])

    def test_bank_account_balance_backfill_enqueue_uses_durable_queue_contract(self) -> None:
        class Queue:
            def __init__(self, _connection: object) -> None:
                self.enqueued: list[dict[str, object]] = []
                queues.append(self)

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queues: list[Queue] = []
        with (
            patch.object(bank_account_balance_backfill.PostgresSettings, "from_env", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "PostgresConnection", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "RuntimeQueueRepository", Queue),
            patch.object(bank_account_balance_backfill, "BankAccountBalanceProjectionBuilder", return_value=SimpleNamespace()),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = bank_account_balance_backfill.main(["--enqueue"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            queues[0].enqueued,
            [
                {
                    "scope_type": "bank_account_balance",
                    "scope_key": "all",
                    "reason": "bank_account_balance_backfill",
                }
            ],
        )
        self.assertTrue(json.loads(output.getvalue())["enqueued"])

    def test_bank_detail_backfill_enqueue_all_and_missing_use_expected_reasons(self) -> None:
        class Queue:
            def __init__(self, _connection: object) -> None:
                self.enqueued: list[dict[str, object]] = []
                queues.append(self)

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queues: list[Queue] = []
        projection = SimpleNamespace(list_bank_detail_scope_shards=lambda _scope: ["2026-04", "2026-05"])
        with (
            patch.object(bank_detail_backfill.PostgresSettings, "from_env", return_value=SimpleNamespace()),
            patch.object(bank_detail_backfill, "PostgresConnection", return_value=SimpleNamespace()),
            patch.object(bank_detail_backfill, "RuntimeQueueRepository", Queue),
            patch.object(bank_detail_backfill, "BankDetailSqlProjectionBuilder", return_value=projection),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = bank_detail_backfill.main(["--enqueue-all", "--enqueue-missing"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            queues[0].enqueued,
            [
                {"scope_type": "bank_detail", "scope_key": "all", "reason": "bank_detail_backfill_all"},
                {"scope_type": "bank_detail", "scope_key": "2026-04", "reason": "bank_detail_backfill_missing"},
                {"scope_type": "bank_detail", "scope_key": "2026-05", "reason": "bank_detail_backfill_missing"},
            ],
        )
        self.assertEqual(json.loads(output.getvalue())["enqueued_scope_keys"], ["all", "2026-04", "2026-05"])

    def test_bank_account_balance_worker_drain_wires_expected_event_type_and_handler(self) -> None:
        class Worker:
            def __init__(self, *, queue_repository, config, handlers) -> None:
                self.config = config
                self.handlers = handlers
                workers.append(self)

            def run_once(self):
                return "idle"

        workers: list[Worker] = []
        with (
            patch.object(bank_account_balance_backfill.PostgresSettings, "from_env", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "PostgresConnection", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "RuntimeQueueRepository", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "BankAccountBalanceProjectionBuilder", return_value=SimpleNamespace()),
            patch.object(bank_account_balance_backfill, "RuntimeWorker", Worker),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = bank_account_balance_backfill.main(["--worker-drain", "--max-iterations", "1"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(workers[0].config.worker_kind, "bank-account-balance-read-model")
        self.assertEqual(workers[0].config.event_types, ["bank_account_balance.read_model.refresh"])
        self.assertEqual(list(workers[0].handlers), ["bank_account_balance.read_model.refresh"])
        self.assertEqual(json.loads(output.getvalue())["drain_result"], ["idle"])


if __name__ == "__main__":
    unittest.main()
