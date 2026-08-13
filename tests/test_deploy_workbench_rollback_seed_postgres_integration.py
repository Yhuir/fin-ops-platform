from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONTROL = REPO_ROOT / "deploy/oa/bin/finops-deploy-control.sh"


def _rollback_seed_function_source() -> str:
    deploy_control = DEPLOY_CONTROL.read_text(encoding="utf-8")
    return deploy_control.split("seed_previous_workbench_rehydrate_scopes() {", 1)[1].split(
        "\nprepare_previous_workbench_page_runtime() {",
        1,
    )[0]


def _rollback_seed_upsert_sql() -> str:
    seed_source = _rollback_seed_function_source()
    fetch_source = seed_source.split("row = transaction.fetch_one(", 1)[1]
    return fetch_source.split('"""', 1)[1].split('"""', 1)[0]


def _seed_scopes(connection: PostgresConnection, scope_keys: list[str]) -> list[dict[str, object]]:
    seeded: list[dict[str, object]] = []
    with connection.transaction() as transaction:
        processing = transaction.fetch_all(
            """
            select scope_key
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = %s
              and status = %s
              and scope_key = any(%s::text[])
            order by scope_key
            """,
            ("default", "workbench", "processing", scope_keys),
        )
        if processing:
            raise RuntimeError("cannot seed rollback rehydrate while a Workbench dirty scope is processing")
        for scope_key in scope_keys:
            marker = {
                "reason": "direct_only_release_rollback_rehydrate",
                "rollback_rehydrate_seed": {
                    "scope_key": scope_key,
                    "source": "finops-deploy-control",
                },
            }
            row = transaction.fetch_one(
                _rollback_seed_upsert_sql(),
                (
                    "default",
                    "workbench",
                    scope_key,
                    f"{scope_key}-01" if scope_key != "all" else None,
                    "direct_only_release_rollback_rehydrate",
                    "default",
                    "workbench",
                    scope_key,
                    "pending",
                    jsonb(marker),
                    jsonb(marker),
                    "pending",
                    "pending",
                ),
            )
            if row is None:
                raise RuntimeError(f"failed to seed rollback rehydrate scope {scope_key}")
            seeded.append(dict(row))
    return seeded


class DeployWorkbenchRollbackSeedSourceTests(unittest.TestCase):
    def test_partial_unique_arbiter_predicate_is_literal_and_not_parameterized(self) -> None:
        normalized_sql = " ".join(_rollback_seed_upsert_sql().lower().split())

        self.assertIn(
            "on conflict (tenant_id, scope_type, scope_key) "
            "where status in ($$pending$$, $$processing$$) do update set",
            normalized_sql,
        )
        self.assertNotIn("where status in (%s, %s)", normalized_sql)


class DeployWorkbenchRollbackSeedPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def _insert_scope(
        self,
        scope_key: str,
        *,
        status: str,
        source_version: int,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self.connection.fetch_one(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, month, reason,
                source_version, status, payload, raw_payload
            )
            values (
                'default', 'workbench', %s, %s::date, 'existing',
                %s, %s, %s, %s
            )
            returning id, scope_key, source_version, status
            """,
            (
                scope_key,
                f"{scope_key}-01" if scope_key != "all" else None,
                source_version,
                status,
                jsonb(payload or {}),
                jsonb(payload or {}),
            ),
        ) or {}

    def test_existing_pending_scope_is_updated_through_partial_unique_index(self) -> None:
        existing = self._insert_scope(
            "2026-08",
            status="pending",
            source_version=7,
            payload={"existing": True},
        )

        seeded = _seed_scopes(self.connection, ["2026-08"])

        self.assertEqual(
            seeded,
            [{"scope_key": "2026-08", "source_version": 8, "status": "pending"}],
        )
        active = self.connection.fetch_one(
            """
            select id, reason, source_version, status, payload, raw_payload
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = '2026-08'
              and status in ('pending', 'processing')
            """
        ) or {}
        self.assertEqual(active["id"], existing["id"])
        self.assertEqual(active["source_version"], 8)
        self.assertEqual(active["status"], "pending")
        self.assertEqual(active["reason"], "direct_only_release_rollback_rehydrate")
        self.assertTrue(active["payload"]["existing"])
        self.assertEqual(
            active["payload"]["rollback_rehydrate_seed"]["scope_key"],
            "2026-08",
        )
        self.assertEqual(active["payload"], active["raw_payload"])

    def test_done_history_is_preserved_and_new_pending_scope_is_inserted(self) -> None:
        done = self._insert_scope(
            "2026-08",
            status="done",
            source_version=4,
            payload={"history": True},
        )

        seeded = _seed_scopes(self.connection, ["2026-08"])

        self.assertEqual(
            seeded,
            [{"scope_key": "2026-08", "source_version": 5, "status": "pending"}],
        )
        rows = self.connection.fetch_all(
            """
            select id, month::text as month, source_version, status, payload
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = '2026-08'
            order by source_version
            """
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], done["id"])
        self.assertEqual(rows[0]["status"], "done")
        self.assertEqual(rows[0]["payload"], {"history": True})
        self.assertEqual(rows[1]["status"], "pending")
        self.assertEqual(rows[1]["source_version"], 5)
        self.assertEqual(rows[1]["month"], "2026-08-01")

    def test_processing_scope_fails_closed_and_rolls_back_all_requested_scopes(self) -> None:
        processing = self._insert_scope(
            "2026-09",
            status="processing",
            source_version=3,
            payload={"locked": True},
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "cannot seed rollback rehydrate while a Workbench dirty scope is processing",
        ):
            _seed_scopes(self.connection, ["2026-08", "2026-09"])

        rows = self.connection.fetch_all(
            """
            select id, scope_key, source_version, status, payload
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = any(%s::text[])
            order by scope_key
            """,
            (["2026-08", "2026-09"],),
        )
        self.assertEqual(
            rows,
            [
                {
                    "id": processing["id"],
                    "scope_key": "2026-09",
                    "source_version": 3,
                    "status": "processing",
                    "payload": {"locked": True},
                }
            ],
        )
