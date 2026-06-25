from __future__ import annotations

from typing import Any, Callable


class NoOaBankBatchWorkbenchPayloadDecorator:
    def __init__(self, *, batch_provider: Callable[[str], dict[str, Any]]) -> None:
        self._batch_provider = batch_provider

    def relation_with_batch_metadata(self, relation: dict[str, object]) -> dict[str, object]:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            return relation
        source_batch_id = str(special_metadata.get("source_batch_id") or "").strip()
        if not source_batch_id:
            return relation
        try:
            batch = self._batch_provider(source_batch_id)
        except KeyError:
            return relation
        enriched_relation = dict(relation)
        enriched_metadata = dict(special_metadata)
        for metadata_key, batch_key in (
            ("batch_version", "version"),
            ("batch_type", "batch_type"),
            ("batch_label", "batch_label"),
            ("row_count", "row_count"),
            ("total_amount", "total_amount"),
            ("withdrawable", "can_withdraw"),
        ):
            value = batch.get(batch_key)
            if value not in (None, ""):
                enriched_metadata[metadata_key] = value
        enriched_relation["special_metadata"] = enriched_metadata
        return enriched_relation

    @staticmethod
    def apply_pair_metadata(payload: dict[str, object], relation: dict[str, object]) -> None:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            special_metadata = {}
        payload["special_metadata"] = dict(special_metadata)

        display_tags = [
            str(tag).strip()
            for tag in list(relation.get("display_tags") or special_metadata.get("display_tags") or [])
            if str(tag).strip()
        ]
        batch_label = str(special_metadata.get("batch_label") or "").strip()
        if not display_tags:
            display_tags = ["免OA"]
            if batch_label:
                display_tags.append(batch_label)

        tags = [str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()]
        for tag in display_tags:
            if tag not in tags:
                tags.append(tag)
        payload["tags"] = tags
        payload["display_tags"] = display_tags

        cost_policy = str(special_metadata.get("cost_policy") or "").strip()
        if cost_policy == "exclude_all":
            payload["cost_excluded"] = True
        for fields_key in ("summary_fields", "detail_fields"):
            fields = payload.get(fields_key)
            if isinstance(fields, dict):
                fields["免OA批次"] = batch_label or "免OA流水"
                if cost_policy == "exclude_all":
                    fields["成本统计"] = "不计入"

    @staticmethod
    def apply_available_actions(payload: dict[str, object]) -> None:
        special_metadata = payload.get("special_metadata")
        if not isinstance(special_metadata, dict):
            return
        source_batch_id = str(special_metadata.get("source_batch_id") or "").strip()
        withdrawable = (
            bool(special_metadata.get("withdrawable"))
            if "withdrawable" in special_metadata
            else bool(source_batch_id)
        )
        if not source_batch_id or not withdrawable:
            return
        actions = [str(action).strip() for action in list(payload.get("available_actions") or []) if str(action).strip()]
        if "detail" not in actions:
            actions.insert(0, "detail")
        if "withdraw_no_oa_batch" not in actions:
            actions.append("withdraw_no_oa_batch")
        payload["available_actions"] = actions
