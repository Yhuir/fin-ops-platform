from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_materialization_service import BankBatchMaterializationService
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService


BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE = "bank_flow_rule_batch_draft"
BANK_FLOW_RULE_BATCH_DRAFT_REFRESH_EVENT_TYPE = "bank_flow_rule_batch.canonical_draft.refresh"


class BankFlowRuleBatchCanonicalDraftPersistencePort:
    """Persistence boundary for canonical bank-flow draft facts."""

    def __init__(self, state_store: Any) -> None:
        self._state_store = state_store

    def save_public_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        scope_key: str = "all",
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
        expected_source_proof: dict[str, object] | None = None,
    ) -> bool | None:
        save_scope = getattr(self._state_store, "save_bank_flow_rule_batches_scope", None)
        if callable(save_scope):
            return save_scope(
                snapshot,
                scope_key=scope_key,
                expected_source_proof=expected_source_proof,
            )
        save_snapshot = getattr(self._state_store, "save_bank_flow_rule_batches", None)
        if not callable(save_snapshot):
            raise RuntimeError("bank_flow_rule_batch canonical persistence requires save_bank_flow_rule_batches.")
        save_snapshot(snapshot)
        return None

    def source_proof(self, scope_key: str) -> dict[str, object] | None:
        loader = getattr(
            self._state_store,
            "bank_flow_rule_batch_canonical_source_proof",
            None,
        )
        return loader(scope_key) if callable(loader) else None


class BankFlowRuleBatchCanonicalDraftOwner(BankBatchMaterializationService):
    """Asynchronously rebuild canonical bank-flow draft facts for one month."""

    def __init__(self, **kwargs: Any) -> None:
        relation_snapshot_service = kwargs.pop("relation_snapshot_service", None)
        if relation_snapshot_service is not None and kwargs.get("pair_relation_service") is None:
            kwargs["pair_relation_service"] = relation_snapshot_service
        if kwargs.get("materialization_persistence") is None:
            kwargs["materialization_persistence"] = BankFlowRuleBatchCanonicalDraftPersistencePort(
                kwargs["state_store"]
            )
        super().__init__(
            **kwargs,
            refresh_event_type=BANK_FLOW_RULE_BATCH_DRAFT_REFRESH_EVENT_TYPE,
            scope_type=BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            application_service_class=BankFlowRuleBatchApplicationService,
        )

    def _publish_source_versions_are_current(
        self,
        *,
        scope_key: str,
        relation_mode: str,
        expected_source_versions: dict[str, object],
    ) -> bool:
        bank_rows = self._application_service.bank_transaction_rows(
            month=scope_key,
            include_categories=False,
        )
        relation_bundle = self._application_service.active_relation_source_bundle_for_bank_rows(
            bank_rows,
            scope_key=scope_key,
        )
        relation_source_versions = relation_bundle.get("source_versions")
        current_source_versions = self._application_service.canonical_draft_source_versions(
            scope_key=scope_key,
            relation_mode=relation_mode,
            relation_source_versions=(
                dict(relation_source_versions)
                if isinstance(relation_source_versions, dict)
                else None
            ),
            source_scope_keys=self._source_scope_keys(scope_key, bank_rows),
        )
        return current_source_versions == expected_source_versions

    def _source_proof_before_build(
        self,
        *,
        scope_key: str,
    ) -> dict[str, object]:
        source_proof = getattr(self._materialization_persistence, "source_proof", None)
        if callable(source_proof):
            proof = source_proof(scope_key)
            if isinstance(proof, dict):
                return proof
        return {}

    @staticmethod
    def _source_scope_keys(
        scope_key: str,
        bank_rows: list[dict[str, object]],
    ) -> list[str]:
        if scope_key != "all":
            return [scope_key]
        return sorted(
            {
                str(row.get("txn_date") or row.get("trade_date") or "")[:7]
                for row in bank_rows
                if len(str(row.get("txn_date") or row.get("trade_date") or "")) >= 7
            }
        )
