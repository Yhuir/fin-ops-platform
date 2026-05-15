from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fin_ops_platform.services.etc_reconciliation_models import (
    EtcReconciliationTask,
    EtcReconciliationTaskStatus,
    ExpectedEtcInvoiceRequirement,
)
from fin_ops_platform.services.etc_service import ParsedEtcXml, UploadedEtcZipFile, parse_etc_xml


class StaleReconciliationPreviewError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EtcZipFilterItem:
    file_name: str
    invoice_number: str | None
    filter_status: str
    requirement_id: str | None = None
    message: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "fileName": self.file_name,
            "invoiceNumber": self.invoice_number,
            "filterStatus": self.filter_status,
            "requirementId": self.requirement_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class EtcZipFilterPreview:
    task_id: str
    task_version: int
    confirmed_item_set_hash: str
    allowed_invoice_numbers: list[str]
    items: list[EtcZipFilterItem]
    blocking_issues: list[dict[str, object]] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "taskVersion": self.task_version,
            "confirmedItemSetHash": self.confirmed_item_set_hash,
            "allowedInvoiceNumbers": self.allowed_invoice_numbers,
            "items": [item.to_payload() for item in self.items],
            "blockingIssues": list(self.blocking_issues),
        }


@dataclass(frozen=True, slots=True)
class _InvoiceCandidate:
    file_name: str
    invoice: ParsedEtcXml

    @property
    def invoice_number(self) -> str:
        return self.invoice.invoice_number


@dataclass(frozen=True, slots=True)
class _RequirementMatch:
    candidates: tuple[_InvoiceCandidate, ...]
    business_score: tuple[object, ...] = ()
    deterministic_score: tuple[object, ...] = ()
    ambiguous_candidates: tuple[_InvoiceCandidate, ...] = ()
    covered_requirement_ids: tuple[str, ...] = ()

    @property
    def invoice_numbers(self) -> tuple[str, ...]:
        return tuple(candidate.invoice_number for candidate in self.candidates)

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_candidates)


def preview_etc_zip_for_task(*, task: EtcReconciliationTask, uploads: list[UploadedEtcZipFile]) -> EtcZipFilterPreview:
    _assert_ready_task(task)
    parsed_items = _parse_uploads(uploads)
    parsed_candidates = [_InvoiceCandidate(file_name=file_name, invoice=invoice) for file_name, invoice in parsed_items]
    unique_candidates = _unique_invoice_candidates(parsed_items)
    matched_invoice_numbers: set[str] = set()
    items_by_invoice: dict[str, EtcZipFilterItem] = {}
    consumed_requirement_by_invoice: dict[str, str] = {}
    blocking_issues: list[dict[str, object]] = []
    global_matches = _select_global_requirement_matches(task.expected_etc_invoice_requirements, unique_candidates)

    if global_matches is not None:
        for requirement in task.expected_etc_invoice_requirements:
            match = global_matches.get(requirement.requirement_id)
            if match is None:
                continue
            for candidate in match.candidates:
                matched_invoice_numbers.add(candidate.invoice_number)
                consumed_requirement_by_invoice[candidate.invoice_number] = requirement.requirement_id
                items_by_invoice[candidate.invoice_number] = EtcZipFilterItem(
                    file_name=candidate.file_name,
                    invoice_number=candidate.invoice_number,
                    filter_status="included",
                    requirement_id=requirement.requirement_id,
                )
    else:
        blocking_issues = _match_requirements_sequentially(
            requirements=task.expected_etc_invoice_requirements,
            unique_candidates=unique_candidates,
            parsed_candidates=parsed_candidates,
            matched_invoice_numbers=matched_invoice_numbers,
            items_by_invoice=items_by_invoice,
            consumed_requirement_by_invoice=consumed_requirement_by_invoice,
        )

    all_items: list[EtcZipFilterItem] = []
    for file_name, invoice in parsed_items:
        existing = items_by_invoice.get(invoice.invoice_number)
        if existing is not None:
            all_items.append(existing)
            continue
        all_items.append(
            EtcZipFilterItem(
                file_name=file_name,
                invoice_number=invoice.invoice_number,
                filter_status="excluded_extra_zip_invoice",
            )
        )

    return EtcZipFilterPreview(
        task_id=task.task_id,
        task_version=task.version,
        confirmed_item_set_hash=task.confirmed_item_set_hash or "",
        allowed_invoice_numbers=sorted(matched_invoice_numbers),
        items=all_items,
        blocking_issues=blocking_issues,
    )


