from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_batch_application_service import (
    SEARCH_MONTH_RE,
    BankBatchApplicationService,
    BankBatchPersistenceError,
)
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE


BANK_FLOW_RULE_BATCH_ONLINE_MUTATION_ACTIONS = frozenset(
    {
        "bank_flow_rule_batch_submit",
        "bank_flow_rule_batch_withdraw",
        "bank_flow_rule_batch_reset_submitted",
    }
)


class BankFlowRuleBatchApplicationService(BankBatchApplicationService):
    """Application boundary for 流水规则批量处理."""

    def _refresh_bank_flow_rule_batch_runtime_snapshot(self) -> None:
        self.refresh_batches(
            apply_relation_repairs=False,
            scope_key="all",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

    def _refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(self, batch_id: str) -> None:
        try:
            self._bank_batch_service.get_batch(batch_id)
            return
        except KeyError:
            if self._restore_bank_flow_rule_batch_runtime_snapshot(batch_id):
                return
            self._refresh_bank_flow_rule_batch_runtime_snapshot()

    def _restore_bank_flow_rule_batch_runtime_snapshot(self, batch_id: str) -> bool:
        state_store = getattr(self, "_state_store", None)
        load_snapshot = getattr(state_store, "load_bank_flow_rule_batches", None)
        replace_snapshot = getattr(self._bank_batch_service, "replace_snapshot", None)
        if not callable(load_snapshot) or not callable(replace_snapshot):
            return False
        snapshot = load_snapshot()
        if not isinstance(snapshot, dict):
            return False
        replace_snapshot(snapshot)
        try:
            self._bank_batch_service.get_batch(batch_id)
            return True
        except KeyError:
            return False

    def _prepare_batch_for_submit(self, batch_id: str, *, relation_mode: str) -> None:
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
            return
        super()._prepare_batch_for_submit(batch_id, relation_mode=relation_mode)

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
        relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
        persist: bool = True,
    ) -> dict[str, object]:
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            return super().submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
                relation_mode=relation_mode,
                persist=persist,
            )
        previous_batch_snapshot = self._bank_batch_service.snapshot()
        try:
            self._prepare_batch_for_submit(batch_id, relation_mode=relation_mode)
            before_batch = self._bank_batch_service.get_batch(batch_id)
            already_submitted = str(before_batch.get("status") or "") == "submitted"
            batch = self._bank_batch_service.submit_batch(
                batch_id,
                actor=actor,
                expected_version=expected_version,
                note=note,
            )
            if not already_submitted:
                self._confirm_relation_for_batch(batch, actor=actor, note=note, relation_mode=relation_mode)
            return self._mutation_result(
                batch,
                status="submitted",
                persist=persist,
                read_model_key=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )
        except Exception:
            self._restore_batch_service_snapshot(self._bank_batch_service, previous_batch_snapshot)
            raise

    def detail_payload(self, batch_id: str) -> dict[str, object]:
        self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
        return super().detail_payload(batch_id)

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        self._refresh_bank_flow_rule_batch_runtime_snapshot_if_missing(batch_id)
        return super().withdraw_batch(
            batch_id,
            actor=actor,
            expected_version=expected_version,
            reason=reason,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

    def reset_submitted_bank_flow_rule_batches(
        self,
        *,
        actor: str,
        reason: str | None,
    ) -> dict[str, object]:
        return super().reset_submitted_bank_flow_rule_batches(actor=actor, reason=reason)

    def after_mutation(
        self,
        affected_months: list[str],
        *,
        changed_case_ids: list[str],
        persist: bool,
        action_name: str | None = None,
    ) -> bool:
        normalized_action_name = str(action_name or "").strip()
        if not normalized_action_name.startswith("bank_flow_rule_batch"):
            return super().after_mutation(
                affected_months,
                changed_case_ids=changed_case_ids,
                persist=persist,
                action_name=action_name,
            )
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if SEARCH_MONTH_RE.match(str(month).strip())
        ]
        if normalized_action_name not in BANK_FLOW_RULE_BATCH_ONLINE_MUTATION_ACTIONS:
            self._execute_derived_data_lifecycle_event(
                "bank_flow_rule_batch_changed",
                months=normalized_months,
                metadata={
                    "source": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    **({"action_name": normalized_action_name} if normalized_action_name else {}),
                },
                schedule_cost_warmup=False,
            )
        if persist:
            self.persist_mutation(
                changed_case_ids=changed_case_ids,
                changed_scope_keys=["all", *normalized_months],
            )
        return bool(normalized_months)

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
                changed_case_ids=changed_case_ids,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            raise BankBatchPersistenceError(str(exc)) from exc

    def tag_selection_payload(self) -> dict[str, Any]:
        return self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload()

    def update_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        result = self._app_settings_service.update_bank_flow_rule_batch_tag_rules(
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
