from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence, TextIO

from .cli_reports import input_file_error_report, write_json_report

DEFAULT_PLAN_PATH = Path(".planning/P2P3-CLOSURE-PLAN.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a machine-readable P2/P3 closure summary from .planning/P2P3-CLOSURE-PLAN.md.",
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH, help="Path to P2/P3 closure markdown plan.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--json", action="store_true", help="Accepted for consistency; output is always JSON.")
    return parser


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells)


def _table_after_heading(lines: Sequence[str], heading: str) -> list[dict[str, str]]:
    try:
        start_index = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []

    table_lines: list[str] = []
    in_table = False
    for line in lines[start_index + 1:]:
        stripped = line.strip()
        if stripped.startswith("## ") and not in_table:
            return []
        if stripped.startswith("|"):
            table_lines.append(stripped)
            in_table = True
            continue
        if in_table:
            break

    if len(table_lines) < 2:
        return []
    header = _split_markdown_row(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[1:]:
        cells = _split_markdown_row(line)
        if _is_separator_row(cells):
            continue
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        rows.append({header[index]: cells[index] for index in range(len(header))})
    return rows


def _split_statuses(value: str) -> list[str]:
    return [item.strip() for item in value.split("+") if item.strip()]


def _split_item_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_coverage(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_gate_covers(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip().startswith("P2P3-")]


def _gated_statuses(statuses: Sequence[str]) -> list[str]:
    return [status for status in statuses if status in {"staging-gated", "production-gated", "manual-only"}]


def _requires_external_evidence(status: str, classification: str) -> bool:
    return status in {"staging-gated", "production-gated", "manual-only"} or classification in {
        "staging-required",
        "production-required",
        "manual-only",
    }


def _item_number(item_id: str) -> int:
    try:
        return int(item_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 999_999


def _priority_rank(priority: str) -> int:
    ranks = {
        "P2-A": 0,
        "P2-B": 1,
        "P2-C": 2,
        "P2-D": 3,
        "P3": 4,
    }
    return ranks.get(priority, 99)


def _status_rank(status: str) -> int:
    ranks = {
        "production-gated": 0,
        "staging-gated": 1,
        "manual-only": 2,
    }
    return ranks.get(status, 99)


def _next_focus(items: Sequence[dict[str, Any]], pages: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in items
        if item.get("requires_external_evidence") and item.get("next_actions")
    ]
    if not candidates:
        return None
    item = sorted(
        candidates,
        key=lambda candidate: (
            _status_rank(str(candidate.get("status", ""))),
            _priority_rank(str(candidate.get("priority", ""))),
            _item_number(str(candidate.get("id", ""))),
        ),
    )[0]
    item_id = str(item["id"])
    affected_pages = [
        {
            "phase": page["phase"],
            "page": page["page"],
            "status": page["status"],
            "remaining_gate": page["remaining_gate"],
        }
        for page in pages
        if item_id in page.get("external_gate_item_ids", [])
    ]
    focus = {
        "item_id": item_id,
        "item_status": item.get("status", ""),
        "item_priority": item.get("priority", ""),
        "item_classification": item.get("classification", ""),
        "gap": item.get("gap", ""),
        "closure_evidence": item.get("closure_evidence", ""),
        "affected_page_count": len(affected_pages),
        "affected_pages": affected_pages,
        "recommended_gate": item["next_actions"][0],
        "all_item_gates": item.get("next_actions", []),
        "notes": item.get("notes", ""),
    }
    focus["next_bounded_action"] = _next_bounded_action(focus)
    return focus


def _next_bounded_action(focus: dict[str, Any]) -> dict[str, Any]:
    gate = focus.get("recommended_gate") if isinstance(focus.get("recommended_gate"), dict) else {}
    item_id = str(focus.get("item_id") or "")
    item_status = str(focus.get("item_status") or "")
    gate_name = str(gate.get("gate") or "external gate")
    command = str(gate.get("command_or_evidence") or "")
    return {
        "goal": f"Advance {item_id} by executing or unblocking its next required gate: {gate_name}.",
        "evidence_to_inspect": [
            "Run the recommended gate command if its required secure environment and approvals are available.",
            "If the gate returns configuration_missing, auth_missing, input_error, or no sample evidence, record that exact structured status and branch to the required setup path.",
            "Inspect the gate payload for runtime blockers, failed checks, missing args, required env, sample counts, p95/p99 latency, freshness status, and failure handling.",
        ],
        "allowed_scope": [
            ".planning/P2P3-CLOSURE-PLAN.md",
            "docs/modules/app-health-operations/*",
            "docs/modules/runtime-workers/*",
            "docs/operations/monitoring.md",
            "backend/src/fin_ops_platform/tools/*",
            "tests/test_*slo*",
            "tests/test_runtime_sync_closure_gate.py",
            "tests/test_p2p3_closure_summary.py",
        ],
        "architecture_constraints": [
            "Do not mark stale read models as fresh.",
            "Do not bypass PostgreSQL durable queue, dirty scope, outbox, or readiness facts.",
            "Do not use RabbitMQ as a read model state source.",
            "Do not perform production writes, deployments, service restarts, destructive shell commands, or mutating HTTP scenarios without explicit approval and rollback planning.",
            "Do not write credentials to files, logs, scripts, docs, or prompts.",
        ],
        "required_action": [
            "Execute the gate command when safe, or preserve its structured blocker output when required env/auth/input/approval is missing.",
            "If a local code/test/doc gap prevents the gate from branching safely, fix that gap with minimal scoped changes and tests.",
            "Update the P2/P3 ledger and relevant module docs only when facts, validation commands, or remaining gates change.",
        ],
        "recommended_command_or_evidence": command,
        "pass_criteria": gate.get("pass_criteria", ""),
        "failure_handling": gate.get("failure_handling", ""),
        "stop_condition": (
            f"Stop this bounded action after {item_id} has either new passing evidence, a more precise structured blocker, "
            "or a tested local gate/tooling/doc fix. Do not claim final 17-page closure unless every external gate is proven."
        ),
        "status_context": item_status,
    }


def build_summary(plan_path: Path = DEFAULT_PLAN_PATH) -> dict[str, Any]:
    text = plan_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    catalog_rows = _table_after_heading(lines, "## 聚合 Closure Items")
    smoke_gate_rows = _table_after_heading(lines, "## Final Gated Smoke Matrix")
    mapping_rows = _table_after_heading(lines, "## 17 页面覆盖映射")
    page_rows = _table_after_heading(lines, "## 17 页面当前 P2/P3 状态")
    item_rows = _table_after_heading(lines, "## Current Status")

    item_catalog_by_id = {
        row["ID"]: {
            "priority": row.get("Priority", ""),
            "classification": row.get("Classification", ""),
            "covered_pages": _split_coverage(row.get("覆盖页面", "")),
            "gap": row.get("Gap", ""),
            "closure_evidence": row.get("Closure evidence", ""),
        }
        for row in catalog_rows
        if row.get("ID", "").startswith("P2P3-")
    }
    smoke_gates: list[dict[str, Any]] = []
    gates_by_item_id: dict[str, list[dict[str, str]]] = {}
    for row in smoke_gate_rows:
        gate = {
            "gate": row.get("Gate", ""),
            "covers": _split_gate_covers(row.get("Covers", "")),
            "command_or_evidence": row.get("Command / evidence", ""),
            "pass_criteria": row.get("Pass criteria", ""),
            "failure_handling": row.get("Failure handling", ""),
        }
        if not gate["gate"] or not gate["covers"]:
            continue
        smoke_gates.append(gate)
        for item_id in gate["covers"]:
            gates_by_item_id.setdefault(item_id, []).append({
                "gate": str(gate["gate"]),
                "command_or_evidence": str(gate["command_or_evidence"]),
                "pass_criteria": str(gate["pass_criteria"]),
                "failure_handling": str(gate["failure_handling"]),
            })
    primary_ids_by_phase = {
        int(row["Phase"]): _split_item_ids(row["Primary Closure IDs"])
        for row in mapping_rows
        if row.get("Phase", "").isdigit()
    }
    items: list[dict[str, Any]] = []
    item_status_counts: Counter[str] = Counter()
    for row in item_rows:
        item_id = row.get("ID", "")
        status = row.get("Status", "")
        if not item_id.startswith("P2P3-"):
            continue
        item_status_counts[status] += 1
        catalog = item_catalog_by_id.get(item_id, {})
        classification = str(catalog.get("classification", ""))
        items.append({
            "id": item_id,
            "status": status,
            "priority": catalog.get("priority", ""),
            "classification": classification,
            "covered_pages": catalog.get("covered_pages", []),
            "gap": catalog.get("gap", ""),
            "closure_evidence": catalog.get("closure_evidence", ""),
            "requires_external_evidence": _requires_external_evidence(status, classification),
            "next_actions": gates_by_item_id.get(item_id, []),
            "notes": row.get("Notes", ""),
        })

    items_by_id = {item["id"]: item for item in items}
    pages: list[dict[str, Any]] = []
    page_status_counts: Counter[str] = Counter()
    for row in page_rows:
        phase_text = row.get("Phase", "")
        if not phase_text.isdigit():
            continue
        phase = int(phase_text)
        statuses = _split_statuses(row.get("Current P2/P3 status", ""))
        page_status_counts.update(statuses)
        primary_ids = primary_ids_by_phase.get(phase, [])
        page_next_actions: list[dict[str, Any]] = []
        external_gate_item_ids: list[str] = []
        for item_id in primary_ids:
            item = items_by_id.get(item_id)
            if not item or not item.get("requires_external_evidence"):
                continue
            external_gate_item_ids.append(item_id)
            for action in item.get("next_actions", []):
                page_next_actions.append({
                    "item_id": item_id,
                    "item_status": item.get("status", ""),
                    "item_classification": item.get("classification", ""),
                    **action,
                })
        pages.append({
            "phase": phase,
            "page": row.get("Page", ""),
            "status": statuses,
            "gates": _gated_statuses(statuses),
            "primary_closure_ids": primary_ids,
            "external_gate_item_ids": external_gate_item_ids,
            "next_actions": page_next_actions,
            "local_closure_evidence": row.get("Local closure evidence", ""),
            "remaining_gate": row.get("Remaining gate", ""),
        })

    return {
        "status": "gated" if any(page["gates"] for page in pages) else "pass",
        "tool": "p2p3_closure_summary",
        "source_path": str(plan_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "page_count": len(pages),
            "item_count": len(items),
            "gated_page_count": sum(1 for page in pages if page["gates"]),
            "page_status_counts": dict(sorted(page_status_counts.items())),
            "item_status_counts": dict(sorted(item_status_counts.items())),
            "item_classification_counts": dict(sorted(Counter(item["classification"] for item in items if item["classification"]).items())),
            "smoke_gate_count": len(smoke_gates),
        },
        "next_focus": _next_focus(items, pages),
        "smoke_gates": smoke_gates,
        "pages": sorted(pages, key=lambda page: page["phase"]),
        "items": sorted(items, key=lambda item: item["id"]),
    }


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    stdout = stdout or sys.stdout
    if not args.plan.exists():
        report = input_file_error_report(
            tool="p2p3_closure_summary",
            path=str(args.plan),
            error="plan_not_found",
            message=f"P2/P3 closure plan not found: {args.plan}",
        )
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    report = build_summary(args.plan)
    write_json_report(report, output=args.output, stdout=stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
