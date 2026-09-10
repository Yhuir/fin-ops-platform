"""Pure source allocation rules. Sources own account, classification and payment date."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

ZERO = Decimal("0.00")
MONEY = re.compile(r"^(?:0|[1-9]\d{0,14})\.\d{2}$")


class SourceAllocationError(ValueError):
    def __init__(self, message: str, *, path: str, code: str) -> None:
        super().__init__(message)
        self.path = path
        self.code = code


def _fail(message: str, path: str, code: str) -> None:
    raise SourceAllocationError(message, path=path, code=code)


def validate_source_allocations(
    task: dict[str, Any],
    allocations: list[dict[str, str]],
    non_cost_amount: Decimal,
    value: Any,
) -> dict[str, list[dict[str, str]]]:
    """Validate both sides of the allocation, not merely the grand total."""
    if not isinstance(value, dict) or set(value) != {
        "cost_lines", "refund_links", "non_cost_lines"
    }:
        _fail("请填写完整的流水来源分配。", "source_allocations", "source_required")
    targets = {line["unit_id"]: Decimal(line["amount"]) for line in allocations}
    if Decimal(task["oa_total"]) == Decimal(task["net_outflow_total"]):
        for unit in task["units"]:
            if targets[unit["unit_id"]] != Decimal(unit["oa_original_amount"]):
                _fail("金额一致时，每个 OA 单元的成本目标必须保持原金额。", "allocations", "unit_amount_mismatch")
    sources = {
        event["transaction_id"]: Decimal(event["amount"])
        for event in task["bank_events"] if event["event_kind"] == "outflow"
    }
    refunds = {
        event["transaction_id"]: Decimal(event["amount"])
        for event in task["bank_events"] if event["event_kind"] == "wrong_payment_refund"
    }
    used = dict.fromkeys(sources, ZERO)
    unit_used = dict.fromkeys(targets, ZERO)
    refund_used = dict.fromkeys(refunds, ZERO)
    non_cost_used = ZERO
    result: dict[str, list[dict[str, str]]] = {}
    for kind, identity in (("cost_lines", "unit_id"), ("refund_links", "refund_transaction_id"), ("non_cost_lines", None)):
        rows = value[kind]
        if not isinstance(rows, list):
            _fail("分配行必须是数组。", f"source_allocations.{kind}", "invalid_rows")
        seen: set[tuple[str, str]] = set()
        result[kind] = []
        for index, row in enumerate(rows):
            path = f"source_allocations.{kind}[{index}]"
            fields = {"bank_transaction_id", "amount"} | ({identity} if identity else set())
            if not isinstance(row, dict) or set(row) != fields:
                _fail("分配行字段不完整或包含不支持的字段。", path, "invalid_fields")
            bank_id = row["bank_transaction_id"]
            if not isinstance(bank_id, str) or bank_id not in sources:
                _fail("请选择本关联中的支出流水。", path + ".bank_transaction_id", "invalid_source")
            item_id = row[identity] if identity else ""
            if not isinstance(item_id, str):
                _fail("分配对象无效。", path, "invalid_identity")
            if (bank_id, item_id) in seen:
                _fail("同一对象与来源已有分配行，请修改已有行。", path, "duplicate_source")
            seen.add((bank_id, item_id))
            if not isinstance(row["amount"], str) or not MONEY.fullmatch(row["amount"]) or Decimal(row["amount"]) <= ZERO:
                _fail("分配金额必须是大于零的两位小数。", path + ".amount", "invalid_amount")
            amount = Decimal(row["amount"])
            used[bank_id] += amount
            if kind == "cost_lines":
                if item_id not in targets:
                    _fail("成本单元不属于当前关联。", path, "invalid_unit")
                unit_used[item_id] += amount
            elif kind == "refund_links":
                if item_id not in refunds:
                    _fail("退款不属于当前关联的付错退款。", path, "invalid_refund")
                refund_used[item_id] += amount
            else:
                non_cost_used += amount
            result[kind].append(dict(row))
    for bank_id, amount in sources.items():
        if used[bank_id] != amount:
            _fail("每笔支出的成本、退款冲减和非成本合计必须等于该流水金额。", "source_allocations", "source_amount_mismatch")
    if unit_used != targets:
        _fail("每个 OA 单元的来源分配合计必须等于本项成本。", "source_allocations.cost_lines", "unit_amount_mismatch")
    if refund_used != refunds:
        _fail("每笔退款必须完整归属到原支出。", "source_allocations.refund_links", "refund_amount_mismatch")
    if non_cost_used != non_cost_amount:
        _fail("非成本来源合计必须等于非成本金额。", "source_allocations.non_cost_lines", "non_cost_amount_mismatch")
    return result


def automatic_source_allocations(task: dict[str, Any]) -> dict[str, Any] | None:
    """Only unique solutions: one outflow, or one positive unit without deductions."""
    allocations = task["allocations"]
    if not allocations:
        return None
    sources = [event for event in task["bank_events"] if event["event_kind"] == "outflow"]
    refunds = [event for event in task["bank_events"] if event["event_kind"] == "wrong_payment_refund"]
    positive = [line for line in allocations if Decimal(line["amount"]) > ZERO]
    non_cost = Decimal(task["non_cost_amount"])
    result: dict[str, list[dict[str, str]]] = {"cost_lines": [], "refund_links": [], "non_cost_lines": []}
    if len(sources) == 1:
        source_id = sources[0]["transaction_id"]
        result["cost_lines"] = [{**line, "bank_transaction_id": source_id} for line in positive]
        result["refund_links"] = [{"refund_transaction_id": event["transaction_id"], "bank_transaction_id": source_id, "amount": event["amount"]} for event in refunds]
        if non_cost > ZERO:
            result["non_cost_lines"] = [{"bank_transaction_id": source_id, "amount": f"{non_cost:.2f}"}]
    elif len(positive) == 1 and not refunds and non_cost == ZERO:
        result["cost_lines"] = [{"unit_id": positive[0]["unit_id"], "bank_transaction_id": event["transaction_id"], "amount": event["amount"]} for event in sources]
    else:
        return None
    return validate_source_allocations(task, allocations, non_cost, result)


# Bound detail-only combinatorial work; exhaustion is unknown, never a match.
SUGGESTION_MAX_STATES = 50000
SUGGESTION_MAX_NODES = 128


class _SuggestionLimit(Exception):
    pass


def suggest_source_allocations(
    task: dict[str, Any], bank_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Suggest unique whole-source/fixed-unit combinations for human confirmation.

    Active relation membership is supplied by the scoped repository. Suggestions
    never feed completion/statistics. Explicit OA references constrain candidates;
    neither screen order nor a greedy exact-amount match proves uniqueness.
    """
    if (task["status"] != "pending" or task["version"] != 0
            or task["source_allocations"] is not None
            or "allocation_stale" in task["pending_reasons"]
            or not task["amounts_fixed"]
            or any(event["event_kind"] != "outflow" for event in task["bank_events"])):
        return None
    units = [unit for unit in task["units"] if Decimal(unit["oa_original_amount"]) > ZERO]
    events = [event for event in task["bank_events"] if event["event_kind"] == "outflow"]
    if (not units or not events or len(units) + len(events) > SUGGESTION_MAX_NODES
            or any(Decimal(event["amount"]) <= ZERO for event in events)):
        return None
    if (sum((Decimal(e["amount"]) for e in events), ZERO) != Decimal(task["net_outflow_total"])
            or sum((Decimal(u["oa_original_amount"]) for u in units), ZERO) != Decimal(task["oa_total"])
            or Decimal(task["non_cost_amount"]) != ZERO):
        return None
    owners = {row["id"]: set(row.get("source_oa_ids", [])) for row in bank_rows}
    oa_ids = {unit["oa_id"] for unit in units}
    # Conflicting scalar references are bad evidence, not several possible owners.
    if any(len(refs) > 1 or not refs.issubset(oa_ids) for refs in owners.values()):
        return None
    eligible = [{i for i, unit in enumerate(units)
                 if (not owners.get(event["transaction_id"])
                     or unit["oa_id"] in owners[event["transaction_id"]])}
                for event in events]
    try:
        lines = _unique_source_components(units, events, eligible)
    except _SuggestionLimit:
        return None
    return {"cost_lines": lines, "refund_links": [], "non_cost_lines": []} if lines else None


