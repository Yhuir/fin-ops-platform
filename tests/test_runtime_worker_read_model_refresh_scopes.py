import unittest

from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerImportSupport


class StateStoreRecorder:
    def __init__(self) -> None:
        self.saved_payloads: list[dict[str, object]] = []

    def save_import_delta(self, payload: dict[str, object]) -> None:
        self.saved_payloads.append(payload)


class RuntimeWorkerImportSupportTests(unittest.TestCase):
    def _support(self) -> tuple[_RuntimeWorkerImportSupport, StateStoreRecorder]:
        state_store = StateStoreRecorder()
        support = _RuntimeWorkerImportSupport(
            state_store=state_store,
            workbench_source_versions_provider=lambda: {},
        )
        return support, state_store

    def test_import_delta_persistence_is_canonical_only(self) -> None:
        support, state_store = self._support()
        payload = {"imports": {"batches": {"batch-1": {}}}, "file_imports": {"sessions": {}}}

        support.persist_confirmed_import_delta(import_state_payload=payload)

        self.assertEqual(state_store.saved_payloads, [payload])
        self.assertFalse(hasattr(support, "_queue_repository"))
        self.assertFalse(hasattr(support, "execute_event"))

    def test_import_delta_rejects_cross_domain_payload(self) -> None:
        support, state_store = self._support()

        with self.assertRaisesRegex(ValueError, "only imports and file_imports"):
            support.persist_confirmed_import_delta(
                import_state_payload={
                    "imports": {},
                    "file_imports": {},
                    "tax_certified_imports": {},
                }
            )

        self.assertEqual(state_store.saved_payloads, [])


if __name__ == "__main__":
    unittest.main()
