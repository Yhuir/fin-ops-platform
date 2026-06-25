from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_RELATION_MODE
from fin_ops_platform.services.no_oa_managed_rule_policy import NO_OA_MANAGED_LABELS


class NoOaBankBatchWorkbenchDisplayPolicy:
    def __init__(self, *, label_provider: Callable[[str], str]) -> None:
        self._label_provider = label_provider

    def relation_display_payload(self, special_metadata: dict[str, object] | None = None) -> dict[str, str]:
        batch_label = ""
        if isinstance(special_metadata, dict):
            batch_label = str(special_metadata.get("batch_label") or "").strip()
        return {
            "code": NO_OA_BANK_BATCH_RELATION_MODE,
            "label": f"已匹配：{batch_label}" if batch_label else "已匹配：免OA流水",
            "tone": "success",
        }

    def row_tags(
        self,
        *,
        relation: dict[str, object] | None,
        group: dict[str, object],
        special_metadata: dict[str, object] | None,
    ) -> list[str]:
        tags: list[str] = []
        managed_labels = set(NO_OA_MANAGED_LABELS.values())

        def add(tag: object) -> None:
            tag_text = str(tag).strip()
            if tag_text and tag_text not in managed_labels and tag_text not in tags:
                tags.append(tag_text)

        if isinstance(relation, dict):
            for tag in list(relation.get("display_tags") or []):
                add(tag)
        for tag in list(group.get("display_tags") or []):
            add(tag)
        if isinstance(special_metadata, dict):
            for tag in list(special_metadata.get("display_tags") or []):
                add(tag)
            batch_type = str(special_metadata.get("batch_type") or "").strip()
            if batch_type:
                label = str(self._label_provider(batch_type) or "").strip()
                if label and label not in tags:
                    tags.append(label)
            add(special_metadata.get("batch_label"))
        return tags