def _match_requirements_sequentially(
    *,
    requirements: list[ExpectedEtcInvoiceRequirement],
    unique_candidates: list[_InvoiceCandidate],
    parsed_candidates: list[_InvoiceCandidate],
    matched_invoice_numbers: set[str],
    items_by_invoice: dict[str, EtcZipFilterItem],
    consumed_requirement_by_invoice: dict[str, str],
) -> list[dict[str, object]]:
    blocking_issues: list[dict[str, object]] = []
    for requirement in requirements:
        eligible_candidates = [
            candidate
            for candidate in unique_candidates
            if candidate.invoice_number not in consumed_requirement_by_invoice
            and _invoice_satisfies_requirement_context(candidate.invoice, requirement)
        ]
        match = _select_requirement_match(eligible_candidates, requirement)
        if match is None:
            duplicate_match = _select_requirement_match(
                [
                    candidate
                    for candidate in unique_candidates
                    if _invoice_satisfies_requirement_context(candidate.invoice, requirement)
                ],
                requirement,
            )
            duplicate_invoice_numbers = [
                invoice_number
                for invoice_number in (duplicate_match.invoice_numbers if duplicate_match is not None else ())
                if invoice_number in consumed_requirement_by_invoice
            ]
            if duplicate_invoice_numbers:
                duplicate_requirement_ids = list(
                    dict.fromkeys(
                        [
                            *[
                                consumed_requirement_by_invoice[invoice_number]
                                for invoice_number in duplicate_invoice_numbers
                            ],
                            requirement.requirement_id,
                        ]
                    )
                )
                for invoice_number in duplicate_invoice_numbers:
                    matched_invoice_numbers.discard(invoice_number)
                    existing = items_by_invoice.get(invoice_number)
                    items_by_invoice[invoice_number] = EtcZipFilterItem(
                        file_name=existing.file_name if existing is not None else "",
                        invoice_number=invoice_number,
                        filter_status="duplicate_requirement_invoice_match",
                        requirement_id=None,
                    )
                blocking_issues.append(
                    {
                        "error": "duplicate_requirement_invoice_match",
                        "invoiceNumber": duplicate_invoice_numbers[0] if len(duplicate_invoice_numbers) == 1 else None,
                        "invoiceNumbers": duplicate_invoice_numbers,
                        "requirementIds": duplicate_requirement_ids,
                    }
                )
                continue
            blocking_issues.append(
                _missing_requirement_issue(requirement)
            )
            continue
        if match.is_ambiguous:
            numbers = [candidate.invoice_number for candidate in match.ambiguous_candidates]
            blocking_issues.append(
                {
                    "error": "ambiguous_etc_invoice_match",
                    "requirementId": requirement.requirement_id,
                    "invoiceNumbers": numbers,
                }
            )
            for candidate in match.ambiguous_candidates:
                items_by_invoice[candidate.invoice_number] = EtcZipFilterItem(
                    file_name=candidate.file_name,
                    invoice_number=candidate.invoice_number,
                    filter_status="ambiguous_zip_match",
                    requirement_id=requirement.requirement_id,
                )
            continue
        for candidate in match.candidates:
            matched_invoice_numbers.add(candidate.invoice_number)
            consumed_requirement_by_invoice[candidate.invoice_number] = requirement.requirement_id
            items_by_invoice[candidate.invoice_number] = EtcZipFilterItem(
                file_name=candidate.file_name,
                invoice_number=candidate.invoice_number,
                filter_status="included",
                requirement_id=requirement.requirement_id,
            )
    _resolve_missing_requirements_with_package_groups(
        requirements=requirements,
        parsed_candidates=parsed_candidates,
        matched_invoice_numbers=matched_invoice_numbers,
        items_by_invoice=items_by_invoice,
        consumed_requirement_by_invoice=consumed_requirement_by_invoice,
        blocking_issues=blocking_issues,
    )
    return blocking_issues


