from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from fin_ops_platform.services.etc_document_parsers import PLATE_RE, REPAYMENT_KEYWORDS, _is_etc_candidate
from fin_ops_platform.services.etc_reconciliation_models import CreditCardItem, TicketRootItem


def refresh_reconciliation_matches(
    *, credit_card_items: list[CreditCardItem], ticket_root_items: list[TicketRootItem], date_window_days: int = 7,
) -> tuple[list[CreditCardItem], list[TicketRootItem]]:
    """One candidate policy and one maximum-cardinality, minimum-cost assignment."""
    manual_cards = {c.item_id for c in credit_card_items if c.manual_resolution == "included_etc"}
    manual_links: dict[str, list[str]] = {}
    seen_manual: set[str] = set()
    by_amount: dict[int, list[TicketRootItem]] = {}
    active_tickets = []
    for ticket in ticket_root_items:
        if ticket.removed:
            continue
        ids = [key for key in ticket.linked_credit_card_item_ids if key in manual_cards]
        if len(ids) > 1 or seen_manual.intersection(ids):
            raise ValueError("conflicting_manual_ticket_links")
        if ids:
            manual_links[ticket.item_id] = ids
            seen_manual.update(ids)
        try:
            datetime.fromisoformat(ticket.transaction_at)
        except ValueError:
            continue
        active_tickets.append(ticket)
        if not ids:
            by_amount.setdefault(_cents(ticket.amount), []).append(ticket)
    for tickets in by_amount.values():
        tickets.sort(key=_ticket_sort_key)
    dates_by_amount = {amount: [t.transaction_at[:10] for t in tickets] for amount, tickets in by_amount.items()}
    candidates_by_card: dict[str, list[TicketRootItem]] = {}
    candidates_by_ticket: dict[str, list[CreditCardItem]] = {}
    cards = []
    for original in credit_card_items:
        description = re.sub(r"\s+", "", original.description).lower()
        excluded = (original.settlement_amount <= 0 or any(k in description for k in REPAYMENT_KEYWORDS)
                    or any(k in description for k in ("加油", "餐饮", "餐厅", "超市"))
                    or original.manual_resolution in {"excluded_non_etc", "excluded_error"})
        card = replace(original, is_etc_candidate=not excluded, match_reason=None)
        cards.append(card)
        if excluded or card.manual_resolution != "unresolved":
            continue
        if card.settlement_currency != "CNY":
            card.match_reason = "结算币种缺失或非人民币，请核对来源"
            continue
        try:
            transaction = date.fromisoformat(card.transaction_date)
            posting = date.fromisoformat(card.posting_date)
            business_date = _extract_business_date(card.description)
        except ValueError:
            card.match_reason = "交易日期或记账日期不合法"
            continue
        known = _is_etc_candidate(card.description, card.settlement_amount)
        start = business_date or (transaction - timedelta(days=date_window_days if known else 0))
        end = business_date or (min(transaction + timedelta(days=1), posting) if known else transaction)
        amount = _cents(card.settlement_amount)
        rows = by_amount.get(amount, [])
        dates = dates_by_amount.get(amount, [])
        plates = set(PLATE_RE.findall(card.description.upper()))
        rejected = set(card.rejected_ticket_ids)
        entry = re.search(r"入口(?:收费)?站\s*[:：]\s*([^\s,，;；]+)", card.description)
        exit_station = re.search(r"出口(?:收费)?站\s*[:：]\s*([^\s,，;；]+)", card.description)
        candidates = [t for t in rows[bisect_left(dates, start.isoformat()):bisect_right(dates, end.isoformat())]
                      if t.item_id not in rejected and (not plates or t.vehicle_plate in plates)
                      and _station_matches(entry.group(1) if entry else "", t.entry_station)
                      and _station_matches(exit_station.group(1) if exit_station else "", t.exit_station)]
        candidates_by_card[card.item_id] = candidates
        for ticket in candidates:
            candidates_by_ticket.setdefault(ticket.item_id, []).append(card)
    auto = _stable_auto_links(ticket_candidates_by_card=candidates_by_card,
        card_candidates_by_ticket=candidates_by_ticket, cards_by_id={c.item_id: c for c in cards},
        tickets_by_id={t.item_id: t for t in active_tickets})
    links = {**auto, **manual_links}
    linked = {key: tid for tid, keys in links.items() for key in keys}
    for card in cards:
        if card.item_id in linked:
            card.recommendation_status = "suggested_match"
            card.match_reason = "人工指定" if card.item_id in seen_manual else "金额一致，按通行日期与商户信息全局分配"
        elif card.manual_resolution == "covered_by_supplement":
            card.recommendation_status = "suggested_match"
            card.match_reason = "补充凭证"
        elif not card.is_etc_candidate:
            card.recommendation_status = "not_candidate"
        else:
            card.recommendation_status = "missing_ticket"
            card.match_reason = card.match_reason or ("合格票根已分配给其他交易" if candidates_by_card.get(card.item_id) else "未找到符合金额、日期和身份条件的票根")
    return cards, [replace(t, linked_credit_card_item_ids=links.get(t.item_id, []) if not t.removed else [],
        recommendation_status="suggested_match" if t.item_id in links and not t.removed else "extra_ticket") for t in ticket_root_items]


