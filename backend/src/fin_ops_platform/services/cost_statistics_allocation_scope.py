"""Cost-only task projection and source-owned save merging; no I/O or classification."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fin_ops_platform.services.cost_statistics_source_allocation import (
    SourceAllocationError,
    complete_source_task,
    validate_source_allocations,
)

ZERO = Decimal('0.00')
KINDS = ('cost_lines', 'refund_links', 'non_cost_lines')


def source_totals(units: list[dict[str, Any]], decision: dict[str, Any]) -> tuple[list[dict[str, str]], Decimal]:
    totals = dict.fromkeys((unit['unit_id'] for unit in units), ZERO)
    for line in decision['cost_lines']:
        totals[line['unit_id']] += Decimal(line['amount'])
    return ([{'unit_id': key, 'amount': f'{amount:.2f}'} for key, amount in totals.items()],
            sum((Decimal(line['amount']) for line in decision['non_cost_lines']), ZERO))


def covered_source_task(task: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Validate persisted decisions against actual covered sources, allowing new unassigned sources."""
    covered = {line['bank_transaction_id'] for kind in KINDS for line in decision[kind]}
    refund_amounts: dict[str, Decimal] = {}
    for line in decision['refund_links']:
        key = line['refund_transaction_id']
        refund_amounts[key] = refund_amounts.get(key, ZERO) + Decimal(line['amount'])
    events = []
    for event in task['bank_events']:
        if event['event_kind'] == 'outflow' and event['transaction_id'] in covered:
            events.append(event)
        elif event['event_kind'] == 'wrong_payment_refund' and event['transaction_id'] in refund_amounts:
            amount = refund_amounts[event['transaction_id']]
            if amount > Decimal(event['amount']):
                raise SourceAllocationError('退款分配超过原始退款金额。', path='source_allocations.refund_links', code='refund_amount_mismatch')
            events.append({**event, 'amount': f'{amount:.2f}'})
    allocations, non_cost = source_totals(task['units'], decision)
    result = {**task, 'bank_events': events, 'allocations': allocations,
              'non_cost_amount': f'{non_cost:.2f}', 'amounts_fixed': False}
    validate_source_allocations(result, allocations, non_cost, decision)
    return result


def project_source_task(task: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    """Expose the current cost scope without changing canonical facts or stored decisions."""
    sources = [e for e in task['bank_events'] if e['event_kind'] == 'outflow']
    selected = {e['transaction_id'] for e in sources if e['in_project_cost_scope']}
    all_ids = {e['transaction_id'] for e in sources}
    scoped = {kind: [dict(line) for line in decision[kind] if line['bank_transaction_id'] in selected]
              for kind in KINDS} if decision is not None else None
    refunds = [e for e in task['bank_events'] if e['event_kind'] == 'wrong_payment_refund']
    unresolved_refund = False
    refund_events = []
    links_by_refund: dict[str, list[dict[str, str]]] = {}
    if decision:
        for line in decision['refund_links']:
            links_by_refund.setdefault(line['refund_transaction_id'], []).append(line)
    for event in refunds:
        links = links_by_refund.get(event['transaction_id'], [])
        if selected == all_ids:
            refund_events.append(event)
        elif selected:
            if sum((Decimal(line['amount']) for line in links), ZERO) != Decimal(event['amount']):
                unresolved_refund = True
            else:
                amount = sum((Decimal(line['amount']) for line in links if line['bank_transaction_id'] in selected), ZERO)
                if amount:
                    refund_events.append({**event, 'amount': f'{amount:.2f}'})
    units = task['units']
    covered_inside = {line['bank_transaction_id'] for kind in KINDS for line in scoped[kind]} if scoped else set()
    if decision is not None and selected != all_ids and covered_inside == selected:
        outside_units = {line['unit_id'] for line in decision['cost_lines'] if line['bank_transaction_id'] not in selected}
        inside_units = {line['unit_id'] for line in scoped['cost_lines']}
        units = [unit for unit in units if unit['unit_id'] not in outside_units - inside_units]
    events = [e for e in sources if e['transaction_id'] in selected] + refund_events
    gross = sum((Decimal(e['amount']) for e in events if e['event_kind'] == 'outflow'), ZERO)
    refund_total = sum((Decimal(e['amount']) for e in refund_events), ZERO)
    oa_total = sum((Decimal(u['oa_original_amount']) for u in units), ZERO)
    result = {**task, 'units': units, 'bank_events': events, 'oa_total': f'{oa_total:.2f}',
              'gross_outflow_total': f'{gross:.2f}', 'wrong_payment_refund_total': f'{refund_total:.2f}',
              'net_outflow_total': f'{gross - refund_total:.2f}', 'difference': f'{gross - refund_total - oa_total:.2f}',
              'in_project_cost_scope': bool(selected), 'amounts_fixed': oa_total == gross - refund_total,
              'source_allocations': scoped, 'suggested_source_allocations': None}
    if scoped is not None:
        allocations, non_cost = source_totals(units, scoped)
        result.update(allocations=allocations, non_cost_amount=f'{non_cost:.2f}',
                      non_cost_reason=task['non_cost_reason'] if non_cost else '')
        # A source slice is an explicit amount decision, not the original full OA target.
        result['amounts_fixed'] = result['amounts_fixed'] and all(
            line['amount'] == unit['oa_original_amount'] for line, unit in zip(allocations, units, strict=True))
    elif selected != all_ids:
        result.update(allocations=[{'unit_id': u['unit_id'], 'amount': u['oa_original_amount']} for u in units]
                      if result['amounts_fixed'] else [], non_cost_amount='0.00', non_cost_reason='')
    if not selected or unresolved_refund:
        result.update(status='pending', pending_reasons=['scope_refund_required'] if unresolved_refund else [],
                      allocations=[], source_allocations=None)
        return result
    if task['status'] == 'stale':
        return complete_source_task(result)
    if scoped is None and selected != all_ids:
        # Narrowing scope must not silently confirm a previously ambiguous/manual task.
        result.update(status='pending', pending_reasons=['source_required' if result['allocations'] else 'amount_required'])
        return result
    if scoped is not None:
        covered_source_task(result, scoped)
        covered = {line['bank_transaction_id'] for kind in KINDS for line in scoped[kind]}
        if covered != selected:
            result.update(status='pending', pending_reasons=['source_required'], amounts_fixed=False)
            return result
    return complete_source_task(result, scoped)


def merge_source_decision(task: dict[str, Any], previous: dict[str, Any] | None,
                          current: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace only editable bank sources; retain valid decisions outside the current scope."""
    selected = {e['transaction_id'] for e in task['bank_events'] if e['event_kind'] == 'outflow'}
    retained = previous.get('source_allocations') if previous and previous.get('source_fingerprint') == task['source_fingerprint'] else None
    decision = {kind: [dict(line) for line in retained[kind] if line['bank_transaction_id'] not in selected] + current[kind]
                if retained else list(current[kind]) for kind in KINDS}
    allocations, non_cost = source_totals(units, decision)
    outside_non_cost = retained and any(line['bank_transaction_id'] not in selected for line in retained['non_cost_lines'])
    reasons = list(dict.fromkeys(reason for reason in [previous['non_cost_reason'] if outside_non_cost else '', task['non_cost_reason']] if reason))
    return {'source_allocations': decision, 'allocations': allocations,
            'non_cost_amount': f'{non_cost:.2f}', 'non_cost_reason': '；'.join(reasons) if non_cost else ''}