def _select_global_requirement_matches(
    requirements: list[ExpectedEtcInvoiceRequirement],
    candidates: list[_InvoiceCandidate],
) -> dict[str, _RequirementMatch] | None:
    if not requirements:
        return {}
    options_by_requirement: dict[str, list[_RequirementMatch]] = {
        requirement.requirement_id: _requirement_match_options(candidates, requirement)
        for requirement in requirements
    }
    if any(not options for options in options_by_requirement.values()):
        return None

    ordered_requirements = sorted(
        requirements,
        key=lambda requirement: (len(options_by_requirement[requirement.requirement_id]), requirement.requirement_id),
    )
    solutions: list[dict[str, _RequirementMatch]] = []

    def backtrack(index: int, used_invoice_numbers: set[str], selected: dict[str, _RequirementMatch]) -> None:
        if len(solutions) > 32:
            return
        if index >= len(ordered_requirements):
            solutions.append(dict(selected))
            return
        requirement = ordered_requirements[index]
        for option in options_by_requirement[requirement.requirement_id]:
            option_invoice_numbers = set(option.invoice_numbers)
            if used_invoice_numbers & option_invoice_numbers:
                continue
            selected[requirement.requirement_id] = option
            backtrack(index + 1, used_invoice_numbers | option_invoice_numbers, selected)
            selected.pop(requirement.requirement_id, None)

    backtrack(0, set(), {})
    if not solutions:
        return None
    solutions.sort(key=lambda solution: _global_assignment_score(requirements, solution, deterministic=True))
    best = solutions[0]
    best_business_score = _global_assignment_score(requirements, best, deterministic=False)
    tied = [
        solution
        for solution in solutions
        if _global_assignment_score(requirements, solution, deterministic=False) == best_business_score
    ]
    if len(tied) > 1:
        return None
    return best


def _global_assignment_score(
    requirements: list[ExpectedEtcInvoiceRequirement],
    solution: dict[str, _RequirementMatch],
    *,
    deterministic: bool,
) -> tuple[object, ...]:
    scores = tuple(
        solution[requirement.requirement_id].deterministic_score
        if deterministic
        else solution[requirement.requirement_id].business_score
        for requirement in requirements
    )
    invoice_numbers = tuple(
        invoice_number
        for requirement in requirements
        for invoice_number in solution[requirement.requirement_id].invoice_numbers
    )
    return (*scores, invoice_numbers) if deterministic else scores


def _missing_requirement_issue(requirement: ExpectedEtcInvoiceRequirement) -> dict[str, object]:
    return {
        "error": "missing_required_etc_invoice",
        "requirementId": requirement.requirement_id,
        "transactionAt": requirement.transaction_at,
        "transactionDate": requirement.transaction_at[:10],
        "amount": f"{requirement.amount.quantize(Decimal('0.01')):.2f}",
        "vehiclePlate": requirement.vehicle_plate,
        "invoiceCount": requirement.invoice_count,
        "dateWindowStart": requirement.date_window_start,
        "dateWindowEnd": requirement.date_window_end,
        "creditCardItemId": requirement.credit_card_item_id,
        "ticketRootItemId": requirement.ticket_root_item_id,
    }


