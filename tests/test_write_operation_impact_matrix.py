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
from fin_ops_platform.tools import (  # noqa: E402
    write_operation_e2e_smoke,
    write_operation_scenario_discovery,
    write_operation_slo_audit,
)


MATRIX_PATH = REPO_ROOT / "docs" / "dev" / "write-operation-impact-matrix.json"
PAGE_MATRIX_PATH = REPO_ROOT / "docs" / "dev" / "page-read-model-fact-display-matrix.json"

APPLY_POLICIES = {
    "standing_apply",
    "audit_profile_only",
    "single_use_approval_required",
    "legacy_audit_only",
}

REVERSIBLE_RELATION_PROFILE_PAIRS = {
    "bank_invoice": (
        "workbench_relation_confirm_bank_invoice_cross_page",
        "workbench_relation_withdraw_bank_invoice_cross_page",
    ),
    "bank_turnover": (
        "turnover_relation_confirm_cross_page",
        "turnover_relation_withdraw_cross_page",
    ),
    "bank_oa_invoice": (
        "workbench_relation_confirm_cross_page",
        "workbench_relation_withdraw_cross_page",
    ),
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

    def test_matrix_rejects_every_legacy_write_time_fan_out_signature(self) -> None:
        audit_scope_types_by_operation = _audit_scope_types_by_operation()

        for operation, row in self.rows_by_operation.items():
            self.assertEqual(row["expected_outbox_scope_types"], [], operation)
            self.assertEqual(
                set(row["forbidden_write_time_scope_types"]),
                audit_scope_types_by_operation[operation],
                operation,
            )
            direct_scope_types = set(row["forbidden_write_time_scope_types"])
            retired_direct_scope_types = set(row.get("retired_direct_canonical_scope_types", []))
            derived_read_model_keys = set(row.get("derived_read_model_keys", []))
            self.assertEqual(direct_scope_types & derived_read_model_keys, set(), operation)
            self.assertEqual(retired_direct_scope_types - direct_scope_types, set(), operation)
            self.assertEqual(
                set(row["target_read_model_keys"]),
                (
                    (direct_scope_types - retired_direct_scope_types)
                    | derived_read_model_keys
                )
                & set(APP_STATUS_READ_MODEL_REGISTRY),
                operation,
            )

    def test_slo_targets_match_runtime_write_operation_gates(self) -> None:
        slo = self.matrix["slo"]

        self.assertEqual(slo["write_time_page_fan_out_max"], 0)
        self.assertEqual(slo["access_to_fresh_p95_ms"], write_operation_slo_audit.DEFAULT_TARGET_MS)
        self.assertEqual(
            slo["access_to_fresh_p99_ms"],
            write_operation_slo_audit.effective_p99_target_ms_for(write_operation_slo_audit.DEFAULT_TARGET_MS, None),
        )
        self.assertTrue(all(expectation.forbidden for expectation in write_operation_slo_audit.DEFAULT_OPERATION_EXPECTATIONS))

    def test_scope_and_page_targets_are_current_read_model_contracts(self) -> None:
        valid_read_model_keys = set(APP_STATUS_READ_MODEL_REGISTRY)
        valid_page_keys = set(self.page_rows_by_key)

        for operation, row in self.rows_by_operation.items():
            target_read_model_keys = set(row["target_read_model_keys"])
            derived_read_model_keys = set(row.get("derived_read_model_keys", []))
            direct_canonical_targets = set(row.get("direct_canonical_target_page_keys", []))
            self.assertEqual(target_read_model_keys - valid_read_model_keys, set(), operation)
            self.assertEqual(derived_read_model_keys - valid_read_model_keys, set(), operation)
            self.assertEqual(direct_canonical_targets - set(row["target_page_keys"]), set(), operation)

            for page_key in row["source_page_keys"]:
                self.assertIn(page_key, valid_page_keys, operation)
            for page_key in row["target_page_keys"]:
                self.assertIn(page_key, valid_page_keys, operation)
                page_read_model_keys = set(self.page_rows_by_key[page_key]["read_model_keys"])
                accepted_read_model_keys = target_read_model_keys | set(
                    row.get("legacy_page_proxy_read_model_keys", [])
                )
                if page_key not in direct_canonical_targets:
                    self.assertTrue(
                        page_read_model_keys & accepted_read_model_keys,
                        f"{operation}: {page_key} has no declared impacted read model",
                    )

    def test_pairing_operations_use_the_canonical_relation_fact_sources(self) -> None:
        for operation, row in self.rows_by_operation.items():
            relation_sources = set(row["pairing_relation_fact_sources"])
            if not relation_sources:
                continue
            self.assertEqual(
                relation_sources,
                {"app.workbench_pair_relations", "read_model.workbench_relation_rows"},
                operation,
            )
            self.assertIn("workbench_relation", row["target_read_model_keys"], operation)

    def test_reversible_relation_registry_has_exactly_three_safe_profile_pairs(self) -> None:
        pairs = list(self.matrix["reversible_relation_profile_pairs"])
        pairs_by_shape = {str(pair["shape"]): pair for pair in pairs}
        consumer_probe_paths = dict(self.matrix["reversible_relation_consumer_probe_paths"])
        consumer_business_roots = dict(self.matrix["reversible_relation_consumer_business_roots"])

        self.assertEqual(len(pairs), 3)
        self.assertEqual(set(pairs_by_shape), set(REVERSIBLE_RELATION_PROFILE_PAIRS))
        for shape, expected_profiles in REVERSIBLE_RELATION_PROFILE_PAIRS.items():
            pair = pairs_by_shape[shape]
            self.assertEqual(
                pair["mutation_contract"],
                "turnover_closure" if shape == "bank_turnover" else "workbench_relation",
            )
            profiles = (str(pair["confirm_profile"]), str(pair["withdraw_profile"]))
            self.assertEqual(profiles, expected_profiles, shape)

            confirm_row = self.rows_by_operation[profiles[0]]
            withdraw_row = self.rows_by_operation[profiles[1]]
            affected_consumers = set(pair["affected_consumer_page_keys"])
            non_consumers = set(pair["non_consumer_isolation_page_keys"])
            self.assertEqual(affected_consumers, set(confirm_row["target_page_keys"]), shape)
            self.assertEqual(affected_consumers, set(withdraw_row["target_page_keys"]), shape)
            self.assertTrue(non_consumers, shape)
            self.assertEqual(affected_consumers & non_consumers, set(), shape)
            self.assertEqual(non_consumers - set(self.page_rows_by_key), set(), shape)

            for row in (confirm_row, withdraw_row):
                self.assertEqual(
                    set(row["pairing_relation_fact_sources"]),
                    {"app.workbench_pair_relations", "read_model.workbench_relation_rows"},
                    row["operation"],
                )

            self.assertEqual(
                pair["safety_contract"],
                {
                    "fixture_ownership": "test_owned",
                    "bounded_row_ids": True,
                    "approval_required": True,
                    "checkpoints": ["confirm", "withdraw"],
                    "cleanup": "withdraw",
                    "unique_idempotency_key_per_mutation": True,
                    "discovery_candidate_policy": "read_only_context_only",
                },
                shape,
            )
        registered_pages = {
            str(page_key)
            for pair in pairs
            for key in ("affected_consumer_page_keys", "non_consumer_isolation_page_keys")
            for page_key in pair[key]
        }
        self.assertEqual(set(consumer_probe_paths), registered_pages)
        self.assertTrue(all(str(path).startswith("/api/") for path in consumer_probe_paths.values()))
        self.assertEqual(set(consumer_business_roots), registered_pages)
        self.assertTrue(all(consumer_business_roots[page_key] for page_key in registered_pages))
        runtime_consumers = write_operation_e2e_smoke.REVERSIBLE_RELATION_CONSUMER_CONTRACTS
        self.assertEqual(
            consumer_probe_paths,
            {page_key: contract["path"] for page_key, contract in runtime_consumers.items()},
        )
        self.assertEqual(
            consumer_business_roots,
            {page_key: list(contract["business_roots"]) for page_key, contract in runtime_consumers.items()},
        )
        runtime_shapes = write_operation_e2e_smoke.REVERSIBLE_RELATION_SHAPE_CONTRACTS
        for shape, pair in pairs_by_shape.items():
            runtime_pair = runtime_shapes[shape]
            for key in (
                "mutation_contract",
                "confirm_profile",
                "withdraw_profile",
                "affected_consumer_page_keys",
                "non_consumer_isolation_page_keys",
            ):
                self.assertEqual(
                    list(pair[key]) if isinstance(pair[key], list) else pair[key],
                    list(runtime_pair[key]) if isinstance(runtime_pair[key], tuple) else runtime_pair[key],
                )
        retired_asymmetric_profiles = {
            "workbench_relation_confirm_bank_turnover_cross_page",
            "workbench_relation_withdraw_bank_turnover_cross_page",
        }
        self.assertEqual(retired_asymmetric_profiles & set(self.rows_by_operation), set())
        self.assertEqual(retired_asymmetric_profiles & set(_audit_scope_types_by_operation()), set())

    def test_full_bank_oa_invoice_pair_declares_oa_access_time_consumer_without_write_fan_out(self) -> None:
        for operation in REVERSIBLE_RELATION_PROFILE_PAIRS["bank_oa_invoice"]:
            row = self.rows_by_operation[operation]
            self.assertEqual(row["expected_outbox_scope_types"], [], operation)
            self.assertNotIn("oa_pending_payment", row["target_read_model_keys"], operation)
            self.assertIn("oa-pending-payments", row["target_page_keys"], operation)
            self.assertIn("oa-pending-payments", row["direct_canonical_target_page_keys"], operation)

    def test_relation_profiles_keep_consumer_coverage_without_legacy_facade_fan_out_helpers(self) -> None:
        for pair in self.matrix["reversible_relation_profile_pairs"]:
            for operation in (pair["confirm_profile"], pair["withdraw_profile"]):
                row = self.rows_by_operation[operation]
                self.assertEqual(row["expected_outbox_scope_types"], [], operation)
                self.assertTrue(row["target_read_model_keys"], operation)
                self.assertTrue(row["target_page_keys"], operation)

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
