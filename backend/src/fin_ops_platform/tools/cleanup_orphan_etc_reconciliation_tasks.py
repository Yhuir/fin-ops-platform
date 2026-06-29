from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.services.etc_reconciliation_models import EtcReconciliationTaskStatus
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    etc_reconciliation_task_service,
    etc_service,
)


ACTOR = "system_orphan_etc_task_cleanup"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tombstone orphan ETC reconciliation tasks after ETC business batch deletion.")
    parser.add_argument("--task-id", action="append", required=True, help="ETC reconciliation task id to inspect. Can be repeated.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Optional local state directory for non-Postgres runs.")
    parser.add_argument("--execute", action="store_true", help="Persist tombstones. Without this flag the command is a dry run.")
    parser.add_argument("--reason", default="cleanup_orphan_etc_reconciliation_task", help="Audit reason for execute mode.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_tool_runtime_application(args.data_dir)
    task_ids = _normalized_task_ids(args.task_id)
    if args.execute:
        results = [_execute_task_cleanup(app, task_id, reason=str(args.reason or "")) for task_id in task_ids]
        mode = "execute"
    else:
        results = [_plan_task_cleanup(app, task_id) for task_id in task_ids]
        mode = "dry-run"
    status = "ok" if all(result.get("status") in {"ready", "deleted", "already_deleted"} for result in results) else "attention"
    print(json.dumps({"status": status, "mode": mode, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "ok" else 1


def _normalized_task_ids(raw_task_ids: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_task_id in raw_task_ids:
        task_id = str(raw_task_id or "").strip()
        if not task_id or task_id in seen:
            continue
        normalized.append(task_id)
        seen.add(task_id)
    if not normalized:
        raise ValueError("at least one --task-id is required")
    return normalized


def _plan_task_cleanup(app: Any, task_id: str) -> dict[str, object]:
    task_payload = _raw_task_payload(app, task_id)
    if task_payload is None:
        return {"task_id": task_id, "status": "missing"}
    task_status = _task_status(task_payload)
    active_business_batch_ids = _active_business_batch_ids(app, task_id)
    if task_status == EtcReconciliationTaskStatus.DELETED.value:
        return {
            "task_id": task_id,
            "status": "already_deleted",
            "task_status": task_status,
            "active_business_batch_ids": active_business_batch_ids,
        }
    if active_business_batch_ids:
        return {
            "task_id": task_id,
            "status": "blocked_active_business_batch",
            "task_status": task_status,
            "active_business_batch_ids": active_business_batch_ids,
        }
    return {
        "task_id": task_id,
        "status": "ready",
        "task_status": task_status,
        "version": _task_version(task_payload),
        "active_business_batch_ids": active_business_batch_ids,
    }


def _execute_task_cleanup(app: Any, task_id: str, *, reason: str) -> dict[str, object]:
    plan = _plan_task_cleanup(app, task_id)
    if plan.get("status") != "ready":
        return plan
    service = etc_reconciliation_task_service(app)
    task = service.get_task(task_id)
    result = service.delete_task(
        task_id=task_id,
        expected_version=int(getattr(task, "version", 0) or 0),
        actor=ACTOR,
        import_cleanup_confirmed=True,
    )
    return {
        "task_id": task_id,
        "status": "deleted",
        "task_status": plan.get("task_status"),
        "version": plan.get("version"),
        "reason": str(reason or "").strip() or None,
        "result": result,
    }


def _raw_task_payload(app: Any, task_id: str) -> dict[str, Any] | None:
    service = etc_reconciliation_task_service(app)
    snapshot = service.snapshot()
    tasks = snapshot.get("tasks") if isinstance(snapshot, dict) else None
    if not isinstance(tasks, dict):
        return None
    payload = tasks.get(task_id)
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    return {
        "task_id": str(getattr(payload, "task_id", task_id) or task_id),
        "status": str(getattr(payload, "status", "") or ""),
        "version": int(getattr(payload, "version", 0) or 0),
    }


def _task_status(task_payload: dict[str, Any]) -> str:
    status = task_payload.get("status")
    if isinstance(status, EtcReconciliationTaskStatus):
        return status.value
    return str(status or "").strip() or EtcReconciliationTaskStatus.DRAFT.value


def _task_version(task_payload: dict[str, Any]) -> int:
    try:
        return int(task_payload.get("version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _active_business_batch_ids(app: Any, task_id: str) -> list[str]:
    service = etc_service(app)
    batches = service.list_business_batches(task_id=task_id)
    return [
        str(getattr(batch, "business_batch_id", "") or "").strip()
        for batch in batches
        if str(getattr(batch, "business_batch_id", "") or "").strip()
    ]


if __name__ == "__main__":
    raise SystemExit(main())
