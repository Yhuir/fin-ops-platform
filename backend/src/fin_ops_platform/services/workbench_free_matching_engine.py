from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json
from typing import Iterable, Literal


RULE_VERSION = "2026-08-24-in-progress-oa-facts-v13"
MATCHABLE_ROW_TYPES = frozenset({"oa", "bank", "invoice"})
ROW_TYPE_ORDER = {"oa": 0, "bank": 1, "invoice": 2}
STRONG_COMPOSITE_EVIDENCE_KINDS = frozenset(
    {
        "business_reference",
        "counterparty",
        "employee_reimbursement_payee",
        "invoice_number",
        "project_reference",
        "tax_no",
    }
)
EXPLICIT_REFERENCE_KINDS = frozenset(
    {
        "attachment_source",
        "canonical_source",
        "contract_reference",
        "invoice_reference",
        "oa_source",
        "order_reference",
        "original_reference",
        "transaction_reference",
    }
)

MemberKey = tuple[str, str]


def canonical_member_key(row_type: object, canonical_object_identity: object) -> MemberKey:
    normalized_row_type = str(row_type or "").strip().lower()
    normalized_identity = str(canonical_object_identity or "").strip()
    if normalized_row_type not in MATCHABLE_ROW_TYPES:
        raise ValueError(f"Unsupported formal relation row type: {normalized_row_type or '<empty>'}.")
    if not normalized_identity:
        raise ValueError("Formal relation canonical object identity is required.")
    return normalized_row_type, normalized_identity


def relation_fingerprint(member_keys: Iterable[MemberKey]) -> str:
    normalized = sorted(
        {canonical_member_key(row_type, identity) for row_type, identity in member_keys},
        key=_member_sort_key,
    )
    if len(normalized) < 2:
        raise ValueError("A formal relation fingerprint requires at least two canonical members.")
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, order=True)
class FormalRelationReference:
    kind: str
    value: str
    target_row_type: str = ""
    target_identity: str = ""
    original: bool = False

    def __post_init__(self) -> None:
        kind = str(self.kind or "").strip().lower()
        value = str(self.value or "").strip()
        target_row_type = str(self.target_row_type or "").strip().lower()
        target_identity = str(self.target_identity or "").strip()
        if kind not in EXPLICIT_REFERENCE_KINDS:
            raise ValueError(f"Unsupported explicit reference kind: {kind or '<empty>'}.")
        if not value:
            raise ValueError("Explicit reference value is required.")
        if bool(target_row_type) != bool(target_identity):
            raise ValueError("Explicit reference target row type and identity must be provided together.")
        if target_row_type:
            canonical_member_key(target_row_type, target_identity)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "target_row_type", target_row_type)
        object.__setattr__(self, "target_identity", target_identity)

    @property
    def target_member_key(self) -> MemberKey | None:
        if not self.target_row_type:
            return None
        return canonical_member_key(self.target_row_type, self.target_identity)


@dataclass(frozen=True, slots=True)
class FormalRelationFact:
    row_type: str
    canonical_object_identity: str
    row_id: str
    amount_minor: int
    currency: str
    direction: Literal["expenditure", "income"]
    fact_date: date | None
    evidence_keys: tuple[tuple[str, str], ...] = ()
    references: tuple[FormalRelationReference, ...] = ()
    source_version: str = ""
    reversal_key: tuple[str, ...] | None = None
    reversal_polarity: Literal["blue", "red"] | None = None

    def __post_init__(self) -> None:
        row_type, identity = canonical_member_key(self.row_type, self.canonical_object_identity)
        row_id = str(self.row_id or "").strip()
        currency = str(self.currency or "").strip().upper()
        direction = str(self.direction or "").strip().lower()
        if not row_id:
            raise ValueError("Formal relation fact row_id is required.")
        if type(self.amount_minor) is not int:
            raise TypeError("Formal relation fact amount_minor must be an integer.")
        if not currency:
            raise ValueError("Formal relation fact currency is required.")
        if direction not in {"expenditure", "income"}:
            raise ValueError("Formal relation fact direction must be expenditure or income.")
        if self.fact_date is not None and not isinstance(self.fact_date, date):
            raise TypeError("Formal relation fact fact_date must be a date or None.")
        if self.reversal_polarity not in {None, "blue", "red"}:
            raise ValueError("Formal relation fact reversal_polarity must be blue, red or None.")
        reversal_key = (
            tuple(str(item or "").strip() for item in self.reversal_key)
            if self.reversal_key is not None
            else None
        )
        if reversal_key is not None and (not reversal_key or any(not item for item in reversal_key)):
            raise ValueError("Formal relation fact reversal_key values must be non-empty.")
        if (reversal_key is None) != (self.reversal_polarity is None):
            raise ValueError("Formal relation fact reversal key and polarity must be provided together.")
        normalized_evidence: set[tuple[str, str]] = set()
        for raw_kind, raw_value in self.evidence_keys:
            kind = str(raw_kind or "").strip().lower()
            value = str(raw_value or "").strip()
            if kind not in STRONG_COMPOSITE_EVIDENCE_KINDS:
                raise ValueError(f"Unsupported strong evidence kind: {kind or '<empty>'}.")
            if not value:
                raise ValueError("Strong evidence value is required.")
            normalized_evidence.add((kind, value))
        object.__setattr__(self, "row_type", row_type)
        object.__setattr__(self, "canonical_object_identity", identity)
        object.__setattr__(self, "row_id", row_id)
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "evidence_keys", tuple(sorted(normalized_evidence)))
        object.__setattr__(self, "references", tuple(sorted(set(self.references))))
        object.__setattr__(self, "source_version", str(self.source_version or "").strip())
        object.__setattr__(self, "reversal_key", reversal_key)

    @property
    def member_key(self) -> MemberKey:
        return self.row_type, self.canonical_object_identity


