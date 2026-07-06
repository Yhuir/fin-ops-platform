from __future__ import annotations

import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY  # noqa: E402
from fin_ops_platform.tools import write_operation_scenario_discovery, write_operation_slo_audit  # noqa: E402


MATRIX_PATH = REPO_ROOT / "docs" / "dev" / "write-operation-impact-matrix.json"
PAGE_MATRIX_PATH = REPO_ROOT / "docs" / "dev" / "page-read-model-fact-display-matrix.json"

APPLY_POLICIES = {
    "standing_apply",
    "audit_profile_only",
    "single_use_approval_required",
    "legacy_audit_only",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_scope_types_by_operation() -> dict[str, set[str]]:
    scope_types_by_operation: dict[str, set[str]] = defaultdict(set)
    for expectation in write_operation_slo_audit.DEFAULT_OPERATION_EXPECTATIONS:
        scope_types_by_operation[expectation.operation].add(expectation.scope_type)
    return dict(scope_types_by_operation)


class WriteOperationImpactMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = _load_json(MATRIX_PATH)
        self.rows = list(self.matrix["operations"])
        self.rows_by_operation = {str(row["operation"]): row for row in self.rows}
        page_matrix = _load_json(PAGE_MATRIX_PATH)
        self.page_rows_by_key = {str(row["page_key"]): row for row in page_matrix["rows"]}

    def test_matrix_covers_every_write_operation_slo_profile(self) -> None:
        audit_operations = set(_audit_scope_types_by_operation())
        matrix_operations = set(self.rows_by_operation)

        self.assertEqual(matrix_operations - audit_operations, set())
        self.assertEqual(audit_operations - matrix_operations, set())
        self.assertEqual(len(self.rows), len(matrix_operations))

    def test_matrix_scope_types_match_write_operation_slo_expectations(self) -> None:
        audit_scope_types_by_operation = _audit_scope_types_by_operation()

        for operation, row in self.rows_by_operation.items():
            self.assertEqual(
                set(row["expected_outbox_scope_types"]),
                audit_scope_types_by_operation[operation],
                operation,
            )
            self.assertEqual(set(row["target_read_model_keys"]), set(row["expected_outbox_scope_types"]), operation)

    def test_slo_targets_match_runtime_write_operation_gates(self) -> None:
        slo = self.matrix["slo"]

        self.assertEqual(slo["p95_enqueue_to_done_ms"], write_operation_slo_audit.DEFAULT_TARGET_MS)
        self.assertEqual(
            slo["p99_enqueue_to_done_ms"],
            write_operation_slo_audit.effective_p99_target_ms_for(write_operation_slo_audit.DEFAULT_TARGET_MS, None),
        )

    def test_scope_and_page_targets_are_current_read_model_contracts(self) -> None:
        valid_read_model_keys = set(APP_STATUS_READ_MODEL_REGISTRY)
        valid_page_keys = set(self.page_rows_by_key)

        for operation, row in self.rows_by_operation.items():
            target_read_model_keys = set(row["target_read_model_keys"])
            self.assertEqual(target_read_model_keys - valid_read_model_keys, set(), operation)

            for page_key in row["source_page_keys"]:
                self.assertIn(page_key, valid_page_keys, operation)
            for page_key in row["target_page_keys"]:
                self.assertIn(page_key, valid_page_keys, operation)
                page_read_model_keys = set(self.page_rows_by_key[page_key]["read_model_keys"])
                accepted_read_model_keys = target_read_model_keys | set(row.get("legacy_page_proxy_read_model_keys", []))
                self.assertTrue(
                    page_read_model_keys & accepted_read_model_keys,
                    f"{operation}: {page_key} has no declared impacted read model",
                )

    def test_pairing_operations_use_the_canonical_relation_fact_sources(self) -> None:
        for operation, row in self.rows_by_operation.items():
            relation_sources = set(row["pairing_relation_fact_sources"])
            if "workbench_relation" in set(row["expected_outbox_scope_types"]):
                self.assertIn("app.workbench_pair_relations", relation_sources, operation)
                self.assertIn("read_model.workbench_relation_rows", relation_sources, operation)
            else:
                self.assertEqual(relation_sources, set(), operation)

    def test_production_gate_policy_is_explicit_and_matches_standing_ticket_rules(self) -> None:
        policy_by_page = {
            str(policy["page_key"]): policy
            for policy in write_operation_scenario_discovery.STANDARD_PAGE_WRITE_SCENARIO_POLICIES
        }

        for operation, row in self.rows_by_operation.items():
            gate = row["production_gate"]
            apply_policy = gate["apply_policy"]
            self.assertEqual(gate["slo_audit_profile"], operation)
            self.assertIn(apply_policy, APPLY_POLICIES, operation)

            if apply_policy != "standing_apply":
                continue

            self.assertEqual(gate["approval_ticket"], write_operation_scenario_discovery.STANDARD_APPROVAL_TICKET)
            self.assertIn(operation, write_operation_scenario_discovery.STANDARD_WRITE_OPERATIONS)
            self.assertTrue(
                any(
                    policy_by_page.get(page_key, {}).get("apply_policy") == "standing_apply"
                    and operation in policy_by_page.get(page_key, {}).get("scenario_operations", ())
                    for page_key in row["source_page_keys"]
                ),
                operation,
            )

    def test_deterministic_evidence_files_exist_and_contain_required_markers(self) -> None:
        for operation, row in self.rows_by_operation.items():
            evidence_entries = list(row["deterministic_evidence"])
            self.assertTrue(evidence_entries, operation)

            for evidence in evidence_entries:
                evidence_path = REPO_ROOT / evidence["path"]
                self.assertTrue(evidence_path.exists(), f"{operation}: {evidence_path}")
                evidence_text = evidence_path.read_text(encoding="utf-8")
                markers = list(evidence["required_markers"])
                self.assertTrue(markers, f"{operation}: {evidence_path}")
                for marker in markers:
                    self.assertIn(marker, evidence_text, f"{operation}: {evidence['path']} missing {marker!r}")


if __name__ == "__main__":
    unittest.main()