def _resolve_missing_requirements_with_package_groups(
    *,
    requirements: list[ExpectedEtcInvoiceRequirement],
    parsed_candidates: list[_InvoiceCandidate],
    matched_invoice_numbers: set[str],
    items_by_invoice: dict[str, EtcZipFilterItem],
    consumed_requirement_by_invoice: dict[str, str],
    blocking_issues: list[dict[str, object]],
) -> None:
    missing_requirement_ids = {
        str(issue.get("requirementId") or "")
        for issue in blocking_issues
        if issue.get("error") == "missing_required_etc_invoice"
    }
    if len(missing_requirement_ids) < 2:
        return
    missing_requirements = [
        requirement
        for requirement in requirements
        if requirement.requirement_id in missing_requirement_ids
    ]
    options = _package_group_match_options(
        requirements=missing_requirements,
        parsed_candidates=[
            candidate
            for candidate in parsed_candidates
            if candidate.invoice_number not in consumed_requirement_by_invoice
        ],
    )
    selected = _select_non_overlapping_group_matches(options)
    if not selected:
        return

    resolved_requirement_ids = {
        requirement_id
        for match in selected
        for requirement_id in match.covered_requirement_ids
    }
    blocking_issues[:] = [
        issue
        for issue in blocking_issues
        if not (
            issue.get("error") == "missing_required_etc_invoice"
            and str(issue.get("requirementId") or "") in resolved_requirement_ids
        )
    ]
    for match in selected:
        requirement_key = "+".join(match.covered_requirement_ids)
        for candidate in match.candidates:
            matched_invoice_numbers.add(candidate.invoice_number)
            consumed_requirement_by_invoice[candidate.invoice_number] = requirement_key
            items_by_invoice[candidate.invoice_number] = EtcZipFilterItem(
                file_name=candidate.file_name,
                invoice_number=candidate.invoice_number,
                filter_status="included",
                requirement_id=requirement_key,
            )


def _package_group_match_options(
    *,
    requirements: list[ExpectedEtcInvoiceRequirement],
    parsed_candidates: list[_InvoiceCandidate],
) -> list[_RequirementMatch]:
    requirements_by_plate_and_day: dict[tuple[str, str], list[ExpectedEtcInvoiceRequirement]] = {}
    for requirement in requirements:
        if not requirement.vehicle_plate:
            continue
        requirements_by_plate_and_day.setdefault(
            (requirement.vehicle_plate, requirement.transaction_at[:10]),
            [],
        ).append(requirement)

    candidates_by_package: dict[str, list[_InvoiceCandidate]] = {}
    for candidate in parsed_candidates:
        candidates_by_package.setdefault(_package_key(candidate.file_name), []).append(candidate)

    options: list[_RequirementMatch] = []
    for grouped_requirements in requirements_by_plate_and_day.values():
        if len(grouped_requirements) < 2:
            continue
        for requirement_group in _contiguous_requirement_groups(grouped_requirements):
            target_cents = sum(_money_cents(requirement.amount) for requirement in requirement_group)
            if target_cents <= 0:
                continue
            for package_key, package_candidates in candidates_by_package.items():
                unique_package_candidates = _unique_package_candidates(package_candidates)
                if not unique_package_candidates:
                    continue
                if any(
                    not _invoice_satisfies_requirement_group_context(candidate.invoice, requirement_group)
                    for candidate in unique_package_candidates
                ):
                    continue
                if sum(_money_cents(candidate.invoice.total_amount) for candidate in unique_package_candidates) != target_cents:
                    continue
                covered_ids = tuple(requirement.requirement_id for requirement in requirement_group)
                business_score = _package_group_business_score(unique_package_candidates, requirement_group, package_key)
                options.append(
                    _RequirementMatch(
                        candidates=tuple(unique_package_candidates),
                        business_score=business_score,
                        deterministic_score=(
                            *business_score,
                            tuple(candidate.file_name for candidate in unique_package_candidates),
                            tuple(candidate.invoice_number for candidate in unique_package_candidates),
                        ),
                        covered_requirement_ids=covered_ids,
                    )
                )
    return sorted(options, key=lambda option: option.deterministic_score)


def _contiguous_requirement_groups(
    requirements: list[ExpectedEtcInvoiceRequirement],
) -> list[tuple[ExpectedEtcInvoiceRequirement, ...]]:
    groups: list[tuple[ExpectedEtcInvoiceRequirement, ...]] = []
    max_group_size = min(len(requirements), 6)
    for start in range(len(requirements)):
        for end in range(start + 2, min(len(requirements), start + max_group_size) + 1):
            groups.append(tuple(requirements[start:end]))
    return groups


