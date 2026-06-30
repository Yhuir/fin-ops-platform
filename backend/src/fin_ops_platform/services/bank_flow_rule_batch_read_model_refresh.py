from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_read_model_refresh import BankBatchReadModelRefreshService
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE


BANK_FLOW_RULE_BATCH_REFRESH_EVENT_TYPE = "bank_flow_rule_batch.read_model.refresh"
BANK_FLOW_RULE_BATCH_SCOPE_TYPE = "bank_flow_rule_batch"


class BankFlowRuleBatchReadModelPersistencePort:
    """Persistence boundary for bank_flow_rule_batch public read model snapshots."""

    def __init__(self, state_store: Any) -> None:
        self._state_store = state_store

    def save_public_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        scope_key: str = "all",
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
    ) -> None:
        save_scope = getattr(self._state_store, "save_bank_flow_rule_batches_scope", None)
        if callable(save_scope):
            save_scope(snapshot, scope_key=scope_key)
            return
        save_snapshot = getattr(self._state_store, "save_bank_flow_rule_batches", None)
        if not callable(save_snapshot):
            raise RuntimeError("bank_flow_rule_batch persistence requires save_bank_flow_rule_batches.")
        save_snapshot(snapshot)


class BankFlowRuleBatchReadModelRefreshService(BankBatchReadModelRefreshService):
    """Refresh boundary for the bank_flow_rule_batch read model."""

    def __init__(self, **kwargs: Any) -> None:
        relation_snapshot_service = kwargs.pop("relation_snapshot_service", None)
        if relation_snapshot_service is not None and kwargs.get("pair_relation_service") is None:
            kwargs["pair_relation_service"] = relation_snapshot_service
        if kwargs.get("read_model_persistence") is None:
            kwargs["read_model_persistence"] = BankFlowRuleBatchReadModelPersistencePort(kwargs["state_store"])
        super().__init__(
            **kwargs,
            refresh_event_type=BANK_FLOW_RULE_BATCH_REFRESH_EVENT_TYPE,
            scope_type=BANK_FLOW_RULE_BATCH_SCOPE_TYPE,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
