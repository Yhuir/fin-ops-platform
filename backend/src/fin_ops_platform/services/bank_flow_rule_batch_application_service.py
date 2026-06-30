from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_application_service import BankBatchApplicationService, BankBatchPersistenceError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE


class BankFlowRuleBatchApplicationService(BankBatchApplicationService):
    """Application boundary for 流水规则批量处理."""

    def persist_mutation(self, *, changed_case_ids: list[str], changed_scope_keys: list[str]) -> None:
        if self._state_store is None:
            return
        try:
            self._search_cache_clearer()
            save_mutation = getattr(self._state_store, "save_bank_flow_rule_batch_mutation", None)
            if not callable(save_mutation):
                raise RuntimeError("bank_flow_rule_batch mutation persistence requires save_bank_flow_rule_batch_mutation.")
            save_mutation(
                pair_relation_snapshot=self._pair_relation_snapshot_port.snapshot_case_ids(changed_case_ids)
                if changed_case_ids
                else self._pair_relation_snapshot_port.snapshot(),
                bank_flow_rule_batch_snapshot=self._bank_batch_public_snapshot(),
                workbench_read_model_snapshot=self._workbench_read_model_service.snapshot(),
                changed_case_ids=changed_case_ids,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            raise BankBatchPersistenceError(str(exc)) from exc

    def update_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        result = self._app_settings_service.update_no_oa_bank_batch_tag_selection(
            payload,
            actor_id=actor_id,
        )
        self._sync_bank_flow_rule_relation_requirements(result, actor_id=actor_id)
        self._sync_turnover_rule_relation_requirements(result, actor_id=actor_id)
        self.after_mutation(
            ["all"],
            changed_case_ids=[],
            persist=False,
            action_name="bank_flow_rule_batch_tag_rules_changed",
        )
        self.enqueue_background_refresh(
            ["all"],
            reason="bank_flow_rule_batch_tag_rules_changed",
            metadata=self._read_model_refresh_metadata_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE),
        )
        return result
