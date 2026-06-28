from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from fin_ops_platform.services.state_store_diff import diff_state_snapshots, redact_diff_payload


ALLOWED_SEVERITIES = {"P0", "P1", "P2", "ignored"}
FORBIDDEN_METHOD_PREFIXES = (
    "save",
    "store",
    "delete",
    "truncate",
    "confirm",
    "submit",
    "withdraw",
    "revert",
    "clear",
    "sync",
)
FORBIDDEN_READ_METHODS = {
    "load",
    "load_oa_attachment_invoice_cache_entry",
    "load_oa_sync_state",
    "load_manual_oa_imports",
    "read_import_file",
    "read_etc_reconciliation_file",
    "read_etc_invoice_file",
    "read_historical_etc_repair_bundle",
}


@dataclass(frozen=True)
class ShadowReadDomainSpec:
    domain: str
    method_name: str
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    primary_source: str = "primary"
    shadow_source: str = "shadow"
    parameters_source: str = "parameterless"
    expected_shape: str = "unknown"
    ignored_paths: frozenset[str] = field(default_factory=frozenset)
    severity: str = "P1"
    severity_by_path: Mapping[str, str] = field(default_factory=dict)
    max_mismatches: int = 20

    def __post_init__(self) -> None:
        _validate_read_method(self.method_name)
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"Unsupported severity {self.severity!r}.")
        for path, severity in self.severity_by_path.items():
            if severity not in ALLOWED_SEVERITIES:
                raise ValueError(f"Unsupported severity {severity!r} for path {path!r}.")
        if self.max_mismatches <= 0:
            raise ValueError("max_mismatches must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return redact_diff_payload(
            {
                **asdict(self),
                "ignored_paths": sorted(self.ignored_paths),
                "kwargs": dict(self.kwargs),
            }
        )


@dataclass(frozen=True)
class ShadowReadDomainResult:
    domain: str
    method_name: str
    status: str
    matched: bool
    severity_counts: dict[str, int]
    mismatch_count: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    spec: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_diff_payload(asdict(self))


@dataclass(frozen=True)
class ShadowReadRehearsalReport:
    run_id: str
    started_at: str
    completed_at: str
    primary_backend: str
    shadow_backend: str
    domain_results: list[dict[str, Any]]
    summary: dict[str, Any]
    gate_recommendation: str
    redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return redact_diff_payload(asdict(self))


class ShadowReadRehearsalRunner:
    def __init__(
        self,
        *,
        primary_store: Any,
        shadow_store: Any,
        domain_specs: list[ShadowReadDomainSpec],
        run_id: str | None = None,
        max_mismatches: int = 20,
    ) -> None:
        self._primary_store = primary_store
        self._shadow_store = shadow_store
        self._domain_specs = list(domain_specs)
        self._run_id = run_id or f"stage11-{uuid4().hex[:12]}"
        self._max_mismatches = max_mismatches
        if self._max_mismatches <= 0:
            raise ValueError("max_mismatches must be positive.")
        if not self._domain_specs:
            raise ValueError("At least one shadow-read domain spec is required.")

    def run(self) -> ShadowReadRehearsalReport:
        started_at = _utc_now()
        domain_results = [self._run_domain(spec).to_dict() for spec in self._domain_specs]
        completed_at = _utc_now()
        summary = summarize_domain_results(domain_results)
        return ShadowReadRehearsalReport(
            run_id=self._run_id,
            started_at=started_at,
            completed_at=completed_at,
            primary_backend=str(getattr(self._primary_store, "storage_backend", "unknown")),
            shadow_backend=str(getattr(self._shadow_store, "storage_backend", "unknown")),
            domain_results=domain_results,
            summary=summary,
            gate_recommendation=_gate_from_summary(summary),
        )

    def _run_domain(self, spec: ShadowReadDomainSpec) -> ShadowReadDomainResult:
        _validate_read_method(spec.method_name)
        try:
            primary_method = getattr(self._primary_store, spec.method_name)
        except AttributeError as exc:
            return _error_result(spec, "primary_error", exc)
        try:
            shadow_method = getattr(self._shadow_store, spec.method_name)
        except AttributeError as exc:
            return _error_result(spec, "shadow_error", exc)

        try:
            primary_value = primary_method(*spec.args, **dict(spec.kwargs))
        except Exception as exc:  # noqa: BLE001 - rehearsal reports primary read failures as data.
            return _error_result(spec, "primary_error", exc)
        try:
            shadow_value = shadow_method(*spec.args, **dict(spec.kwargs))
        except Exception as exc:  # noqa: BLE001 - shadow read is intentionally non-mutating rehearsal.
            return _error_result(spec, "shadow_error", exc)

        diff = diff_state_snapshots(
            primary_value,
            shadow_value,
            domain=spec.domain,
            ignored_paths=set(spec.ignored_paths),
            max_mismatches=min(spec.max_mismatches, self._max_mismatches),
        )
        if diff.matched:
            return ShadowReadDomainResult(
                domain=spec.domain,
                method_name=spec.method_name,
                status="matched",
                matched=True,
                mismatch_count=0,
                severity_counts=_empty_severity_counts(),
                spec=spec.to_dict(),
            )

        classified = [_classify_mismatch(mismatch, spec) for mismatch in diff.mismatches]
        return ShadowReadDomainResult(
            domain=spec.domain,
            method_name=spec.method_name,
            status="mismatched",
            matched=False,
            mismatch_count=diff.mismatch_count,
            mismatches=classified,
            severity_counts=_severity_counts(classified),
            spec=spec.to_dict(),
        )


