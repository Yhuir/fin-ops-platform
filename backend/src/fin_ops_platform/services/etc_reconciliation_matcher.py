from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from fin_ops_platform.services.etc_reconciliation_models import CreditCardItem, TicketRootItem


def refresh_reconciliation_matches(
    *,
    credit_card_items: list[CreditCardItem],
    ticket_root_items: list[TicketRootItem],
    date_window_days: int = 1,
) -> tuple[list[CreditCardItem], list[TicketRootItem]]:
    active_tickets = [ticket for ticket in ticket_root_items if not ticket.removed]
    manually_resolved_card_ids = {
        card.item_id
        for card in credit_card_items
        if card.manual_resolution == "included_etc"
    }
    manual_link_by_ticket: dict[str, list[str]] = {}
    for ticket in active_tickets:
        manual_ids = [
            card_id
            for card_id in ticket.linked_credit_card_item_ids
            if card_id in manually_resolved_card_ids
        ]
        if manual_ids:
            manual_link_by_ticket[ticket.item_id] = list(dict.fromkeys(manual_ids))
    manually_consumed_ticket_ids = set(manual_link_by_ticket)

    ticket_candidates_by_card: dict[str, list[TicketRootItem]] = {}
    card_candidates_by_ticket: dict[str, list[CreditCardItem]] = {}

    for card in credit_card_items:
        if not card.is_etc_candidate or card.manual_resolution != "unresolved":
            continue
        candidates = [
            ticket
            for ticket in active_tickets
            if ticket.item_id not in manually_consumed_ticket_ids
            if _money(ticket.amount) == _money(card.settlement_amount)
            and _date_in_card_window(
                ticket.transaction_at[:10],
                transaction_date=card.transaction_date,
                posting_date=card.posting_date,
                description=card.description,
                fallback_days=date_window_days,
            )
        ]
        ticket_candidates_by_card[card.item_id] = candidates
        for ticket in candidates:
            card_candidates_by_ticket.setdefault(ticket.item_id, []).append(card)

    cards_by_id = {card.item_id: card for card in credit_card_items}
    tickets_by_id = {ticket.item_id: ticket for ticket in active_tickets}
    auto_link_by_ticket = _stable_auto_links(
        ticket_candidates_by_card=ticket_candidates_by_card,
        card_candidates_by_ticket=card_candidates_by_ticket,
        cards_by_id=cards_by_id,
        tickets_by_id=tickets_by_id,
    )
    auto_linked_card_ids = {
        card_id
        for card_ids in auto_link_by_ticket.values()
        for card_id in card_ids
    }

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


def _date_in_card_window(
    candidate_date: str,
    *,
    transaction_date: str,
    posting_date: str,
    description: str,
    fallback_days: int,
) -> bool:
    try:
        candidate = _parse_date(candidate_date)
        transaction = _parse_date(transaction_date)
    except ValueError:
        return False
    business_date = _extract_business_date(description)
    if business_date:
        return candidate == business_date
    try:
        posting = _parse_date(posting_date)
    except ValueError:
        return transaction - timedelta(days=fallback_days) <= candidate <= transaction + timedelta(days=fallback_days)
    window_start = transaction - timedelta(days=fallback_days)
    return window_start <= candidate <= posting


