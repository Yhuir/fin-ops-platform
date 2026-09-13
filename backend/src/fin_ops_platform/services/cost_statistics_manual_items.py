"""Cost-only supplemental targets; no OA, bank or catalogue writes."""
from __future__ import annotations

import re
from typing import Any


def validate_manual_items(value: Any, options: dict[str, Any], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError("人工成本明细必须是数组，最多 200 条。")
    projects = {p["id"]: p for p in options["projects"]}
    tags = {t["code"]: t for t in options["tags"]}
    old = {item["unit_id"]: item for item in previous}
    seen, result = set(), []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"unit_id", "project_id", "expense_content", "cost_tag_code"}:
            raise ValueError("人工成本字段不完整或包含不支持的字段。")
        if any(not isinstance(v, str) for v in item.values()):
            raise ValueError("人工成本字段必须是文本。")
        identity = item["unit_id"]
        if not re.fullmatch(r"manual:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", identity) or identity in seen:
            raise ValueError("人工成本标识无效或重复。")
        seen.add(identity)
        content = item["expense_content"].strip()
        if not content or len(content) > 500:
            raise ValueError("请填写不超过 500 字的成本项。")
        prior = old.get(identity)
        project = projects.get(item["project_id"])
        tag = tags.get(item["cost_tag_code"])
        if project is None and not (prior and prior["project_id"] == item["project_id"]):
            raise ValueError("请选择有效的已有项目。")
        if tag is None and not (prior and prior["cost_tag_code"] == item["cost_tag_code"]):
            raise ValueError("请选择有效的成本标签。")
        result.append({**item, "expense_content": content,
                       "project_name": project["name"] if project else prior["project_name"],
                       "cost_tag_primary_label": tag["primary_label"] if tag else prior["cost_tag_primary_label"],
                       "cost_tag_sub_label": tag["sub_label"] if tag else prior["cost_tag_sub_label"]})
    return result


def allocation_targets(task: dict[str, Any]) -> list[dict[str, Any]]:
    return [*task["units"], *task.get("manual_items", [])]