def _unique_package_candidates(candidates: list[_InvoiceCandidate]) -> list[_InvoiceCandidate]:
    by_invoice: dict[str, _InvoiceCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: (item.invoice_number, item.file_name)):
        by_invoice.setdefault(candidate.invoice_number, candidate)
    return sorted(by_invoice.values(), key=lambda item: (item.file_name, item.invoice_number))


def _invoice_satisfies_requirement_group_context(
    invoice: ParsedEtcXml,
    requirements: tuple[ExpectedEtcInvoiceRequirement, ...],
) -> bool:
    plates = {requirement.vehicle_plate for requirement in requirements if requirement.vehicle_plate}
    if len(plates) != 1 or (invoice.plate_number or "") not in plates:
        return False
    start = min(requirement.date_window_start for requirement in requirements)
    end = max(requirement.date_window_end for requirement in requirements)
    return any(
        _date_in_window(candidate, start, end)
        for candidate in (invoice.passage_start_date, invoice.passage_end_date, invoice.issue_date)
    )


def _package_group_business_score(
    candidates: list[_InvoiceCandidate],
    requirements: tuple[ExpectedEtcInvoiceRequirement, ...],
    package_key: str,
) -> tuple[object, ...]:
    distance = sum(
        min(_date_distance_days(candidate.invoice, requirement) for requirement in requirements)
        for candidate in candidates
    )
    return (
        2,
        len(requirements),
        len(candidates),
        distance,
        package_key,
    )


def _select_non_overlapping_group_matches(matches: list[_RequirementMatch]) -> list[_RequirementMatch]:
    selected: list[_RequirementMatch] = []
    used_requirement_ids: set[str] = set()
    used_invoice_numbers: set[str] = set()
    for match in sorted(
        matches,
        key=lambda item: (
            -len(item.covered_requirement_ids),
            item.deterministic_score,
        ),
    ):
        requirement_ids = set(match.covered_requirement_ids)
        invoice_numbers = set(match.invoice_numbers)
        if used_requirement_ids & requirement_ids or used_invoice_numbers & invoice_numbers:
            continue
        selected.append(match)
        used_requirement_ids.update(requirement_ids)
        used_invoice_numbers.update(invoice_numbers)
    return selected


def validate_etc_zip_confirm_for_task(*, task: EtcReconciliationTask, preview: EtcZipFilterPreview) -> None:
    if (
        task.task_id != preview.task_id
        or task.version != preview.task_version
        or task.confirmed_item_set_hash != preview.confirmed_item_set_hash
    ):
        raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
    _assert_ready_task(task)
    for issue in preview.blocking_issues:
        error = str(issue.get("error") or "")
        if error in {"missing_required_etc_invoice", "ambiguous_etc_invoice_match", "duplicate_requirement_invoice_match"}:
            raise ValueError(error)


def filter_uploads_by_allowlist(
    *,
    uploads: list[UploadedEtcZipFile],
    allowed_invoice_numbers: list[str],
) -> list[UploadedEtcZipFile]:
    allowed = set(allowed_invoice_numbers)
    if not allowed:
        return []
    filtered: list[UploadedEtcZipFile] = []
    for upload in uploads:
        try:
            entries = _extract_entries(upload.file_name, upload.content)
        except BadZipFile:
            continue
        kept: dict[str, bytes] = {}
        xml_paths_by_invoice: dict[str, str] = {}
        for path, content in entries:
            if _is_xml_entry(path):
                try:
                    invoice = parse_etc_xml(content)
                except Exception:
                    continue
                if invoice.invoice_number in allowed:
                    kept[path] = content
                    xml_paths_by_invoice[invoice.invoice_number] = path
        for path, content in entries:
            if not _is_pdf_entry(path):
                continue
            stem = Path(path).stem.lower()
            for invoice_number, xml_path in xml_paths_by_invoice.items():
                invoice_key = invoice_number.lower()
                if invoice_key in stem or stem in invoice_key or stem == Path(xml_path).stem.lower():
                    kept[path] = content
                    break
        if kept:
            filtered.append(UploadedEtcZipFile(upload.file_name, _zip_entries(kept)))
    return filtered