def default_shadow_read_domain_specs(
    *,
    domains: list[str] | None = None,
    primary_source: str = "primary",
    shadow_source: str = "postgres",
    max_mismatches: int = 20,
) -> list[ShadowReadDomainSpec]:
    catalog = {
        spec.domain: spec
        for spec in [
            _domain("app_settings", "load_app_settings", "settings payload", "P1"),
            _domain("pending_invoice_commands", "load_pending_invoice_commands", "request id -> pending invoice command", "P1"),
            _domain("background_jobs", "load_background_jobs", "job id -> job snapshot", "P2"),
            _domain("app_health_alerts", "load_app_health_alerts", "alert id -> alert snapshot", "P2"),
            _domain("workbench_pair_relations", "load_workbench_pair_relations", "case id -> relation snapshot", "P0"),
            _domain("no_oa_bank_batches", "load_no_oa_bank_batches", "batch id -> batch snapshot", "P0"),
            _domain("bank_transaction_categories", "load_bank_transaction_categories", "category snapshot", "P1"),
            _domain("turnover_relations", "load_turnover_relations", "relation id -> turnover relation", "P0"),
            _domain("turnover_relation_audit_log", "load_turnover_relation_audit_log", "audit event list", "P2"),
            _domain("turnover_ledger_extras", "load_turnover_ledger_extras", "ledger extras snapshot", "P1"),
            _domain("workbench_candidate_matches", "load_workbench_candidate_matches", "month/scope -> candidates", "P1"),
            _domain("tax_certified_imports", "load_tax_certified_imports", "tax certified import snapshot", "P1"),
            _domain(
                "etc_state",
                "load_etc_state",
                "ETC invoice/import snapshot",
                "P1",
                ignored_paths=frozenset({"batch_day_counters"}),
            ),
            _domain("etc_reconciliation_state", "load_etc_reconciliation_state", "ETC reconciliation snapshot", "P1"),
            _domain(
                "historical_etc_repair_bundle_metadata",
                "load_historical_etc_repair_bundle_metadata",
                "bundle id -> metadata only",
                "P2",
            ),
            _domain(
                "historical_etc_repair_parsed_seeds",
                "load_historical_etc_repair_parsed_seeds",
                "bundle id -> parsed seed metadata",
                "P2",
            ),
            _domain("historical_etc_repair_states", "load_historical_etc_repair_states", "repair state snapshot", "P1"),
        ]
    }
    selected = list(domains or catalog)
    unknown = sorted(set(selected) - set(catalog))
    if unknown:
        raise ValueError(f"Unsupported shadow-read domains: {', '.join(unknown)}")
    return [
        ShadowReadDomainSpec(
            **{
                **catalog[domain].to_dict(),
                "ignored_paths": frozenset(catalog[domain].ignored_paths),
                "severity_by_path": dict(catalog[domain].severity_by_path),
                "primary_source": primary_source,
                "shadow_source": shadow_source,
                "max_mismatches": max_mismatches,
            }
        )
        for domain in selected
    ]