def _parse_date(value: str) -> date:
    raw = str(value or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return datetime.fromisoformat(raw).date()


def _extract_business_date(description: str) -> date | None:
    for match in re.finditer(r"(?<!\d)(\d{8})(?!\d)", str(description or "")):
        raw = match.group(1)
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            continue
    return None


def _stable_auto_links(
    *,
    ticket_candidates_by_card: dict[str, list[TicketRootItem]],
    card_candidates_by_ticket: dict[str, list[CreditCardItem]],
    cards_by_id: dict[str, CreditCardItem],
    tickets_by_id: dict[str, TicketRootItem],
) -> dict[str, list[str]]:
    auto_link_by_ticket: dict[str, list[str]] = {}
    visited_cards: set[str] = set()
    visited_tickets: set[str] = set()

    for card_id in sorted(ticket_candidates_by_card, key=lambda item_id: _card_sort_key(cards_by_id[item_id])):
        if card_id in visited_cards:
            continue
        component_card_ids, component_ticket_ids = _candidate_component(
            card_id=card_id,
            ticket_candidates_by_card=ticket_candidates_by_card,
            card_candidates_by_ticket=card_candidates_by_ticket,
            visited_cards=visited_cards,
            visited_tickets=visited_tickets,
        )
        if not component_card_ids or not component_ticket_ids:
            continue
        cards = sorted((cards_by_id[item_id] for item_id in component_card_ids), key=_card_sort_key)
        tickets = sorted((tickets_by_id[item_id] for item_id in component_ticket_ids), key=_ticket_sort_key)
        if len(cards) < len(tickets):
            continue
        pairs = _stable_component_pairs(
            cards=cards,
            tickets=tickets,
            ticket_candidates_by_card=ticket_candidates_by_card,
        )
        for card, ticket in pairs:
            auto_link_by_ticket[ticket.item_id] = [card.item_id]
    return auto_link_by_ticket


def _candidate_component(
    *,
    card_id: str,
    ticket_candidates_by_card: dict[str, list[TicketRootItem]],
    card_candidates_by_ticket: dict[str, list[CreditCardItem]],
    visited_cards: set[str],
    visited_tickets: set[str],
) -> tuple[set[str], set[str]]:
    component_card_ids: set[str] = set()
    component_ticket_ids: set[str] = set()
    stack: list[tuple[str, str]] = [("card", card_id)]
    while stack:
        kind, item_id = stack.pop()
        if kind == "card":
            if item_id in visited_cards:
                continue
            visited_cards.add(item_id)
            component_card_ids.add(item_id)
            for ticket in ticket_candidates_by_card.get(item_id, []):
                if ticket.item_id not in visited_tickets:
                    stack.append(("ticket", ticket.item_id))
        else:
            if item_id in visited_tickets:
                continue
            visited_tickets.add(item_id)
            component_ticket_ids.add(item_id)
            for card in card_candidates_by_ticket.get(item_id, []):
                if card.item_id not in visited_cards:
                    stack.append(("card", card.item_id))
    return component_card_ids, component_ticket_ids


def _stable_component_pairs(
    *,
    cards: list[CreditCardItem],
    tickets: list[TicketRootItem],
    ticket_candidates_by_card: dict[str, list[TicketRootItem]],
) -> list[tuple[CreditCardItem, TicketRootItem]]:
    ticket_order = {ticket.item_id: index for index, ticket in enumerate(tickets)}
    candidate_ticket_ids_by_card = {
        card.item_id: [
            ticket.item_id
            for ticket in sorted(ticket_candidates_by_card.get(card.item_id, []), key=_ticket_sort_key)
            if ticket.item_id in ticket_order
        ]
        for card in cards
    }
    if len(tickets) <= 16:
        pairs = _best_stable_pairs(
            cards=cards,
            ticket_order=ticket_order,
            candidate_ticket_ids_by_card=candidate_ticket_ids_by_card,
        )
        return [(cards[card_index], tickets[ticket_index]) for card_index, ticket_index in pairs]

    matched_card_to_ticket = _deterministic_bipartite_pairs(
        cards=cards,
        candidate_ticket_ids_by_card=candidate_ticket_ids_by_card,
    )
    return [
        (card, tickets[ticket_order[matched_card_to_ticket[card.item_id]]])
        for card in cards
        if card.item_id in matched_card_to_ticket
    ]


def _deterministic_bipartite_pairs(
    *,
    cards: list[CreditCardItem],
    candidate_ticket_ids_by_card: dict[str, list[str]],
) -> dict[str, str]:
    matched_ticket_to_card: dict[str, str] = {}

    def assign(card_id: str, seen_ticket_ids: set[str]) -> bool:
        for ticket_id in candidate_ticket_ids_by_card.get(card_id, []):
            if ticket_id in seen_ticket_ids:
                continue
            seen_ticket_ids.add(ticket_id)
            current_card_id = matched_ticket_to_card.get(ticket_id)
            if current_card_id is None or assign(current_card_id, seen_ticket_ids):
                matched_ticket_to_card[ticket_id] = card_id
                return True
        return False

    for card in reversed(cards):
        assign(card.item_id, set())
    return {card_id: ticket_id for ticket_id, card_id in matched_ticket_to_card.items()}


def _best_stable_pairs(
    *,
    cards: list[CreditCardItem],
    ticket_order: dict[str, int],
    candidate_ticket_ids_by_card: dict[str, list[str]],
) -> tuple[tuple[int, int], ...]:
    @lru_cache(maxsize=None)
    def choose(card_index: int, used_ticket_indexes: frozenset[int]) -> tuple[tuple[int, int], ...]:
        if card_index >= len(cards):
            return ()

        best = choose(card_index + 1, used_ticket_indexes)
        card = cards[card_index]
        for ticket_id in candidate_ticket_ids_by_card.get(card.item_id, []):
            ticket_index = ticket_order[ticket_id]
            if ticket_index in used_ticket_indexes:
                continue
            candidate = (
                (card_index, ticket_index),
                *choose(card_index + 1, frozenset((*used_ticket_indexes, ticket_index))),
            )
            if _stable_pair_tuple_is_better(candidate, best):
                best = candidate
        return best

    return choose(0, frozenset())


def _stable_pair_tuple_is_better(
    candidate: tuple[tuple[int, int], ...],
    current: tuple[tuple[int, int], ...],
) -> bool:
    if len(candidate) != len(current):
        return len(candidate) > len(current)
    return candidate < current


def _card_sort_key(card: CreditCardItem) -> tuple[date, date, date, int, str]:
    transaction = _parse_date_or_max(card.transaction_date)
    return (
        _extract_business_date(card.description) or transaction,
        transaction,
        _parse_date_or_max(card.posting_date),
        card.source_line if card.source_line is not None else 10**9,
        card.item_id,
    )


def _ticket_sort_key(ticket: TicketRootItem) -> tuple[datetime, int, str]:
    return (
        _parse_datetime_or_max(ticket.transaction_at),
        ticket.source_page if ticket.source_page is not None else 10**9,
        ticket.item_id,
    )


def _parse_date_or_max(value: str) -> date:
    try:
        return _parse_date(value)
    except ValueError:
        return date.max


def _parse_datetime_or_max(value: str) -> datetime:
    raw = str(value or "").strip()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed_date = _parse_date(raw)
        except ValueError:
            return datetime.max
        return datetime.combine(parsed_date, datetime.min.time())
