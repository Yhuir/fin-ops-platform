from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.tools import p2p3_closure_summary


class P2P3ClosureSummaryTests(unittest.TestCase):
    def test_build_summary_parses_pages_items_and_gates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            plan = Path(temp_dir) / "P2P3.md"
            plan.write_text(
                """
# P2/P3 Closure Plan

## 聚合 Closure Items

| ID | Priority | Classification | 覆盖页面 | Gap | Closure evidence |
| --- | --- | --- | --- | --- | --- |
| P2P3-001 | P2-A | production-required | 1-2 | runtime gate | runtime closure |
| P2P3-015 | P2-A | auto-fixable | 1 | toolbar action | vitest |

## Final Gated Smoke Matrix

| Gate | Covers | Command / evidence | Pass criteria | Failure handling |
| --- | --- | --- | --- | --- |
| Runtime closure gate | P2P3-001, P2P3-002 | run runtime gate | all checks pass | inspect runtime blocker |
| Manual browser smoke | P2P3-007 | open browser | visual pass | convert UI bug |

## 17 页面覆盖映射

| Phase | Page | Primary Closure IDs |
| --- | --- | --- |
| 1 | 外部往来款管理 | P2P3-001, P2P3-015 |
| 2 | 银行明细 | P2P3-001, P2P3-008 |

## 17 页面当前 P2/P3 状态

状态说明。

| Phase | Page | Current P2/P3 status | Local closure evidence | Remaining gate |
| --- | --- | --- | --- | --- |
| 1 | 外部往来款管理 | fixed-local + evidence-added + manual-only | toolbar fixed | browser smoke |
| 2 | 银行明细 | evidence-added + production-gated | export guard | production SLO |

## Current Status

| ID | Status | Notes |
| --- | --- | --- |
| P2P3-001 | production-gated | runtime proof needs production |
| P2P3-015 | fixed-local | toolbar fixed |
""".strip()
                + "\n",
                encoding="utf-8",
            )

            payload = p2p3_closure_summary.build_summary(plan)

        self.assertEqual(payload["status"], "gated")
        self.assertEqual(payload["summary"]["page_count"], 2)
        self.assertEqual(payload["summary"]["gated_page_count"], 2)
        self.assertEqual(payload["summary"]["smoke_gate_count"], 2)
        self.assertEqual(payload["summary"]["page_status_counts"]["evidence-added"], 2)
        self.assertEqual(payload["summary"]["item_status_counts"], {"fixed-local": 1, "production-gated": 1})
        self.assertEqual(payload["summary"]["item_classification_counts"], {"auto-fixable": 1, "production-required": 1})
        self.assertEqual(payload["pages"][0]["primary_closure_ids"], ["P2P3-001", "P2P3-015"])
        self.assertEqual(payload["pages"][0]["gates"], ["manual-only"])
        self.assertEqual(payload["pages"][0]["external_gate_item_ids"], ["P2P3-001"])
        self.assertEqual(payload["pages"][0]["next_actions"][0]["item_id"], "P2P3-001")
        self.assertEqual(payload["pages"][0]["next_actions"][0]["gate"], "Runtime closure gate")
        self.assertEqual(payload["pages"][1]["gates"], ["production-gated"])
        self.assertEqual(payload["pages"][1]["external_gate_item_ids"], ["P2P3-001"])
        self.assertEqual(payload["items"][0]["priority"], "P2-A")
        self.assertEqual(payload["items"][0]["classification"], "production-required")
        self.assertEqual(payload["items"][0]["covered_pages"], ["1-2"])
        self.assertEqual(payload["items"][0]["gap"], "runtime gate")
        self.assertEqual(payload["items"][0]["closure_evidence"], "runtime closure")
        self.assertTrue(payload["items"][0]["requires_external_evidence"])
        self.assertEqual(payload["items"][0]["next_actions"][0]["gate"], "Runtime closure gate")
        self.assertEqual(payload["items"][0]["next_actions"][0]["command_or_evidence"], "run runtime gate")
        self.assertFalse(payload["items"][1]["requires_external_evidence"])
        self.assertEqual(payload["items"][1]["next_actions"], [])
        self.assertEqual(payload["smoke_gates"][0]["covers"], ["P2P3-001", "P2P3-002"])
        self.assertEqual(payload["next_focus"]["item_id"], "P2P3-001")
        self.assertEqual(payload["next_focus"]["item_status"], "production-gated")
        self.assertEqual(payload["next_focus"]["recommended_gate"]["gate"], "Runtime closure gate")
        self.assertEqual(payload["next_focus"]["affected_page_count"], 2)
        bounded_action = payload["next_focus"]["next_bounded_action"]
        self.assertIn("P2P3-001", bounded_action["goal"])
        self.assertEqual(bounded_action["recommended_command_or_evidence"], "run runtime gate")
        self.assertIn("Do not mark stale read models as fresh.", bounded_action["architecture_constraints"])
        self.assertIn("configuration_missing", " ".join(bounded_action["evidence_to_inspect"]))
        self.assertIn("Do not claim final 17-page closure", bounded_action["stop_condition"])

    def test_current_plan_outputs_all_17_pages_and_items(self) -> None:
        payload = p2p3_closure_summary.build_summary(Path(".planning/P2P3-CLOSURE-PLAN.md"))

        self.assertEqual(payload["tool"], "p2p3_closure_summary")
        self.assertEqual(payload["summary"]["page_count"], 17)
        self.assertGreaterEqual(payload["summary"]["item_count"], 21)
        self.assertEqual([page["phase"] for page in payload["pages"]], list(range(1, 18)))
        for page in payload["pages"]:
            with self.subTest(phase=page["phase"]):
                self.assertTrue(page["primary_closure_ids"])
                self.assertTrue(page["status"])
                self.assertTrue(page["local_closure_evidence"])
                self.assertTrue(page["remaining_gate"])
                if page["gates"]:
                    self.assertTrue(page["external_gate_item_ids"])
                    self.assertTrue(page["next_actions"])
        for item in payload["items"]:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["priority"])
                self.assertTrue(item["classification"])
                self.assertTrue(item["covered_pages"])
                self.assertTrue(item["gap"])
                self.assertTrue(item["closure_evidence"])
                if item["status"] in {"staging-gated", "production-gated", "manual-only"}:
                    self.assertTrue(item["requires_external_evidence"])
                    self.assertTrue(item["next_actions"])
        self.assertEqual(payload["next_focus"]["item_id"], "P2P3-001")
        self.assertEqual(payload["next_focus"]["item_status"], "production-gated")
        self.assertEqual(payload["next_focus"]["item_priority"], "P2-A")
        self.assertGreater(payload["next_focus"]["affected_page_count"], 0)
        self.assertTrue(payload["next_focus"]["recommended_gate"]["gate"])
        self.assertTrue(payload["next_focus"]["next_bounded_action"]["recommended_command_or_evidence"])
        self.assertIn("PostgreSQL durable queue", " ".join(payload["next_focus"]["next_bounded_action"]["architecture_constraints"]))

    def test_cli_returns_input_error_for_missing_plan(self) -> None:
        stdout = StringIO()
        exit_code = p2p3_closure_summary.main(["--plan", "/tmp/not-a-p2p3-plan.md"], stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "input_error")
        self.assertEqual(payload["tool"], "p2p3_closure_summary")
        self.assertEqual(payload["error"], "plan_not_found")


if __name__ == "__main__":
    unittest.main()
