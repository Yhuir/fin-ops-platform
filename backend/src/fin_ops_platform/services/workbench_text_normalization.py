from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from collections.abc import Mapping


LOW_INFORMATION_TOKENS = frozenset({"报销", "付款", "费用", "有限公司"})
COMPANY_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "集团有限公司",
    "有限公司",
    "公司",
)
TOKEN_SPLIT_RE = re.compile(r"[\s,，.。;；:：、/\\|()（）\[\]【】{}<>《》\"'“”‘’+\-=_*&^%$#@!?！？~`]+")
PUNCTUATION_RE = re.compile(r"[\s,，.。;；:：、/\\|()（）\[\]【】{}<>《》\"'“”‘’+\-=_*&^%$#@!?！？~`]+")


@dataclass(frozen=True, slots=True)
class EvidenceToken:
    source_field: str
    value: str


def normalize_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    if not text:
        return ""
    text = PUNCTUATION_RE.sub("", text)
    text = _remove_company_suffix(text)
    text = _remove_low_information_terms(text)
    text = _remove_company_suffix(text)
    return "" if _is_low_information(text) else text


def evidence_tokens(fields: Mapping[str, object]) -> list[EvidenceToken]:
    tokens: list[EvidenceToken] = []
    seen: set[tuple[str, str]] = set()
    for source_field, raw_value in fields.items():
        for value in _field_tokens(raw_value):
            key = (str(source_field), value)
            if key in seen:
                continue
            seen.add(key)
            tokens.append(EvidenceToken(source_field=str(source_field), value=value))
    return tokens


def matching_tokens(left: list[EvidenceToken], right: list[EvidenceToken]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for left_token in left:
        for right_token in right:
            token = _matched_value(left_token.value, right_token.value)
            if not token:
                continue
            key = (left_token.source_field, right_token.source_field, token)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "token": token,
                    "left_source_field": left_token.source_field,
                    "right_source_field": right_token.source_field,
                }
            )
    return matches


def _field_tokens(value: object) -> list[str]:
    raw_text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    if not raw_text:
        return []

    candidates = [raw_text, *TOKEN_SPLIT_RE.split(raw_text)]
    tokens: list[str] = []
    for candidate in candidates:
        normalized = normalize_match_text(candidate)
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return tokens


def _remove_company_suffix(text: str) -> str:
    normalized = text
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                changed = True
                break
    return normalized


def _remove_low_information_terms(text: str) -> str:
    normalized = text
    changed = True
    while changed:
        changed = False
        for token in LOW_INFORMATION_TOKENS:
            if token and token in normalized:
                normalized = normalized.replace(token, "")
                changed = True
    return normalized


def _is_low_information(text: str) -> bool:
    return not text or text in LOW_INFORMATION_TOKENS


def _matched_value(left: str, right: str) -> str:
    if _is_low_information(left) or _is_low_information(right):
        return ""
    if left == right:
        return left
    if len(left) >= 2 and left in right:
        return left
    if len(right) >= 2 and right in left:
        return right
    return ""