def _assert_ready_task(task: EtcReconciliationTask) -> None:
    if task.status != EtcReconciliationTaskStatus.READY_FOR_IMPORT:
        raise ValueError("invalid_reconciliation_task_status")
    if not task.confirmed_item_set_hash:
        raise ValueError("stale_reconciliation_task_preview")


def _parse_uploads(uploads: list[UploadedEtcZipFile]) -> list[tuple[str, ParsedEtcXml]]:
    parsed: list[tuple[str, ParsedEtcXml]] = []
    for upload in uploads:
        try:
            entries = _extract_entries(upload.file_name, upload.content)
        except BadZipFile:
            continue
        for path, content in entries:
            if not _is_xml_entry(path):
                continue
            try:
                parsed.append((path, parse_etc_xml(content)))
            except Exception:
                continue
    return parsed


def _unique_invoice_candidates(parsed_items: list[tuple[str, ParsedEtcXml]]) -> list[_InvoiceCandidate]:
    candidates_by_invoice: dict[str, _InvoiceCandidate] = {}
    for file_name, invoice in sorted(parsed_items, key=lambda item: (item[1].invoice_number, item[0])):
        candidates_by_invoice.setdefault(invoice.invoice_number, _InvoiceCandidate(file_name=file_name, invoice=invoice))
    return sorted(candidates_by_invoice.values(), key=lambda candidate: (candidate.file_name, candidate.invoice_number))


def _extract_entries(source_name: str, content: bytes, *, depth: int = 0) -> list[tuple[str, bytes]]:
    return _extract_entries_with_prefix(source_name, content, depth=depth, path_prefix="")


