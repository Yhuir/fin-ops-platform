from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from fin_ops_platform.tools import validate_workbench_generation_convergence


class ValidateWorkbenchGenerationConvergenceTests(unittest.TestCase):
    def test_reads_combined_initial_then_pins_groups_to_its_version(self) -> None:
        requested_urls: list[str] = []
        payloads = iter(
            (
                {
                    "read_model_status": "fresh",
                    "read_model_version": "generation-17",
                    "summary": {
                        "oa_count": 3,
                        "bank_count": 4,
                        "invoice_count": 5,
                        "paired_count": 2,
                        "unpaired_count": 10,
                    },
                },
                {
                    "read_model_status": "fresh",
                    "read_model_version": "generation-17",
                    "total": 2,
                    "row_counts": {"oa": 1, "bank": 1, "invoice": 0},
                },
            )
        )

        def fake_get_json(url: str, *, timeout_seconds: float) -> dict[str, object]:
            requested_urls.append(url)
            self.assertEqual(timeout_seconds, 2.0)
            return next(payloads)

        args = argparse.Namespace(
            base_url="https://example.test/",
            month="all",
            zone="paired",
            page_size=50,
            iterations=1,
            delay_seconds=0.0,
            timeout_seconds=2.0,
        )
        output = io.StringIO()

        with (
            patch.object(validate_workbench_generation_convergence, "_get_json", side_effect=fake_get_json),
            redirect_stdout(output),
        ):
            status = validate_workbench_generation_convergence.validate(args)

        self.assertEqual(status, 0)
        self.assertEqual(requested_urls[0], "https://example.test/api/workbench?month=all")
        self.assertIn("/api/workbench/groups?", requested_urls[1])
        self.assertIn("expected_read_model_version=generation-17", requested_urls[1])
        self.assertNotIn("/api/workbench/summary", "\n".join(requested_urls))
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["observations"][0]["version"], "generation-17")
        self.assertEqual(report["observations"][0]["initial_status"], "fresh")


if __name__ == "__main__":
    unittest.main()
