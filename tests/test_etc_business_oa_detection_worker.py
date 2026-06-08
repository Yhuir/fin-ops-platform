from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.runtime_worker_handlers import _etc_oa_detection_adapter, handle_etc_business_oa_detection_event


class EtcBusinessOADetectionWorkerTests(unittest.TestCase):
    def test_worker_oa_detection_adapter_falls_back_to_live_oa_when_projection_is_empty(self) -> None:
        class ProjectionRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                return []

        class StateStore:
            def __init__(self, data_dir: Path, repository: ProjectionRepository) -> None:
                self.data_dir = data_dir
                self.oa_projection_repository = repository

        class LiveOAAdapter:
            name = "live_oa"

            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                return [{"oa_row_id": "oa-pay-live-worker-001"}]

        with TemporaryDirectory() as temp_dir:
            projection_repository = ProjectionRepository()
            live_adapter = LiveOAAdapter()
            with (
                patch(
                    "fin_ops_platform.services.runtime_worker_handlers.load_mongo_oa_settings",
                    return_value=object(),
                ),
                patch(
                    "fin_ops_platform.services.runtime_worker_handlers.MongoOAAdapter",
                    return_value=live_adapter,
                ),
            ):
                adapter = _etc_oa_detection_adapter(StateStore(Path(temp_dir), projection_repository))

            rows = adapter.list_etc_oa_detection_candidates(
                business_batch_id="etc_business_batch_0004",
                external_etc_batch_id="etc_20260520_001",
                created_from=datetime(2026, 5, 1),
                created_to=datetime(2026, 6, 8),
            )

        self.assertEqual(rows[0]["oa_row_id"], "oa-pay-live-worker-001")
        self.assertEqual(projection_repository.calls[0]["business_batch_id"], "etc_business_batch_0004")
        self.assertEqual(live_adapter.calls[0]["external_etc_batch_id"], "etc_20260520_001")

    def test_missing_result_does_not_reenqueue_detection_event(self) -> None:
        class Service:
            def __init__(self) -> None:
                self.enqueue_calls: list[object] = []
                self.sync_calls: list[tuple[object, str]] = []

            def refresh_oa_detection(self, business_batch_id: str, *, expected_version: int | None) -> object:
                return SimpleNamespace(
                    business_batch_id=business_batch_id,
                    status="oa_submission_detecting",
                    version=(expected_version or 0) + 1,
                )

            def enqueue_oa_detection(self, batch: object) -> None:
                self.enqueue_calls.append(batch)

            def sync_invoices_after_oa_detection(self, batch: object, *, reason: str) -> None:
                self.sync_calls.append((batch, reason))

        service = Service()

        result = handle_etc_business_oa_detection_event(
            service,
            SimpleNamespace(
                aggregate_id="etc_business_batch_0001",
                payload={"business_batch_id": "etc_business_batch_0001", "expected_version": 7},
            ),
        )

        self.assertEqual(result["status"], "oa_submission_detecting")
        self.assertEqual(service.enqueue_calls, [])
        self.assertEqual(service.sync_calls, [])

    def test_submitted_result_syncs_invoices_after_detection(self) -> None:
        class Service:
            def __init__(self) -> None:
                self.enqueue_calls: list[object] = []
                self.sync_calls: list[tuple[object, str]] = []

            def refresh_oa_detection(self, business_batch_id: str, *, expected_version: int | None) -> object:
                return SimpleNamespace(
                    business_batch_id=business_batch_id,
                    status="oa_submitted",
                    version=(expected_version or 0) + 1,
                )

            def enqueue_oa_detection(self, batch: object) -> None:
                self.enqueue_calls.append(batch)

            def sync_invoices_after_oa_detection(self, batch: object, *, reason: str) -> None:
                self.sync_calls.append((batch, reason))

        service = Service()

        result = handle_etc_business_oa_detection_event(
            service,
            SimpleNamespace(
                aggregate_id="etc_business_batch_0001",
                payload={"business_batch_id": "etc_business_batch_0001", "expected_version": 7},
            ),
        )

        self.assertEqual(result["status"], "oa_submitted")
        self.assertEqual(service.enqueue_calls, [])
        self.assertEqual(service.sync_calls[0][1], "etc_business_oa_status_detected_async")


if __name__ == "__main__":
    unittest.main()