def _extract_entries_with_prefix(
    source_name: str,
    content: bytes,
    *,
    depth: int = 0,
    path_prefix: str = "",
) -> list[tuple[str, bytes]]:
    if depth > 8:
        raise BadZipFile("nested zip depth exceeds limit")
    entries: list[tuple[str, bytes]] = []
    with ZipFile(BytesIO(content)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            file_content = archive.read(info)
            path = f"{path_prefix}{info.filename}"
            if path.lower().endswith(".zip"):
                entries.extend(
                    _extract_entries_with_prefix(
                        source_name,
                        file_content,
                        depth=depth + 1,
                        path_prefix=f"{path}/",
                    )
                )
            else:
                entries.append((path, file_content))
    return entries


def _is_xml_entry(path: str) -> bool:
    return path.lower().endswith(".xml") and not Path(path).name.startswith(".")


def _is_pdf_entry(path: str) -> bool:
    return path.lower().endswith(".pdf") and not Path(path).name.startswith(".")


def _select_requirement_match(
    candidates: list[_InvoiceCandidate],
    requirement: ExpectedEtcInvoiceRequirement,
) -> _RequirementMatch | None:
    options = _requirement_match_options(candidates, requirement)
    if not options:
        return None
    return _select_best_match(options)


def _requirement_match_options(
    candidates: list[_InvoiceCandidate],
    requirement: ExpectedEtcInvoiceRequirement,
) -> list[_RequirementMatch]:
    expected_count = max(int(requirement.invoice_count or 1), 1)
    if expected_count == 1:
        exact_candidates = [
            candidate
            for candidate in candidates
            if _invoice_matches_requirement(candidate.invoice, requirement)
        ]
        return [
            _RequirementMatch(
                candidates=(candidate,),
                business_score=_single_match_business_score(candidate, requirement),
                deterministic_score=_single_match_score(candidate, requirement),
            )
            for candidate in exact_candidates
        ]

    target_cents = _money_cents(requirement.amount)
    amount_candidates = [
        candidate
        for candidate in candidates
        if 0 < _money_cents(candidate.invoice.total_amount) <= target_cents
    ]
    return [
        _RequirementMatch(
            candidates=combination,
            business_score=_combination_match_business_score(combination, requirement),
            deterministic_score=_combination_match_score(combination, requirement),
        )
        for combination in _find_amount_combinations(amount_candidates, target_cents, requirement)
    ]


def _select_best_match(matches: list[_RequirementMatch]) -> _RequirementMatch | None:
    if not matches:
        return None
    matches.sort(key=lambda match: match.deterministic_score)
    best_business_score = matches[0].business_score
    tied = [match for match in matches if match.business_score == best_business_score]
    if len(tied) > 1:
        ambiguous_candidates = tuple(
            {
                candidate.invoice_number: candidate
                for match in tied
                for candidate in match.candidates
            }.values()
        )
        return _RequirementMatch(
            candidates=tied[0].candidates,
            business_score=tied[0].business_score,
            deterministic_score=tied[0].deterministic_score,
            ambiguous_candidates=ambiguous_candidates,
        )
    return matches[0]


def _find_amount_combinations(
    candidates: list[_InvoiceCandidate],
    target_cents: int,
    requirement: ExpectedEtcInvoiceRequirement,
) -> list[tuple[_InvoiceCandidate, ...]]:
    if target_cents <= 0:
        return []
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            _money_cents(candidate.invoice.total_amount),
            _package_key(candidate.file_name),
            _date_distance_days(candidate.invoice, requirement),
            candidate.file_name,
            candidate.invoice_number,
        ),
    )
    expected_count = max(int(requirement.invoice_count or 1), 1)
    if expected_count <= 1 or expected_count > len(sorted_candidates):
        return []
    max_count = expected_count
    retained_per_sum = 64
    combinations_by_sum: dict[int, list[tuple[int, ...]]] = {0: [()]}
    for index, candidate in enumerate(sorted_candidates):
        amount_cents = _money_cents(candidate.invoice.total_amount)
        next_by_sum = {amount: list(combinations) for amount, combinations in combinations_by_sum.items()}
        for current_sum, combinations in combinations_by_sum.items():
            new_sum = current_sum + amount_cents
            if new_sum > target_cents:
                continue
            for combination in combinations:
                if len(combination) + 1 > max_count:
                    continue
                new_combination = (*combination, index)
                next_by_sum.setdefault(new_sum, []).append(new_combination)
        for amount, combinations in next_by_sum.items():
            deduped = list(dict.fromkeys(combinations))
            deduped.sort(
                key=lambda combination: _combination_match_score(
                    tuple(sorted_candidates[candidate_index] for candidate_index in combination),
                    requirement,
                )
            )
            next_by_sum[amount] = deduped[:retained_per_sum]
        combinations_by_sum = next_by_sum
    return [
        tuple(sorted_candidates[candidate_index] for candidate_index in combination)
        for combination in combinations_by_sum.get(target_cents, [])
        if len(combination) == expected_count
    ]


def _single_match_business_score(candidate: _InvoiceCandidate, requirement: ExpectedEtcInvoiceRequirement) -> tuple[object, ...]:
    return (
        0,
        _invoice_issue_time_score(candidate.invoice, requirement),
        _date_distance_days(candidate.invoice, requirement),
        _package_key(candidate.file_name),
    )


def _single_match_score(candidate: _InvoiceCandidate, requirement: ExpectedEtcInvoiceRequirement) -> tuple[object, ...]:
    return (
        *_single_match_business_score(candidate, requirement),
        candidate.file_name,
        candidate.invoice_number,
    )


def _combination_match_business_score(
    candidates: tuple[_InvoiceCandidate, ...],
    requirement: ExpectedEtcInvoiceRequirement,
) -> tuple[object, ...]:
    sorted_candidates = tuple(sorted(candidates, key=lambda candidate: (candidate.file_name, candidate.invoice_number)))
    return (
        1,
        len({_package_key(candidate.file_name) for candidate in sorted_candidates}),
        len(sorted_candidates),
        _combination_issue_time_score(sorted_candidates, requirement),
        sum(_date_distance_days(candidate.invoice, requirement) for candidate in sorted_candidates),
    )