def _unique_source_components(
    units: list[dict[str, Any]], events: list[dict[str, Any]], eligible: list[set[int]],
) -> list[dict[str, str]]:
    """Enumerate star candidates, then exact-cover each independent component.

    A star is one unit paid by whole sources, or one source paying fixed units.
    Arbitrary many-to-many slicing is intentionally not a candidate. Components
    include every overlapping candidate, so a local match cannot steal a source
    from an alternative. Two complete covers disprove uniqueness immediately.
    """
    remaining = SUGGESTION_MAX_STATES

    def step() -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0:
            raise _SuggestionLimit

    def subsets(amounts: list[int], allowed: list[int], target: int) -> list[tuple[int, ...]]:
        ordered = sorted((i for i in allowed if amounts[i] <= target), key=lambda i: (-amounts[i], i))
        suffix = [0] * (len(ordered) + 1)
        for pos in range(len(ordered) - 1, -1, -1):
            suffix[pos] = suffix[pos + 1] + amounts[ordered[pos]]
        found: list[tuple[int, ...]] = []

        def visit(pos: int, needed: int, chosen: tuple[int, ...]) -> None:
            step()
            if needed == 0:
                found.append(chosen)
                return
            if pos == len(ordered) or suffix[pos] < needed:
                return
            for j in range(pos, len(ordered)):
                step()
                i = ordered[j]
                if amounts[i] <= needed:
                    visit(j + 1, needed - amounts[i], (*chosen, i))

        visit(0, target, ())
        return found

    targets = [int(Decimal(u["oa_original_amount"]) * 100) for u in units]
    amounts = [int(Decimal(e["amount"]) * 100) for e in events]
    size = len(units)
    # Each candidate covers unit bits followed by source bits, with precise cents.
    candidates: dict[int, list[tuple[int, int, int]]] = {}
    for u, target in enumerate(targets):
        for banks in subsets(amounts, [b for b, allowed in enumerate(eligible) if u in allowed], target):
            mask = (1 << u) | sum(1 << (size + b) for b in banks)
            candidates[mask] = [(u, b, amounts[b]) for b in banks]
    for b, amount in enumerate(amounts):
        for owners in subsets(targets, sorted(eligible[b]), amount):
            mask = (1 << (size + b)) | sum(1 << u for u in owners)
            candidates[mask] = [(u, b, targets[u]) for u in owners]

    by_node: dict[int, list[int]] = {}
    for mask in candidates:
        for node in range(size + len(events)):
            step()
            if mask & (1 << node):
                by_node.setdefault(node, []).append(mask)
    unvisited = set(by_node)
    resolved: list[tuple[int, int, int]] = []
    while unvisited:
        stack = [min(unvisited)]
        component = 0
        while stack:
            node = stack.pop()
            if node not in unvisited:
                continue
            unvisited.remove(node)
            component |= 1 << node
            for mask in by_node[node]:
                step()
                stack.extend(n for n in unvisited if mask & (1 << n))
        solutions: list[list[int]] = []

        def cover(open_nodes: int, chosen: list[int]) -> None:
            step()
            if len(solutions) == 2:
                return
            if not open_nodes:
                solutions.append(chosen)
                return
            choices = None
            for node in by_node:
                if not open_nodes & (1 << node):
                    continue
                options = [m for m in by_node[node] if m & open_nodes == m]
                if not options:
                    return
                if choices is None or len(options) < len(choices):
                    choices = options
            for mask in choices or []:
                cover(open_nodes ^ mask, [*chosen, mask])
                if len(solutions) == 2:
                    return

        cover(component, [])
        if len(solutions) == 1:
            resolved.extend(line for mask in solutions[0] for line in candidates[mask])
    return [{"unit_id": units[u]["unit_id"], "bank_transaction_id": events[b]["transaction_id"],
             "amount": f"{Decimal(amount) / 100:.2f}"} for u, b, amount in sorted(resolved)]