@dataclass(frozen=True, slots=True)
class ActiveFormalRelationAnchor:
    case_id: str
    member_keys: tuple[MemberKey, ...]

    def __post_init__(self) -> None:
        case_id = str(self.case_id or "").strip()
        members = tuple(sorted({canonical_member_key(*item) for item in self.member_keys}, key=_member_sort_key))
        if not case_id:
            raise ValueError("Active formal relation anchor case_id is required.")
        if len(members) < 2:
            raise ValueError("Active formal relation anchor requires at least two members.")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "member_keys", members)


@dataclass(frozen=True, slots=True)
class FormalRelationFactBatch:
    facts: tuple[FormalRelationFact, ...]
    active_relations: tuple[ActiveFormalRelationAnchor, ...] = ()
    withdrawal_fingerprints: frozenset[str] = frozenset()
    affected_scopes: tuple[str, ...] = ()
    source_versions: tuple[tuple[str, str], ...] = ()
    batch_hash: str = ""

    def __post_init__(self) -> None:
        facts = tuple(sorted(self.facts, key=lambda fact: _member_sort_key(fact.member_key)))
        member_keys = [fact.member_key for fact in facts]
        if len(member_keys) != len(set(member_keys)):
            raise ValueError("Formal relation fact batch contains duplicate canonical identities.")
        active_relations = tuple(sorted(self.active_relations, key=lambda item: item.case_id))
        active_members: dict[MemberKey, str] = {}
        for anchor in active_relations:
            for member_key in anchor.member_keys:
                prior = active_members.setdefault(member_key, anchor.case_id)
                if prior != anchor.case_id:
                    raise ValueError("A canonical fact cannot belong to multiple active formal relations.")
        scopes = tuple(sorted({str(scope or "").strip() for scope in self.affected_scopes if str(scope or "").strip()}))
        versions = tuple(sorted({(str(key).strip(), str(value).strip()) for key, value in self.source_versions if str(key).strip()}))
        withdrawals = frozenset(str(item).strip() for item in self.withdrawal_fingerprints if str(item).strip())
        batch_hash = str(self.batch_hash or "").strip() or _fact_batch_hash(facts, active_relations, withdrawals, versions)
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "active_relations", active_relations)
        object.__setattr__(self, "withdrawal_fingerprints", withdrawals)
        object.__setattr__(self, "affected_scopes", scopes)
        object.__setattr__(self, "source_versions", versions)
        object.__setattr__(self, "batch_hash", batch_hash)