def _combination_match_score(
    candidates: tuple[_InvoiceCandidate, ...],
    requirement: ExpectedEtcInvoiceRequirement,
) -> tuple[object, ...]:
    sorted_candidates = tuple(sorted(candidates, key=lambda candidate: (candidate.file_name, candidate.invoice_number)))
    return (
        *_combination_match_business_score(sorted_candidates, requirement),
        tuple(_package_key(candidate.file_name) for candidate in sorted_candidates),
        tuple(candidate.file_name for candidate in sorted_candidates),
        tuple(candidate.invoice_number for candidate in sorted_candidates),
    )


def _invoice_satisfies_requirement_context(invoice: ParsedEtcXml, requirement: ExpectedEtcInvoiceRequirement) -> bool:
    if requirement.vehicle_plate and (invoice.plate_number or "") != requirement.vehicle_plate:
        return False
    candidate_dates = [invoice.passage_start_date, invoice.passage_end_date, invoice.issue_date]
    return any(_date_in_window(candidate, requirement.date_window_start, requirement.date_window_end) for candidate in candidate_dates)


def _invoice_matches_requirement(invoice: ParsedEtcXml, requirement: ExpectedEtcInvoiceRequirement) -> bool:
    if Decimal(invoice.total_amount).quantize(Decimal("0.01")) != Decimal(requirement.amount).quantize(Decimal("0.01")):
        return False
    return _invoice_satisfies_requirement_context(invoice, requirement)


def _money_cents(value: Decimal) -> int:
    return int((Decimal(value).quantize(Decimal("0.01")) * 100).to_integral_value())


def _package_key(path: str) -> str:
    lowered = path.lower()
    nested_zip_index = lowered.rfind(".zip/")
    if nested_zip_index >= 0:
        return path[: nested_zip_index + len(".zip")]
    parent = Path(path).parent.as_posix()
    return parent if parent != "." else ""


def _date_distance_days(invoice: ParsedEtcXml, requirement: ExpectedEtcInvoiceRequirement) -> int:
    try:
        transaction_date = date.fromisoformat(requirement.transaction_at[:10])
    except ValueError:
        return 999999
    distances: list[int] = []
    for candidate in (invoice.passage_start_date, invoice.passage_end_date, invoice.issue_date):
        if not candidate:
            continue
        try:
            distances.append(abs((date.fromisoformat(candidate[:10]) - transaction_date).days))
        except ValueError:
            continue
    return min(distances) if distances else 999999


def _combination_issue_time_score(
    candidates: tuple[_InvoiceCandidate, ...],
    requirement: ExpectedEtcInvoiceRequirement,
) -> tuple[int, int]:
    scores = [_invoice_issue_time_score(candidate.invoice, requirement) for candidate in candidates]
    return (
        sum(score[0] for score in scores),
        sum(score[1] for score in scores),
    )


def _invoice_issue_time_score(invoice: ParsedEtcXml, requirement: ExpectedEtcInvoiceRequirement) -> tuple[int, int]:
    issue_datetime = _parse_datetime(getattr(invoice, "issue_datetime", None))
    requirement_datetime = _parse_datetime(requirement.transaction_at)
    if issue_datetime is None or requirement_datetime is None:
        return (1, 999999999)
    delta_seconds = int((issue_datetime - requirement_datetime).total_seconds())
    if delta_seconds < 0:
        return (2, abs(delta_seconds))
    return (0, delta_seconds)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("/", "-").replace("T", " ")
    if len(text) == 10:
        text = f"{text} 00:00:00"
    if len(text) == 16:
        text = f"{text}:00"
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _date_in_window(candidate: str | None, start: str, end: str) -> bool:
    if not candidate:
        return False
    try:
        candidate_date = date.fromisoformat(candidate[:10])
        start_date = date.fromisoformat(start[:10])
        end_date = date.fromisoformat(end[:10])
    except ValueError:
        return False
    return start_date <= candidate_date <= end_date


def _zip_entries(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()
