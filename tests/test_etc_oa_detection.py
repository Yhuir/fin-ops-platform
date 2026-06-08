import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from fin_ops_platform.services.etc_oa_detection import (
    EtcOADetectionContext,
    EtcOADetectionService,
    FallbackEtcOADetectionCandidateAdapter,
)


def detection_context() -> EtcOADetectionContext:
    draft_created_at = datetime(2026, 5, 19, 9, 0, 0)
    return EtcOADetectionContext(
        business_batch_id="etc_business_batch_0001",
        external_etc_batch_id="etc_20260519_001",
        amount=Decimal("53.84"),
        invoice_count=2,
        owner_user_id="user-001",
        owner_org_id="org-001",
        oa_draft_created_at=draft_created_at,
        oa_detection_deadline_at=draft_created_at + timedelta(minutes=30),
    )


def candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "oa_row_id": "oa-pay-001",
        "form_id": "2",
        "amount": "53.84",
        "invoice_count": 2,
        "applicant_user_id": "user-001",
        "applicant": "张三",
        "owner_org_id": "org-001",
        "organization": "财务部",
        "created_at": datetime(2026, 5, 19, 9, 5, 0),
        "process_status": "1",
        "reason": "ETC批量提交\nbusiness_batch_id=etc_business_batch_0001\netc_batch_id=etc_20260519_001",
    }
    payload.update(overrides)
    return payload


class EtcOADetectionServiceTests(unittest.TestCase):
    def test_unique_in_progress_candidate_is_detected(self) -> None:
        result = EtcOADetectionService().detect(detection_context(), [candidate()])

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.reason, "unique_candidate_detected")
        self.assertEqual(result.oa_row_id, "oa-pay-001")
        self.assertEqual(result.process_status, "in_progress")
        self.assertEqual(result.candidates[0]["matchedMarker"], "business_batch_id")

    def test_adapter_canonical_process_status_candidate_is_detected(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(process_status="in_progress")],
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.process_status, "in_progress")

    def test_multiple_valid_candidates_are_conflict(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [
                candidate(oa_row_id="oa-pay-001"),
                candidate(oa_row_id="oa-pay-002"),
            ],
        )

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.reason, "multiple_candidates")
        self.assertEqual([item["oaRowId"] for item in result.candidates], ["oa-pay-001", "oa-pay-002"])

    def test_single_valid_candidate_wins_over_invalid_marker_match(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [
                candidate(oa_row_id="oa-pay-invalid", amount="53.85"),
                candidate(oa_row_id="oa-pay-valid"),
            ],
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.oa_row_id, "oa-pay-valid")
        self.assertEqual([item["oaRowId"] for item in result.candidates], ["oa-pay-valid"])

    def test_marker_missing_is_reason_not_business_status(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(reason="ETC批量提交\n未写入稳定业务标记")],
        )

        self.assertEqual(result.status, "missing")
        self.assertEqual(result.reason, "oa_marker_missing")
        self.assertEqual(result.candidates[0]["oaRowId"], "oa-pay-001")

    def test_marker_missing_after_deadline_remains_missing(self) -> None:
        context = detection_context()
        assert context.oa_detection_deadline_at is not None

        result = EtcOADetectionService().detect(
            context,
            [candidate(reason="ETC批量提交\n未写入稳定业务标记")],
            now=context.oa_detection_deadline_at + timedelta(days=3),
        )

        self.assertEqual(result.status, "missing")
        self.assertEqual(result.reason, "oa_marker_missing")
        self.assertEqual(result.candidates[0]["oaRowId"], "oa-pay-001")

    def test_valid_candidate_created_after_deadline_is_detected(self) -> None:
        context = detection_context()
        assert context.oa_detection_deadline_at is not None

        result = EtcOADetectionService().detect(
            context,
            [
                candidate(
                    created_at=context.oa_detection_deadline_at + timedelta(days=3),
                    reason=(
                        "ETC批量提交\n"
                        "business_batch_id=etc_business_batch_0001\n"
                        "etc_batch_id=etc_20260519_001"
                    ),
                )
            ],
            now=context.oa_detection_deadline_at + timedelta(days=3, minutes=5),
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.reason, "unique_candidate_detected")
        self.assertEqual(result.oa_row_id, "oa-pay-001")

    def test_valid_marker_candidate_created_before_local_detection_window_is_detected(self) -> None:
        context = detection_context()
        assert context.oa_draft_created_at is not None

        result = EtcOADetectionService().detect(
            context,
            [candidate(created_at=context.oa_draft_created_at - timedelta(days=10))],
            now=context.oa_detection_deadline_at + timedelta(days=1) if context.oa_detection_deadline_at else None,
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.reason, "unique_candidate_detected")
        self.assertEqual(result.oa_row_id, "oa-pay-001")

    def test_amount_mismatch_is_conflict(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(amount="53.85")],
        )

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.reason, "amount_mismatch")
        self.assertEqual(result.candidates[0]["amount"], "53.85")

    def test_missing_candidate_invoice_count_does_not_reject_stable_marker(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(invoice_count="", detail_fields={"表单ID": "2", "流程状态": "进行中"})],
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.reason, "unique_candidate_detected")
        self.assertIsNone(result.candidates[0]["invoiceCount"])

    def test_explicit_candidate_invoice_count_mismatch_is_conflict(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(invoice_count=3)],
        )

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.reason, "invoice_count_mismatch")
        self.assertEqual(result.candidates[0]["invoiceCount"], 3)

    def test_missing_candidate_owner_identity_does_not_reject_stable_marker(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [
                candidate(
                    applicant="杨丽萍",
                    applicant_user_id="",
                    owner_org_id="",
                    organization="",
                )
            ],
        )

        self.assertEqual(result.status, "detected")
        self.assertEqual(result.reason, "unique_candidate_detected")

    def test_explicit_candidate_owner_identity_mismatch_is_conflict(self) -> None:
        result = EtcOADetectionService().detect(
            detection_context(),
            [candidate(applicant_user_id="other-user", owner_org_id="other-org")],
        )

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.reason, "organization_mismatch")

    def test_unavailable_exception_becomes_unavailable_result(self) -> None:
        def failing_query(_context: EtcOADetectionContext) -> list[dict[str, object]]:
            raise TimeoutError("mongo timeout")

        result = EtcOADetectionService().detect_with_adapter(detection_context(), failing_query)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason, "oa_query_unavailable")
        self.assertIn("mongo timeout", result.error or "")

    def test_fallback_adapter_uses_live_adapter_when_projection_has_no_candidates(self) -> None:
        class EmptyProjectionAdapter:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                return []

        class LiveOAAdapter:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                return [candidate(oa_row_id="oa-pay-live-001")]

        projection = EmptyProjectionAdapter()
        live = LiveOAAdapter()
        adapter = FallbackEtcOADetectionCandidateAdapter([projection, live])

        rows = adapter.list_etc_oa_detection_candidates(
            business_batch_id="etc_business_batch_0001",
            external_etc_batch_id="etc_20260519_001",
            created_from=datetime(2026, 5, 1),
            created_to=datetime(2026, 5, 31),
        )

        self.assertEqual(rows[0]["oa_row_id"], "oa-pay-live-001")
        self.assertEqual(projection.calls[0]["business_batch_id"], "etc_business_batch_0001")
        self.assertEqual(live.calls[0]["external_etc_batch_id"], "etc_20260519_001")


if __name__ == "__main__":
    unittest.main()