@dataclass(frozen=True, slots=True)
class FormalRelationSearchLimits:
    max_search_states: int = 200_000
    max_working_bytes: int = 64 * 1024 * 1024
    max_deadline_states: int = 200_000

    def __post_init__(self) -> None:
        for name in ("max_search_states", "max_working_bytes", "max_deadline_states"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class FormalRelationPlan:
    case_id: str
    member_keys: tuple[MemberKey, ...]
    row_ids: tuple[str, ...]
    row_types: tuple[str, ...]
    relation_fingerprint: str
    rule_code: str
    rule_version: str
    amount_minor: int
    currency: str
    direction: str
    scope_keys: tuple[str, ...]
    evidence_summary: tuple[tuple[str, str], ...]
    batch_hash: str
    target_case_id: str | None = None
    oa_attachment_bindings: tuple[tuple[str, str], ...] = ()
    relation_mode: str = "manual_confirmed"

    @property
    def idempotency_key(self) -> str:
        return f"workbench:formal-relation:{self.rule_version}:{self.relation_fingerprint}"


@dataclass(frozen=True, slots=True)
class FormalRelationMatchResult:
    plans: tuple[FormalRelationPlan, ...] = ()
    ambiguous_component_count: int = 0
    resource_limited_component_count: int = 0
    unsafe_component_count: int = 0
    preserved_active_count: int = 0
    blocked_reason_counts: tuple[tuple[str, int], ...] = ()


@dataclass(slots=True)
class _Budget:
    limits: FormalRelationSearchLimits
    states: int = 0
    working_bytes: int = 0

    def consume(self, *, states: int = 1, working_bytes: int = 0) -> None:
        self.states += states
        self.working_bytes += working_bytes
        if (
            self.states > self.limits.max_search_states
            or self.states > self.limits.max_deadline_states
            or self.working_bytes > self.limits.max_working_bytes
        ):
            raise _ResourceLimited


class _ResourceLimited(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Edge:
    left: MemberKey
    right: MemberKey
    evidence_kind: str
    explicit: bool
    original: bool


class WorkbenchFreeMatchingEngine:
    """Pure deterministic matcher. It never reads or writes I/O and emits only formal plans."""

    def plan_relations(
        self,
        batch: FormalRelationFactBatch,
        limits: FormalRelationSearchLimits | None = None,
    ) -> FormalRelationMatchResult:
        if not isinstance(batch, FormalRelationFactBatch):
            raise TypeError("batch must be a FormalRelationFactBatch.")
        limits = limits or FormalRelationSearchLimits()
        budget = _Budget(limits)
        blocked: dict[str, int] = {}
        active_by_member = {
            member_key: anchor
            for anchor in batch.active_relations
            for member_key in anchor.member_keys
        }
        available = [fact for fact in batch.facts if fact.member_key not in active_by_member]
        preserved_active_count = len(batch.active_relations)
        if not available:
            return FormalRelationMatchResult(preserved_active_count=preserved_active_count)

        reversal_plans, reversal_claimed, reversal_ambiguous = self._output_invoice_reversal_plans(
            batch=batch,
            available=available,
        )
        if reversal_ambiguous:
            blocked["ambiguous_output_invoice_reversal"] = reversal_ambiguous

        facts_by_key = {fact.member_key: fact for fact in batch.facts}
        singleton_plans, singleton_claimed = self._exact_singleton_active_extension_plans(
            batch=batch,
            facts_by_key=facts_by_key,
            eligible_new_facts=[
                fact
                for fact in available
                if fact.reversal_polarity != "red" and fact.member_key not in reversal_claimed
            ],
        )
        try:
            budget.consume(working_bytes=len(available) * 512)
            edges = self._build_edges(batch.facts, budget)
        except _ResourceLimited:
            blocked["resource_limited"] = 1
            return FormalRelationMatchResult(
                plans=tuple(
                    sorted(
                        [*reversal_plans, *singleton_plans],
                        key=lambda plan: plan.relation_fingerprint,
                    )
                ),
                ambiguous_component_count=reversal_ambiguous,
                resource_limited_component_count=1,
                preserved_active_count=preserved_active_count,
                blocked_reason_counts=tuple(sorted(blocked.items())),
            )

        available_keys = {
            fact.member_key
            for fact in available
            if fact.reversal_polarity != "red"
        } - reversal_claimed - singleton_claimed
        (
            extension_plans,
            extension_claimed,
            extension_ambiguous,
            extension_resource_limited,
        ) = self._active_extension_plans(
            batch=batch,
            edges=edges,
            facts_by_key=facts_by_key,
            active_by_member=active_by_member,
            eligible_new_keys=available_keys,
            budget=budget,
            preplanned_case_ids={
                plan.target_case_id
                for plan in singleton_plans
                if plan.target_case_id is not None
            },
        )
        if extension_ambiguous:
            blocked["ambiguous_active_extension"] = extension_ambiguous
        if extension_resource_limited:
            blocked["resource_limited"] = extension_resource_limited

        graph_edges = [
            edge
            for edge in edges
            if edge.left in available_keys - extension_claimed and edge.right in available_keys - extension_claimed
        ]
        components = self._components(available_keys - extension_claimed, graph_edges)
        plans = [*reversal_plans, *singleton_plans, *extension_plans]
        ambiguous_components = extension_ambiguous + reversal_ambiguous
        resource_limited_components = extension_resource_limited
        unsafe_components = 0
        for component in components:
            if len(component) < 2:
                continue
            component_edges = [edge for edge in graph_edges if edge.left in component and edge.right in component]
            try:
                component_plans, outcome = self._plans_for_component(
                    batch=batch,
                    member_keys=component,
                    edges=component_edges,
                    facts_by_key=facts_by_key,
                    budget=budget,
                )
            except _ResourceLimited:
                resource_limited_components += 1
                blocked["resource_limited"] = blocked.get("resource_limited", 0) + 1
                continue
            if outcome == "ambiguous":
                ambiguous_components += 1
                blocked["ambiguous_partition"] = blocked.get("ambiguous_partition", 0) + 1
            elif outcome == "unsafe":
                unsafe_components += 1
                blocked["unsafe_component"] = blocked.get("unsafe_component", 0) + 1
            else:
                plans.extend(component_plans)

        plans = sorted(plans, key=lambda plan: plan.relation_fingerprint)
        return FormalRelationMatchResult(
            plans=tuple(plans),
            ambiguous_component_count=ambiguous_components,
            resource_limited_component_count=resource_limited_components,
            unsafe_component_count=unsafe_components,
            preserved_active_count=preserved_active_count,
            blocked_reason_counts=tuple(sorted(blocked.items())),
        )

    def _output_invoice_reversal_plans(
        self,
        *,
        batch: FormalRelationFactBatch,
        available: list[FormalRelationFact],
    ) -> tuple[list[FormalRelationPlan], set[MemberKey], int]:
        facts_by_key = {fact.member_key: fact for fact in batch.facts}
        groups: dict[tuple[str, ...], list[FormalRelationFact]] = {}
        for fact in available:
            if fact.reversal_key is not None:
                groups.setdefault(fact.reversal_key, []).append(fact)

        plans: list[FormalRelationPlan] = []
        claimed: set[MemberKey] = set()
        ambiguous = 0
        for facts in groups.values():
            blue = [fact for fact in facts if fact.reversal_polarity == "blue"]
            red = [fact for fact in facts if fact.reversal_polarity == "red"]
            if not blue or not red:
                continue
            if len(blue) != 1 or len(red) != 1:
                ambiguous += 1
                continue
            blue_fact, red_fact = blue[0], red[0]
            if (
                blue_fact.fact_date is None
                or red_fact.fact_date is None
                or red_fact.fact_date < blue_fact.fact_date
            ):
                continue
            members = (blue_fact.member_key, red_fact.member_key)
            fingerprint = relation_fingerprint(members)
            if fingerprint in batch.withdrawal_fingerprints:
                continue
            plans.append(
                self._plan(
                    batch=batch,
                    member_keys=members,
                    facts_by_key=facts_by_key,
                    rule_code="output_invoice_exact_reversal",
                    evidence_kinds={"output_invoice_reversal"},
                    relation_mode="output_invoice_reversal",
                    evidence_summary_extra=(
                        ("blue_invoice_identity", blue_fact.canonical_object_identity),
                        ("red_invoice_identity", red_fact.canonical_object_identity),
                    ),
                )
            )
            claimed.update(members)
        return plans, claimed, ambiguous

    def _build_edges(self, facts: tuple[FormalRelationFact, ...], budget: _Budget) -> list[_Edge]:
        facts_by_key = {fact.member_key: fact for fact in facts}
        edges: dict[tuple[MemberKey, MemberKey, str], _Edge] = {}
        shared_references: dict[tuple[str, str], list[FormalRelationFact]] = {}
        for fact in facts:
            for reference in fact.references:
                budget.consume()
                target = reference.target_member_key
                if target is not None and target in facts_by_key and target != fact.member_key:
                    self._add_edge(
                        edges,
                        fact.member_key,
                        target,
                        evidence_kind=reference.kind,
                        explicit=True,
                        original=reference.original or reference.kind == "original_reference",
                    )
                else:
                    shared_references.setdefault((reference.kind, reference.value), []).append(fact)

        for (kind, _value), reference_facts in sorted(shared_references.items()):
            by_type: dict[str, list[FormalRelationFact]] = {}
            for fact in reference_facts:
                by_type.setdefault(fact.row_type, []).append(fact)
            if len(by_type) < 2 or any(len(items) != 1 for items in by_type.values()):
                continue
            unique_facts = sorted(reference_facts, key=lambda fact: _member_sort_key(fact.member_key))
            for index, left in enumerate(unique_facts):
                for right in unique_facts[index + 1 :]:
                    budget.consume()
                    self._add_edge(
                        edges,
                        left.member_key,
                        right.member_key,
                        evidence_kind=kind,
                        explicit=True,
                        original=any(ref.original or ref.kind == "original_reference" for ref in (*left.references, *right.references)),
                    )

        evidence_buckets: dict[
            tuple[str, str, str, str],
            list[FormalRelationFact],
        ] = {}
        for fact in facts:
            for evidence_kind, evidence_value in fact.evidence_keys:
                budget.consume()
                evidence_buckets.setdefault(
                    (fact.currency, fact.direction, evidence_kind, evidence_value),
                    [],
                ).append(fact)

        composite_pairs: dict[tuple[MemberKey, MemberKey], tuple[str, str]] = {}
        for (_currency, _direction, evidence_kind, evidence_value), bucket in evidence_buckets.items():
            by_row_type: dict[str, list[FormalRelationFact]] = {}
            for fact in bucket:
                if fact.fact_date is not None and fact.amount_minor > 0:
                    by_row_type.setdefault(fact.row_type, []).append(fact)
            ordered_row_types = sorted(by_row_type, key=ROW_TYPE_ORDER.__getitem__)
            window_days = 30 if evidence_kind == "employee_reimbursement_payee" else 365
            for type_index, left_type in enumerate(ordered_row_types):
                left_facts = sorted(
                    by_row_type[left_type],
                    key=lambda fact: (fact.fact_date, _member_sort_key(fact.member_key)),
                )
                for right_type in ordered_row_types[type_index + 1 :]:
                    right_facts = sorted(
                        by_row_type[right_type],
                        key=lambda fact: (fact.fact_date, _member_sort_key(fact.member_key)),
                    )
                    for left in left_facts:
                        for right in right_facts:
                            date_delta = (right.fact_date - left.fact_date).days
                            if date_delta < -window_days:
                                continue
                            if date_delta > window_days:
                                break
                            budget.consume()
                            pair = tuple(sorted((left.member_key, right.member_key), key=_member_sort_key))
                            evidence = (evidence_kind, evidence_value)
                            prior = composite_pairs.get(pair)
                            if prior is None or evidence < prior:
                                composite_pairs[pair] = evidence

        budget.consume(working_bytes=len(composite_pairs) * 96)
        for (left, right), (evidence_kind, _value) in sorted(
            composite_pairs.items(),
            key=lambda item: (_member_sort_key(item[0][0]), _member_sort_key(item[0][1]), item[1]),
        ):
            self._add_edge(
                edges,
                left,
                right,
                evidence_kind=evidence_kind,
                explicit=False,
                original=False,
            )
        budget.consume(working_bytes=len(edges) * 192)
        return sorted(edges.values(), key=lambda edge: (_member_sort_key(edge.left), _member_sort_key(edge.right), edge.evidence_kind))

    @staticmethod
    def _add_edge(
        edges: dict[tuple[MemberKey, MemberKey, str], _Edge],
        left: MemberKey,
        right: MemberKey,
        *,
        evidence_kind: str,
        explicit: bool,
        original: bool,
    ) -> None:
        ordered_left, ordered_right = sorted((left, right), key=_member_sort_key)
        key = (ordered_left, ordered_right, evidence_kind)
        edges[key] = _Edge(ordered_left, ordered_right, evidence_kind, explicit, original)

    def _active_extension_plans(
        self,
        *,
        batch: FormalRelationFactBatch,
        edges: list[_Edge],
        facts_by_key: dict[MemberKey, FormalRelationFact],
        active_by_member: dict[MemberKey, ActiveFormalRelationAnchor],
        eligible_new_keys: set[MemberKey],
        budget: _Budget,
        preplanned_case_ids: set[str],
    ) -> tuple[list[FormalRelationPlan], set[MemberKey], int, int]:
        new_members_by_case: dict[str, set[MemberKey]] = {}
        ambiguous_members: set[MemberKey] = set()
        cases_by_new_member: dict[MemberKey, set[str]] = {}
        for edge in edges:
            if not edge.explicit:
                continue
            left_anchor = active_by_member.get(edge.left)
            right_anchor = active_by_member.get(edge.right)
            if bool(left_anchor) == bool(right_anchor):
                continue
            anchor = left_anchor or right_anchor
            new_member = edge.right if left_anchor else edge.left
            if anchor is None or anchor.case_id in preplanned_case_ids:
                continue
            cases_by_new_member.setdefault(new_member, set()).add(anchor.case_id)
        for member_key, case_ids in cases_by_new_member.items():
            if len(case_ids) != 1:
                ambiguous_members.add(member_key)
                continue
            new_members_by_case.setdefault(next(iter(case_ids)), set()).add(member_key)

        plans: list[FormalRelationPlan] = []
        claimed: set[MemberKey] = set(ambiguous_members)
        anchors = {anchor.case_id: anchor for anchor in batch.active_relations}
        for case_id, new_members in sorted(new_members_by_case.items()):
            if new_members & ambiguous_members:
                continue
            anchor = anchors[case_id]
            full_members = tuple(sorted(set(anchor.member_keys).union(new_members), key=_member_sort_key))
            fingerprint = relation_fingerprint(full_members)
            if fingerprint in batch.withdrawal_fingerprints:
                claimed.update(new_members)
                continue
            plan = self._plan(
                batch=batch,
                member_keys=full_members,
                facts_by_key=facts_by_key,
                rule_code="explicit_reference_extension",
                evidence_kinds={"explicit_reference"},
                target_case_id=case_id,
            )
            plans.append(plan)
            claimed.update(new_members)

        composite_candidates: dict[str, tuple[frozenset[MemberKey], set[str]]] = {}
        ambiguous_cases: set[str] = set()
        ambiguous_composite_members: set[MemberKey] = set()
        resource_limited_members: set[MemberKey] = set()
        resource_limited_cases = 0
        eligible = eligible_new_keys - claimed
        composite_adjacency: dict[MemberKey, set[MemberKey]] = {}
        for edge in edges:
            if edge.explicit:
                continue
            composite_adjacency.setdefault(edge.left, set()).add(edge.right)
            composite_adjacency.setdefault(edge.right, set()).add(edge.left)
        for case_id, anchor in sorted(anchors.items()):
            anchor_members = set(anchor.member_keys)
            if (
                case_id in preplanned_case_ids
                or case_id in new_members_by_case
                or {row_type for row_type, _identity in anchor_members} == MATCHABLE_ROW_TYPES
            ):
                continue
            if not anchor_members.issubset(facts_by_key):
                continue

            missing_row_types = MATCHABLE_ROW_TYPES - {row_type for row_type, _identity in anchor_members}
            allowed_members = anchor_members | {
                member for member in eligible if member[0] in missing_row_types
            }
            reachable = set(anchor_members)
            pending = list(anchor_members)
            while pending:
                current = pending.pop()
                for neighbor in (composite_adjacency.get(current, set()) & allowed_members) - reachable:
                    reachable.add(neighbor)
                    pending.append(neighbor)
            ordered_new = tuple(sorted(reachable - anchor_members, key=_member_sort_key))
            if not ordered_new:
                continue
            case_budget = _Budget(budget.limits)
            candidates: dict[frozenset[MemberKey], set[str]] = {}
            try:
                case_budget.consume(working_bytes=len(ordered_new) * 128)
                remaining_states = min(
                    case_budget.limits.max_search_states,
                    case_budget.limits.max_deadline_states,
                ) - case_budget.states
                if remaining_states < 1 or len(ordered_new) > (remaining_states + 1).bit_length() - 1:
                    raise _ResourceLimited

                for mask in range(1, 1 << len(ordered_new)):
                    case_budget.consume()
                    new_members = frozenset(
                        ordered_new[index]
                        for index in range(len(ordered_new))
                        if mask & (1 << index)
                    )
                    if not ({row_type for row_type, _identity in new_members} & missing_row_types):
                        continue
                    full_members = anchor_members | set(new_members)
                    selected_edges = [
                        edge
                        for edge in edges
                        if edge.left in full_members and edge.right in full_members
                    ]
                    if not self._is_connected(full_members, selected_edges):
                        continue
                    if not self._safe_active_extension_closure(
                        anchor_facts=[facts_by_key[member] for member in anchor_members],
                        new_facts=[facts_by_key[member] for member in new_members],
                        edges=selected_edges,
                    ):
                        continue
                    candidates[new_members] = {edge.evidence_kind for edge in selected_edges}
            except _ResourceLimited:
                resource_limited_cases += 1
                resource_limited_members.update(ordered_new)
                continue

            if len(candidates) != 1:
                if candidates:
                    ambiguous_cases.add(case_id)
                    ambiguous_composite_members.update(
                        member for candidate in candidates for member in candidate
                    )
                continue
            new_members, evidence_kinds = next(iter(candidates.items()))
            composite_candidates[case_id] = (new_members, evidence_kinds)

        cases_by_new_member: dict[MemberKey, set[str]] = {}
        for case_id, (new_members, _evidence_kinds) in composite_candidates.items():
            for member in new_members:
                cases_by_new_member.setdefault(member, set()).add(case_id)
        for case_ids in cases_by_new_member.values():
            if len(case_ids) > 1:
                ambiguous_cases.update(case_ids)
        for case_id, (new_members, _evidence_kinds) in composite_candidates.items():
            if new_members & (ambiguous_composite_members | resource_limited_members):
                ambiguous_cases.add(case_id)
        claimed.update(ambiguous_composite_members)
        claimed.update(resource_limited_members)

        for case_id, (new_members, evidence_kinds) in sorted(composite_candidates.items()):
            if case_id in ambiguous_cases:
                claimed.update(new_members)
                continue
            anchor = anchors[case_id]
            full_members = tuple(sorted(set(anchor.member_keys) | set(new_members), key=_member_sort_key))
            if relation_fingerprint(full_members) in batch.withdrawal_fingerprints:
                claimed.update(new_members)
                continue
            plans.append(
                self._plan(
                    batch=batch,
                    member_keys=full_members,
                    facts_by_key=facts_by_key,
                    rule_code="strong_evidence_exact_extension",
                    evidence_kinds=evidence_kinds,
                    target_case_id=case_id,
                )
            )
            claimed.update(new_members)
        return (
            plans,
            claimed,
            len(ambiguous_members) + len(ambiguous_cases),
            resource_limited_cases,
        )

    def _exact_singleton_active_extension_plans(
        self,
        *,
        batch: FormalRelationFactBatch,
        facts_by_key: dict[MemberKey, FormalRelationFact],
        eligible_new_facts: list[FormalRelationFact],
    ) -> tuple[list[FormalRelationPlan], set[MemberKey]]:
        candidates_by_amount: dict[tuple[str, str, str, int], list[FormalRelationFact]] = {}
        for fact in eligible_new_facts:
            if fact.amount_minor > 0 and fact.fact_date is not None:
                candidates_by_amount.setdefault(
                    (fact.row_type, fact.currency, fact.direction, fact.amount_minor),
                    [],
                ).append(fact)

        candidates_by_case: dict[str, tuple[FormalRelationFact, set[str]]] = {}
        for anchor in batch.active_relations:
            anchor_facts = [facts_by_key[key] for key in anchor.member_keys if key in facts_by_key]
            if len(anchor_facts) != len(anchor.member_keys):
                continue
            missing_row_types = MATCHABLE_ROW_TYPES - {fact.row_type for fact in anchor_facts}
            if len(missing_row_types) != 1 or any(fact.amount_minor <= 0 for fact in anchor_facts):
                continue
            currencies = {fact.currency for fact in anchor_facts}
            directions = {fact.direction for fact in anchor_facts}
            if len(currencies) != 1 or len(directions) != 1:
                continue

            missing_row_type = next(iter(missing_row_types))
            amount_totals: dict[str, int] = {}
            for fact in anchor_facts:
                amount_totals[fact.row_type] = amount_totals.get(fact.row_type, 0) + fact.amount_minor
            matching: dict[MemberKey, tuple[FormalRelationFact, set[str]]] = {}
            for amount_minor in set(amount_totals.values()):
                for candidate in candidates_by_amount.get(
                    (missing_row_type, next(iter(currencies)), next(iter(directions)), amount_minor),
                    (),
                ):
                    evidence_kinds = self._shared_composite_evidence_kinds(candidate, anchor_facts)
                    if evidence_kinds:
                        matching[candidate.member_key] = (candidate, evidence_kinds)
            if len(matching) == 1:
                candidates_by_case[anchor.case_id] = next(iter(matching.values()))

        cases_by_member: dict[MemberKey, set[str]] = {}
        for case_id, (candidate, _evidence_kinds) in candidates_by_case.items():
            cases_by_member.setdefault(candidate.member_key, set()).add(case_id)

        plans: list[FormalRelationPlan] = []
        claimed: set[MemberKey] = set()
        anchors = {anchor.case_id: anchor for anchor in batch.active_relations}
        for case_id, (candidate, evidence_kinds) in sorted(candidates_by_case.items()):
            if len(cases_by_member[candidate.member_key]) != 1:
                continue
            full_members = tuple(
                sorted((*anchors[case_id].member_keys, candidate.member_key), key=_member_sort_key)
            )
            if relation_fingerprint(full_members) in batch.withdrawal_fingerprints:
                claimed.add(candidate.member_key)
                continue
            plans.append(
                self._plan(
                    batch=batch,
                    member_keys=full_members,
                    facts_by_key=facts_by_key,
                    rule_code="strong_evidence_exact_singleton_extension",
                    evidence_kinds=evidence_kinds,
                    target_case_id=case_id,
                )
            )
            claimed.add(candidate.member_key)
        return plans, claimed

    @staticmethod
    def _shared_composite_evidence_kinds(
        candidate: FormalRelationFact,
        anchor_facts: list[FormalRelationFact],
    ) -> set[str]:
        candidate_evidence = set(candidate.evidence_keys)
        evidence_kinds: set[str] = set()
        for anchor_fact in anchor_facts:
            if candidate.fact_date is None or anchor_fact.fact_date is None:
                continue
            for evidence_kind, _evidence_value in candidate_evidence.intersection(
                anchor_fact.evidence_keys
            ):
                window_days = 30 if evidence_kind == "employee_reimbursement_payee" else 365
                if abs((candidate.fact_date - anchor_fact.fact_date).days) <= window_days:
                    evidence_kinds.add(evidence_kind)
        return evidence_kinds

    def _plans_for_component(
        self,
        *,
        batch: FormalRelationFactBatch,
        member_keys: set[MemberKey],
        edges: list[_Edge],
        facts_by_key: dict[MemberKey, FormalRelationFact],
        budget: _Budget,
    ) -> tuple[list[FormalRelationPlan], str]:
        ordered = tuple(sorted(member_keys, key=_member_sort_key))
        explicit_only = bool(edges) and all(edge.explicit for edge in edges)
        if explicit_only and self._is_connected(set(ordered), edges):
            fingerprint = relation_fingerprint(ordered)
            evidence_kinds = {edge.evidence_kind for edge in edges}
            if fingerprint in batch.withdrawal_fingerprints and not _is_immutable_oa_attachment_relation(
                ordered,
                evidence_kinds,
            ):
                return [], "unsafe"
            return [
                self._plan(
                    batch=batch,
                    member_keys=ordered,
                    facts_by_key=facts_by_key,
                    rule_code="explicit_unique_reference",
                    evidence_kinds=evidence_kinds,
                )
            ], "ok"

        candidate_sets: list[frozenset[MemberKey]] = []
        candidate_evidence: dict[frozenset[MemberKey], set[str]] = {}
        remaining_states = min(
            budget.limits.max_search_states,
            budget.limits.max_deadline_states,
        ) - budget.states
        if remaining_states < 1 or len(ordered) > (remaining_states + 1).bit_length() - 1:
            raise _ResourceLimited
        total_masks = 1 << len(ordered)
        for mask in range(1, total_masks):
            budget.consume()
            if mask.bit_count() < 2:
                continue
            selected = frozenset(ordered[index] for index in range(len(ordered)) if mask & (1 << index))
            row_types = {row_type for row_type, _identity in selected}
            if len(row_types) < 2:
                continue
            selected_edges = [edge for edge in edges if edge.left in selected and edge.right in selected]
            if not self._is_connected(set(selected), selected_edges):
                continue
            selected_facts = [facts_by_key[key] for key in selected]
            if not self._safe_exact_closure(selected_facts, selected_edges):
                continue
            candidate_sets.append(selected)
            candidate_evidence[selected] = {edge.evidence_kind for edge in selected_edges}

        if not candidate_sets:
            return [], "unsafe"
        max_panes = max(len({row_type for row_type, _identity in candidate}) for candidate in candidate_sets)
        candidates = [
            candidate
            for candidate in candidate_sets
            if len({row_type for row_type, _identity in candidate}) == max_panes
        ]
        unique_candidates = sorted(set(candidates), key=lambda item: tuple(_member_sort_key(key) for key in sorted(item, key=_member_sort_key)))
        overlapping_members = {
            member
            for index, candidate in enumerate(unique_candidates)
            for other in unique_candidates[index + 1 :]
            for member in candidate.intersection(other)
        }
        accepted = [candidate for candidate in unique_candidates if not candidate.intersection(overlapping_members)]
        if not accepted:
            return [], "ambiguous"
        plans: list[FormalRelationPlan] = []
        for candidate in accepted:
            fingerprint = relation_fingerprint(candidate)
            evidence_kinds = candidate_evidence[candidate]
            if fingerprint in batch.withdrawal_fingerprints and not _is_immutable_oa_attachment_relation(
                candidate,
                evidence_kinds,
            ):
                continue
            plans.append(
                self._plan(
                    batch=batch,
                    member_keys=tuple(sorted(candidate, key=_member_sort_key)),
                    facts_by_key=facts_by_key,
                    rule_code="strong_evidence_exact_closure",
                    evidence_kinds=evidence_kinds,
                )
            )
        return plans, "ok" if plans else "unsafe"

    @staticmethod
    def _safe_exact_closure(facts: list[FormalRelationFact], edges: list[_Edge]) -> bool:
        if not facts or len({fact.currency for fact in facts}) != 1 or len({fact.direction for fact in facts}) != 1:
            return False
        if any(fact.amount_minor <= 0 for fact in facts):
            return False
        totals: dict[str, int] = {}
        for fact in facts:
            totals[fact.row_type] = totals.get(fact.row_type, 0) + fact.amount_minor
        if len(totals) < 2 or len(set(totals.values())) != 1:
            return False
        degree = {fact.member_key: 0 for fact in facts}
        for edge in edges:
            degree[edge.left] += 1
            degree[edge.right] += 1
        return all(value > 0 for value in degree.values())

    @classmethod
    def _safe_active_extension_closure(
        cls,
        *,
        anchor_facts: list[FormalRelationFact],
        new_facts: list[FormalRelationFact],
        edges: list[_Edge],
    ) -> bool:
        facts = [*anchor_facts, *new_facts]
        if cls._safe_exact_closure(facts, edges):
            return True
        if (
            not anchor_facts
            or not new_facts
            or len({fact.row_type for fact in new_facts}) != 1
            or len({fact.currency for fact in facts}) != 1
            or len({fact.direction for fact in facts}) != 1
            or any(fact.amount_minor <= 0 for fact in facts)
        ):
            return False
        new_total = sum(fact.amount_minor for fact in new_facts)
        anchor_totals: dict[str, int] = {}
        for fact in anchor_facts:
            anchor_totals[fact.row_type] = anchor_totals.get(fact.row_type, 0) + fact.amount_minor
        if new_total not in anchor_totals.values():
            return False
        degree = {fact.member_key: 0 for fact in facts}
        for edge in edges:
            degree[edge.left] += 1
            degree[edge.right] += 1
        return all(value > 0 for value in degree.values())

    @staticmethod
    def _components(member_keys: set[MemberKey], edges: list[_Edge]) -> list[set[MemberKey]]:
        adjacency = {member_key: set() for member_key in member_keys}
        for edge in edges:
            if edge.left in adjacency and edge.right in adjacency:
                adjacency[edge.left].add(edge.right)
                adjacency[edge.right].add(edge.left)
        components: list[set[MemberKey]] = []
        remaining = set(member_keys)
        while remaining:
            root = min(remaining, key=_member_sort_key)
            pending = [root]
            component: set[MemberKey] = set()
            while pending:
                current = pending.pop()
                if current in component:
                    continue
                component.add(current)
                pending.extend(sorted(adjacency[current] - component, key=_member_sort_key, reverse=True))
            remaining.difference_update(component)
            components.append(component)
        return components

    @staticmethod
    def _is_connected(member_keys: set[MemberKey], edges: list[_Edge]) -> bool:
        if len(member_keys) < 2:
            return False
        adjacency = {member_key: set() for member_key in member_keys}
        for edge in edges:
            if edge.left in adjacency and edge.right in adjacency:
                adjacency[edge.left].add(edge.right)
                adjacency[edge.right].add(edge.left)
        if any(not neighbors for neighbors in adjacency.values()):
            return False
        visited: set[MemberKey] = set()
        pending = [min(member_keys, key=_member_sort_key)]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
        return visited == member_keys

    def _plan(
        self,
        *,
        batch: FormalRelationFactBatch,
        member_keys: tuple[MemberKey, ...],
        facts_by_key: dict[MemberKey, FormalRelationFact],
        rule_code: str,
        evidence_kinds: set[str],
        target_case_id: str | None = None,
        relation_mode: str = "manual_confirmed",
        evidence_summary_extra: tuple[tuple[str, str], ...] = (),
    ) -> FormalRelationPlan:
        members = tuple(sorted(set(member_keys), key=_member_sort_key))
        fingerprint = relation_fingerprint(members)
        member_facts = [facts_by_key[key] for key in members if key in facts_by_key]
        row_ids_by_key = {fact.member_key: fact.row_id for fact in member_facts}
        if target_case_id:
            anchor = next(anchor for anchor in batch.active_relations if anchor.case_id == target_case_id)
            for member_key in anchor.member_keys:
                row_ids_by_key.setdefault(member_key, member_key[1])
        totals: dict[str, int] = {}
        for fact in member_facts:
            totals[fact.row_type] = totals.get(fact.row_type, 0) + fact.amount_minor
        amount_minor = next(iter(totals.values())) if totals and len(set(totals.values())) == 1 else 0
        scope_keys = {
            fact.fact_date.strftime("%Y-%m")
            for fact in member_facts
            if fact.fact_date is not None
        }
        if not scope_keys:
            scope_keys.add("all")
        evidence_summary = (
            ("evidence_kinds", ",".join(sorted(evidence_kinds))),
            ("member_count", str(len(members))),
            ("pane_count", str(len({row_type for row_type, _identity in members}))),
            *evidence_summary_extra,
        )
        attachment_bindings = {
            (row_ids_by_key[target], fact.row_id)
            for fact in member_facts
            if fact.row_type == "invoice"
            for reference in fact.references
            if reference.kind == "attachment_source"
            and (target := reference.target_member_key) in members
            and target in row_ids_by_key
        }
        return FormalRelationPlan(
            case_id=target_case_id or f"CASE-AUTO-{fingerprint[:20].upper()}",
            member_keys=members,
            row_ids=tuple(row_ids_by_key[key] for key in members),
            row_types=tuple(row_type for row_type, _identity in members),
            relation_fingerprint=fingerprint,
            rule_code=rule_code,
            rule_version=RULE_VERSION,
            amount_minor=amount_minor,
            currency=member_facts[0].currency if member_facts else "CNY",
            direction=member_facts[0].direction if member_facts else "expenditure",
            scope_keys=tuple(sorted(scope_keys)),
            evidence_summary=evidence_summary,
            batch_hash=batch.batch_hash,
            target_case_id=target_case_id,
            oa_attachment_bindings=tuple(sorted(attachment_bindings)),
            relation_mode=relation_mode,
        )


def _is_immutable_oa_attachment_relation(
    member_keys: Iterable[MemberKey],
    evidence_kinds: set[str],
) -> bool:
    row_types = {row_type for row_type, _identity in member_keys}
    return row_types == {"oa", "invoice"} and evidence_kinds == {"attachment_source"}


def _member_sort_key(member_key: MemberKey) -> tuple[int, str]:
    return ROW_TYPE_ORDER[member_key[0]], member_key[1]


def _fact_batch_hash(
    facts: tuple[FormalRelationFact, ...],
    active_relations: tuple[ActiveFormalRelationAnchor, ...],
    withdrawals: frozenset[str],
    versions: tuple[tuple[str, str], ...],
) -> str:
    payload = {
        "facts": [
            {
                "member": fact.member_key,
                "row_id": fact.row_id,
                "amount_minor": fact.amount_minor,
                "currency": fact.currency,
                "direction": fact.direction,
                "fact_date": fact.fact_date.isoformat() if fact.fact_date else None,
                "evidence_keys": fact.evidence_keys,
                "references": [
                    (
                        reference.kind,
                        reference.value,
                        reference.target_row_type,
                        reference.target_identity,
                        reference.original,
                    )
                    for reference in fact.references
                ],
                "source_version": fact.source_version,
            }
            for fact in facts
        ],
        "active": [(anchor.case_id, anchor.member_keys) for anchor in active_relations],
        "withdrawals": sorted(withdrawals),
        "versions": versions,
    }
    return sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()