def _cents(value: Decimal) -> int:
    amount = Decimal(value) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("invalid_reconciliation_amount")
    return int(amount)


def _station_matches(explicit: str, actual: str) -> bool:
    if not explicit or not actual:
        return True
    return explicit == actual or explicit.endswith(actual) or actual.endswith(explicit)


def _extract_business_date(description: str) -> date | None:
    match = re.search(r"(?<!\d)(\d{8})(?!\d)\s*(?:高速|通行|收费)|(?:通行日期|通行时间)\s*[:：]?\s*(\d{4}[-/]?\d{2}[-/]?\d{2})", description)
    if match is None:
        return None
    raw = (match.group(1) or match.group(2)).replace("-", "").replace("/", "")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))


def _card_sort_key(card: CreditCardItem) -> tuple:
    return (card.transaction_date, card.posting_date, card.source_page or 0, card.source_line or 0,
            card.description, card.card_last4, card.item_id)


def _ticket_sort_key(ticket: TicketRootItem) -> tuple:
    return (ticket.transaction_at, ticket.vehicle_plate, ticket.entry_station, ticket.exit_station, ticket.item_id)


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
    *, cards: list[CreditCardItem], tickets: list[TicketRootItem],
    ticket_candidates_by_card: dict[str, list[TicketRootItem]],
) -> list[tuple[CreditCardItem, TicketRootItem]]:
    # Rectangular Hungarian assignment. Dummy columns represent unmatched cards;
    # their cost exceeds the sum of every possible real edge (cardinality first).
    n, real_count = len(cards), len(tickets)
    order = {t.item_id: j for j, t in enumerate(tickets)}
    edge_scores = []
    for card in cards:
        anchor = _extract_business_date(card.description) or date.fromisoformat(card.transaction_date)
        weak = int(not _is_etc_candidate(card.description, card.settlement_amount))
        edge_scores.append({order[t.item_id]: (weak, abs((date.fromisoformat(t.transaction_at[:10]) - anchor).days),
                            int(date.fromisoformat(t.transaction_at[:10]) > anchor))
                            for t in ticket_candidates_by_card.get(card.item_id, [])})
    max_days = max((score[1] for row in edge_scores for score in row.values()), default=0)
    day_weight = n + 1
    evidence_weight = (n * max_days + 1) * day_weight
    costs = [{j: weak * evidence_weight + days * day_weight + direction for j, (weak, days, direction) in row.items()}
             for row in edge_scores]
    unmatched = n * max((cost for row in costs for cost in row.values()), default=0) + 1
    forbidden = (n + 1) * unmatched + 1
    matrix = [[row.get(j, forbidden) for j in range(real_count)] + [unmatched] * n for row in costs]
    m = real_count + n
    u, v, owner, way = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        owner[0] = i
        j0 = 0
        minimum, used = [forbidden * (n + 1)] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = owner[j0]
            delta, j1 = forbidden * (n + 1), 0
            row = matrix[i0 - 1]
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cost = row[j - 1] - u[i0] - v[j]
                if cost < minimum[j]:
                    minimum[j], way[j] = cost, j0
                if minimum[j] < delta:
                    delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if owner[j0] == 0:
                break
        while j0:
            previous = way[j0]
            owner[j0] = owner[previous]
            j0 = previous
    return [(cards[owner[j] - 1], tickets[j - 1]) for j in range(1, real_count + 1)
            if owner[j] and j - 1 in costs[owner[j] - 1]]
