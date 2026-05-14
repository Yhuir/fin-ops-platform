from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from fin_ops_platform.services.etc_reconciliation_models import CreditCardItem, TicketRootItem


def refresh_reconciliation_matches(
    *,
    credit_card_items: list[CreditCardItem],
    ticket_root_items: list[TicketRootItem],
    date_window_days: int = 1,
) -> tuple[list[CreditCardItem], list[TicketRootItem]]:
    active_tickets = [ticket for ticket in ticket_root_items if not ticket.removed]
    ticket_candidates_by_card: dict[str, list[TicketRootItem]] = {}
    card_candidates_by_ticket: dict[str, list[CreditCardItem]] = {}

    for card in credit_card_items:
        if not card.is_etc_candidate or card.manual_resolution == "covered_by_supplement":
            continue
        candidates = [
            ticket
            for ticket in active_tickets
            if _money(ticket.amount) == _money(card.settlement_amount)
            and _date_in_card_window(
                ticket.transaction_at[:10],
                transaction_date=card.transaction_date,
                posting_date=card.posting_date,
                fallback_days=date_window_days,
            )
        ]
        ticket_candidates_by_card[card.item_id] = candidates
        for ticket in candidates:
            card_candidates_by_ticket.setdefault(ticket.item_id, []).append(card)

    auto_link_by_ticket: dict[str, list[str]] = {}
    auto_linked_card_ids: set[str] = set()
    for card in credit_card_items:
        candidates = ticket_candidates_by_card.get(card.item_id, [])
        if len(candidates) != 1:
            continue
        ticket = candidates[0]
        if len(card_candidates_by_ticket.get(ticket.item_id, [])) != 1:
            continue
        auto_link_by_ticket.setdefault(ticket.item_id, []).append(card.item_id)
        auto_linked_card_ids.add(card.item_id)

    manual_link_by_ticket: dict[str, list[str]] = {}
    manually_resolved_card_ids = {
        card.item_id
        for card in credit_card_items
        if card.manual_resolution == "included_etc"
    }
    for ticket in active_tickets:
        manual_ids = [
            card_id
            for card_id in ticket.linked_credit_card_item_ids
            if card_id in manually_resolved_card_ids
        ]
        if manual_ids:
            manual_link_by_ticket[ticket.item_id] = list(dict.fromkeys(manual_ids))

    refreshed_cards: list[CreditCardItem] = []
    for card in credit_card_items:
        if not card.is_etc_candidate:
            refreshed_cards.append(replace(card, recommendation_status="not_candidate"))
            continue
        if card.manual_resolution == "covered_by_supplement":
            refreshed_cards.append(replace(card, recommendation_status="suggested_match"))
            continue
        if card.item_id in manually_resolved_card_ids or card.item_id in auto_linked_card_ids:
            refreshed_cards.append(replace(card, recommendation_status="suggested_match"))
            continue
        candidates = ticket_candidates_by_card.get(card.item_id, [])
        if candidates:
            status = "needs_review"
        else:
            status = "missing_ticket"
        refreshed_cards.append(replace(card, recommendation_status=status))

    refreshed_tickets: list[TicketRootItem] = []
    for ticket in ticket_root_items:
        if ticket.removed:
            refreshed_tickets.append(ticket)
            continue
        linked_ids = list(dict.fromkeys([*manual_link_by_ticket.get(ticket.item_id, []), *auto_link_by_ticket.get(ticket.item_id, [])]))
        candidates = card_candidates_by_ticket.get(ticket.item_id, [])
        if linked_ids:
            status = "suggested_match"
        elif candidates:
            status = "needs_review"
        else:
            status = "extra_ticket"
        refreshed_tickets.append(replace(ticket, recommendation_status=status, linked_credit_card_item_ids=linked_ids))

    return refreshed_cards, refreshed_tickets


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _date_in_window(candidate_date: str, anchor_date: str, *, days: int) -> bool:
    try:
        candidate = date.fromisoformat(candidate_date)
        anchor = date.fromisoformat(anchor_date)
    except ValueError:
        try:
            candidate = datetime.fromisoformat(candidate_date).date()
            anchor = datetime.fromisoformat(anchor_date).date()
        except ValueError:
            return False
    return anchor - timedelta(days=days) <= candidate <= anchor + timedelta(days=days)


def _date_in_card_window(
    candidate_date: str,
    *,
    transaction_date: str,
    posting_date: str,
    fallback_days: int,
) -> bool:
    try:
        candidate = _parse_date(candidate_date)
        transaction = _parse_date(transaction_date)
    except ValueError:
        return False
    try:
        posting = _parse_date(posting_date)
    except ValueError:
        return _date_in_window(candidate_date, transaction_date, days=fallback_days)
    window_start = transaction - timedelta(days=1)
    return window_start <= candidate <= posting


def _parse_date(value: str) -> date:
    raw = str(value or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return datetime.fromisoformat(raw).date()
