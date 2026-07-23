import unittest
from types import SimpleNamespace

from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerImportSupport


class StateStoreRecorder:
    def __init__(self) -> None:
        self.saved_payloads: list[dict[str, object]] = []

    def save_import_delta(self, payload: dict[str, object]) -> None:
        self.saved_payloads.append(payload)


class RuntimeWorkerImportSupportTests(unittest.TestCase):
    def _support(self) -> tuple[_RuntimeWorkerImportSupport, StateStoreRecorder, list[str]]:
        state_store = StateStoreRecorder()
        cache_calls: list[str] = []
        support = _RuntimeWorkerImportSupport(
            state_store=state_store,
            search_service=SimpleNamespace(clear_cache=lambda: cache_calls.append("clear")),
            workbench_source_versions_provider=lambda: {},
        )
        return support, state_store, cache_calls

    def test_import_delta_persistence_is_canonical_only(self) -> None:
        support, state_store, cache_calls = self._support()
        payload = {"imports": {"batches": {"batch-1": {}}}, "file_imports": {"sessions": {}}}

        support.persist_confirmed_import_delta(import_state_payload=payload)

        self.assertEqual(state_store.saved_payloads, [payload])
        self.assertEqual(cache_calls, ["clear"])
        self.assertFalse(hasattr(support, "_queue_repository"))
        self.assertFalse(hasattr(support, "execute_event"))

    def test_import_delta_rejects_cross_domain_payload(self) -> None:
        support, state_store, _cache_calls = self._support()

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