def complete_source_task(task: dict[str, Any], source_allocations: Any = None) -> dict[str, Any]:
    """Resolve current facts; saving a source decision need not resolve missing metadata."""
    reasons = []
    if task["allocations"] and Decimal(task["oa_total"]) == Decimal(task["net_outflow_total"]):
        targets = {unit["unit_id"]: Decimal(unit["oa_original_amount"]) for unit in task["units"]}
        if any(Decimal(line["amount"]) != targets[line["unit_id"]] for line in task["allocations"]):
            _fail("保存的单元金额与当前 OA 目标不一致。", "allocations", "unit_amount_mismatch")
    if task["status"] == "stale":
        reasons.append("allocation_stale")
    elif not task["allocations"]:
        reasons.append("amount_required")
    else:
        if source_allocations is not None:
            source_allocations = validate_source_allocations(task, task["allocations"], Decimal(task["non_cost_amount"]), source_allocations)
        else:
            source_allocations = automatic_source_allocations(task)
        if source_allocations is None:
            reasons.append("source_required")
        else:
            events = {event["transaction_id"]: event for event in task["bank_events"]}
            for line in source_allocations["cost_lines"]:
                event = events[line["bank_transaction_id"]]
                if not event["bank_tag_code"] or not event["bank_tag_primary_label"]:
                    reasons.append("bank_tag_missing")
                if not event["bank_account_label"]:
                    reasons.append("bank_account_missing")
                if not event["trade_time"]:
                    reasons.append("source_date_missing")
    task["suggested_source_allocations"] = None
    task["source_allocations"] = source_allocations
    task["pending_reasons"] = list(dict.fromkeys(reasons))
    task["status"] = "pending" if reasons else "allocated"
    task["amounts_fixed"] = Decimal(task["oa_total"]) == Decimal(task["net_outflow_total"])
    return task