def summarize_domain_results(domain_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    severity_counts = _empty_severity_counts()
    for result in domain_results:
        status = str(result.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        for severity, count in (result.get("severity_counts") or {}).items():
            if severity in severity_counts:
                severity_counts[severity] += int(count)
    total = len(domain_results)
    return {
        "total_domains": total,
        "compared_domains": status_counts.get("matched", 0) + status_counts.get("mismatched", 0),
        "matched_domains": status_counts.get("matched", 0),
        "mismatched_domains": status_counts.get("mismatched", 0),
        "primary_errors": status_counts.get("primary_error", 0),
        "shadow_errors": status_counts.get("shadow_error", 0),
        "blocked_domains": status_counts.get("blocked", 0),
        "status_counts": status_counts,
        "severity_counts": severity_counts,
    }


def _domain(
    domain: str,
    method_name: str,
    expected_shape: str,
    severity: str,
    *,
    ignored_paths: frozenset[str] = frozenset(),
) -> ShadowReadDomainSpec:
    return ShadowReadDomainSpec(
        domain=domain,
        method_name=method_name,
        expected_shape=expected_shape,
        severity=severity,
        ignored_paths=frozenset({"updated_at", "created_at", "generated_at", "raw_payload.migration_metadata"}) | ignored_paths,
    )


def _classify_mismatch(mismatch: Mapping[str, Any], spec: ShadowReadDomainSpec) -> dict[str, Any]:
    path = str(mismatch.get("path") or "")
    severity = spec.severity
    for prefix, mapped_severity in spec.severity_by_path.items():
        if path == prefix or path.startswith(f"{prefix}.") or path.startswith(f"{prefix}["):
            severity = mapped_severity
            break
    safe_mismatch = {
        "path": path,
        "kind": mismatch.get("kind"),
        "primary": _summarize_mismatch_value(mismatch.get("primary")),
        "shadow": _summarize_mismatch_value(mismatch.get("shadow")),
        "severity": severity,
    }
    return redact_diff_payload(safe_mismatch)


def _summarize_mismatch_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"present": False, "type": "null"}
    redacted_value = redact_diff_payload(value)
    summary: dict[str, Any] = {"present": True, "type": type(redacted_value).__name__}
    if isinstance(redacted_value, dict):
        keys = sorted(str(key) for key in redacted_value.keys())
        summary["key_count"] = len(keys)
        summary["sample_keys"] = keys[:5]
    elif isinstance(redacted_value, (list, tuple, set)):
        summary["item_count"] = len(redacted_value)
    else:
        summary["scalar"] = True
    summary["sha256"] = hashlib.sha256(
        json.dumps(redacted_value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return summary


def _error_result(spec: ShadowReadDomainSpec, status: str, error: Exception) -> ShadowReadDomainResult:
    return ShadowReadDomainResult(
        domain=spec.domain,
        method_name=spec.method_name,
        status=status,
        matched=False,
        severity_counts=_empty_severity_counts(),
        error=str(redact_diff_payload(f"{type(error).__name__}: {error}")),
        spec=spec.to_dict(),
    )


def _severity_counts(mismatches: list[dict[str, Any]]) -> dict[str, int]:
    counts = _empty_severity_counts()
    for mismatch in mismatches:
        severity = str(mismatch.get("severity") or "P1")
        if severity in counts:
            counts[severity] += 1
    return counts


def _empty_severity_counts() -> dict[str, int]:
    return {"P0": 0, "P1": 0, "P2": 0, "ignored": 0}


def _gate_from_summary(summary: Mapping[str, Any]) -> str:
    severity_counts = summary.get("severity_counts") if isinstance(summary.get("severity_counts"), dict) else {}
    if int(summary.get("primary_errors") or 0) or int(summary.get("shadow_errors") or 0):
        return "BLOCKED"
    if int(severity_counts.get("P0") or 0) or int(severity_counts.get("P1") or 0):
        return "BLOCKED"
    if int(summary.get("mismatched_domains") or 0) or int(severity_counts.get("P2") or 0):
        return "PARTIAL"
    return "PASS"


def _validate_read_method(method_name: str) -> None:
    lowered = method_name.lower()
    if lowered in FORBIDDEN_READ_METHODS:
        raise ValueError(f"Shadow-read rehearsal excludes high-risk read method {method_name!r}.")
    if any(lowered.startswith(prefix) for prefix in FORBIDDEN_METHOD_PREFIXES):
        raise ValueError(f"Shadow-read rehearsal refuses non-read method {method_name!r}.")
    if lowered.startswith("load_oa_") or lowered.startswith("read_oa_"):
        raise ValueError(f"Shadow-read rehearsal excludes OA adapter/state domain {method_name!r}.")
    if not (lowered == "load" or lowered.startswith("load_") or lowered.startswith("read_") or lowered.endswith("_exists")):
        raise ValueError(f"Shadow-read rehearsal requires an explicit read method, got {method_name!r}.")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
