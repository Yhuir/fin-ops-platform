from types import SimpleNamespace
import unittest

from fin_ops_platform.services.runtime_worker_handlers import handle_etc_business_oa_detection_event


class EtcBusinessOADetectionWorkerTests(unittest.TestCase):
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
