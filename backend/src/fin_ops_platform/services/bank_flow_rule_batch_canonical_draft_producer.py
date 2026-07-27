from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE


BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE = "bank_flow_rule_batch_draft"
BANK_FLOW_RULE_BATCH_DRAFT_REFRESH_EVENT_TYPE = "bank_flow_rule_batch.canonical_draft.refresh"


class BankFlowRuleBatchCanonicalDraftProducer:
    def __init__(self, *, queue_repository_provider: Callable[[], Any]) -> None:
        self._queue_repository_provider = queue_repository_provider

    def enqueue(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return bool(self.enqueue_scope_keys(scope_keys, reason=reason, metadata=metadata))

    def enqueue_scope_keys(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        queue_repository = self._queue_repository_provider()
        enqueue = getattr(queue_repository, "enqueue", None)
        if not callable(enqueue):
            return []
        event_ids: list[str] = []
        for scope_key in self.normalize_scope_keys(scope_keys):
            trigger = self.trigger_for_reason(reason)
            event = enqueue(
                event_type=BANK_FLOW_RULE_BATCH_DRAFT_REFRESH_EVENT_TYPE,
                aggregate_type="bank_flow_rule_batch",
                aggregate_id=scope_key,
                scope_type=BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE,
                scope_key=scope_key,
                dedupe_key=(
                    f"{BANK_FLOW_RULE_BATCH_DRAFT_REFRESH_EVENT_TYPE}:"
                    f"default:{BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE}:{scope_key}"
                ),
                payload={
                    "scope_type": BANK_FLOW_RULE_BATCH_DRAFT_SCOPE_TYPE,
                    "scope_key": scope_key,
                    "reason": str(reason or "unspecified"),
                    "metadata": {
                        "trigger": trigger,
                        **dict(metadata or {}),
                    },
                },
            )
            event_ids.append(str(getattr(event, "event_id", "") or scope_key))
        return event_ids

    @staticmethod
    def normalize_scope_keys(scope_keys: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in list(scope_keys or []):
            scope_key = str(item).strip()
            if scope_key == "all" or SEARCH_MONTH_RE.match(scope_key):
                normalized.append(scope_key)
        return list(dict.fromkeys(normalized or ["all"]))

    @staticmethod
    def trigger_for_reason(reason: str) -> str:
        normalized = str(reason or "").strip().lower()
        if "settings" in normalized or "reset" in normalized:
            return "settings_reset"
        if "repair" in normalized or "replay" in normalized:
            return "repair_replay"
        if "tag" in normalized or "category" in normalized or "rule" in normalized:
            return "effective_tag_rule_change"
        return "bank_fact_change"
