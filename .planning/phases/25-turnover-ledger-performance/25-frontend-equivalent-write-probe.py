from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "https://www.yn-sourcing.com/fin-ops-api"
ROW_IDS = ("txn_imported_1278", "txn_imported_1348")
GROUPED_PATH = "/api/turnover-ledger?view=grouped&family=all&direction=all&page=1&page_size=100"


def request_json(path: str, *, token: str, body: dict[str, object] | None = None) -> tuple[dict[str, object], float]:
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=encoded,
        method="POST" if body is not None else "GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=20.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {detail[:1000]}") from exc
    elapsed_ms = (time.monotonic() - started) * 1000.0
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} returned a non-object payload")
    return payload, elapsed_ms


def target_rows(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for group in list(payload.get("groups") or []):
        if not isinstance(group, dict):
            continue
        for row in list(group.get("flow_rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("source_bank_row_id") or row.get("id") or "").strip()
            if row_id in ROW_IDS:
                rows[row_id] = row
    if set(rows) != set(ROW_IDS):
        raise RuntimeError(f"fixture rows missing from grouped payload: {sorted(set(ROW_IDS) - set(rows))}")
    return rows


def wait_barrier(targets: list[dict[str, object]], *, token: str, timeout_seconds: float = 20.0) -> tuple[dict[str, object], float, int]:
    started = time.monotonic()
    polls = 0
    while time.monotonic() - started <= timeout_seconds:
        payload, _ = request_json("/api/operation-barrier/status", token=token, body={"targets": targets})
        polls += 1
        status = str(payload.get("status") or "").strip().lower()
        if bool(payload.get("fresh")) or status == "fresh":
            return payload, (time.monotonic() - started) * 1000.0, polls
        if status == "blocked" or list(payload.get("blocked_targets") or []):
            raise RuntimeError(f"operation barrier blocked: {json.dumps(payload, ensure_ascii=False)[:1500]}")
        time.sleep(0.3)
    raise RuntimeError("operation barrier timed out")


def assert_visibility(*, linked: bool, case_id: str | None, token: str) -> tuple[float, dict[str, object]]:
    payload, elapsed_ms = request_json(GROUPED_PATH, token=token)
    if str((payload.get("read_model_status") or {}).get("status") if isinstance(payload.get("read_model_status"), dict) else payload.get("read_model_status") or "").lower() != "fresh":
        raise RuntimeError(f"grouped payload is not fresh: {payload.get('read_model_status')}")
    rows = target_rows(payload)
    observed = {
        row_id: {
            "cash_closure_linked": bool(row.get("cash_closure_linked")),
            "cash_closure_case_id": str(row.get("cash_closure_case_id") or "") or None,
            "category_version": row.get("category_version"),
        }
        for row_id, row in rows.items()
    }
    if any(item["cash_closure_linked"] is not linked for item in observed.values()):
        raise RuntimeError(f"unexpected closure visibility: {observed}")
    if linked and any(item["cash_closure_case_id"] != case_id for item in observed.values()):
        raise RuntimeError(f"closure case mismatch: expected={case_id} observed={observed}")
    return elapsed_ms, observed


def percentile_max(values: list[float]) -> float:
    return round(max(values), 3) if values else 0.0


def run(iterations: int, *, release_sha: str) -> dict[str, object]:
    token = str(os.environ.get("FIN_OPS_HTTP_SLO_ADMIN_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("FIN_OPS_HTTP_SLO_ADMIN_TOKEN is required")
    baseline, baseline_ms = request_json(GROUPED_PATH, token=token)
    baseline_rows = target_rows(baseline)
    if any(bool(row.get("cash_closure_linked")) for row in baseline_rows.values()):
        raise RuntimeError("fixture is already linked; refusing to mutate production")
    expected_versions = {
        f"turnover_bank_row:{row_id}": baseline_rows[row_id].get("category_version")
        for row_id in ROW_IDS
    }
    if any(value is None for value in expected_versions.values()):
        raise RuntimeError(f"fixture category versions are unavailable: {expected_versions}")

    cycles: list[dict[str, object]] = []
    active_case_id: str | None = None
    recovery: dict[str, object] | None = None
    try:
        for index in range(iterations):
            idempotency_key = f"turnover-phase25-batch-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}-{index + 1}"
            confirm, confirm_command_ms = request_json(
                "/api/turnover-ledger/closures/confirm",
                token=token,
                body={
                    "bank_row_ids": list(ROW_IDS),
                    "expected_versions": expected_versions,
                    "idempotency_key": idempotency_key,
                    "note": "Codex production performance verification; reversible fixture",
                },
            )
            pair_relation = confirm.get("workbench_pair_relation")
            active_case_id = str(pair_relation.get("case_id") if isinstance(pair_relation, dict) else "").strip() or None
            if not active_case_id:
                raise RuntimeError(f"confirm response missing workbench pair case: {confirm}")
            confirm_targets = list(confirm.get("operation_barrier_targets") or confirm.get("freshness_targets") or [])
            if not confirm_targets:
                raise RuntimeError("confirm response missing operation barrier targets")
            _, confirm_fresh_ms, confirm_polls = wait_barrier(confirm_targets, token=token)
            confirm_reload_ms, confirm_observed = assert_visibility(linked=True, case_id=active_case_id, token=token)

            withdraw, withdraw_command_ms = request_json(
                "/api/turnover-ledger/closures/withdraw",
                token=token,
                body={
                    "cash_closure_case_id": active_case_id,
                    "note": "Codex production performance verification recovery",
                },
            )
            withdraw_targets = list(withdraw.get("operation_barrier_targets") or withdraw.get("freshness_targets") or [])
            if not withdraw_targets:
                raise RuntimeError("withdraw response missing operation barrier targets")
            _, withdraw_fresh_ms, withdraw_polls = wait_barrier(withdraw_targets, token=token)
            withdraw_reload_ms, withdraw_observed = assert_visibility(linked=False, case_id=None, token=token)
            active_case_id = None
            cycles.append(
                {
                    "cycle": index + 1,
                    "confirm": {
                        "command_ms": round(confirm_command_ms, 3),
                        "response_to_fresh_ms": round(confirm_fresh_ms, 3),
                        "reload_ms": round(confirm_reload_ms, 3),
                        "response_to_visible_ms": round(confirm_fresh_ms + confirm_reload_ms, 3),
                        "click_to_visible_ms": round(confirm_command_ms + confirm_fresh_ms + confirm_reload_ms, 3),
                        "barrier_polls": confirm_polls,
                        "targets": confirm_targets,
                        "observed": confirm_observed,
                    },
                    "withdraw": {
                        "command_ms": round(withdraw_command_ms, 3),
                        "response_to_fresh_ms": round(withdraw_fresh_ms, 3),
                        "reload_ms": round(withdraw_reload_ms, 3),
                        "response_to_visible_ms": round(withdraw_fresh_ms + withdraw_reload_ms, 3),
                        "click_to_visible_ms": round(withdraw_command_ms + withdraw_fresh_ms + withdraw_reload_ms, 3),
                        "barrier_polls": withdraw_polls,
                        "targets": withdraw_targets,
                        "observed": withdraw_observed,
                    },
                }
            )
    finally:
        if active_case_id:
            try:
                response, recovery_command_ms = request_json(
                    "/api/turnover-ledger/closures/withdraw",
                    token=token,
                    body={"cash_closure_case_id": active_case_id, "note": "Codex automatic probe recovery"},
                )
                targets = list(response.get("operation_barrier_targets") or response.get("freshness_targets") or [])
                _, recovery_fresh_ms, recovery_polls = wait_barrier(targets, token=token)
                recovery_reload_ms, recovery_observed = assert_visibility(linked=False, case_id=None, token=token)
                recovery = {
                    "status": "pass",
                    "command_ms": round(recovery_command_ms, 3),
                    "response_to_fresh_ms": round(recovery_fresh_ms, 3),
                    "reload_ms": round(recovery_reload_ms, 3),
                    "barrier_polls": recovery_polls,
                    "observed": recovery_observed,
                }
                active_case_id = None
            except Exception as exc:
                recovery = {"status": "fail", "error": str(exc)}

    command_values = [float(cycle[action]["command_ms"]) for cycle in cycles for action in ("confirm", "withdraw")]
    fresh_values = [float(cycle[action]["response_to_fresh_ms"]) for cycle in cycles for action in ("confirm", "withdraw")]
    visible_values = [float(cycle[action]["response_to_visible_ms"]) for cycle in cycles for action in ("confirm", "withdraw")]
    summary = {
        "command_p95_ms": percentile_max(command_values),
        "response_to_fresh_p95_ms": percentile_max(fresh_values),
        "response_to_visible_p95_ms": percentile_max(visible_values),
        "command_target_ms": 1000.0,
        "fresh_target_ms": 2000.0,
        "hard_max_ms": 3000.0,
    }
    passed = (
        len(cycles) == iterations
        and summary["command_p95_ms"] <= summary["command_target_ms"]
        and summary["response_to_fresh_p95_ms"] <= summary["fresh_target_ms"]
        and max(command_values + fresh_values + visible_values, default=0.0) <= summary["hard_max_ms"]
        and active_case_id is None
        and (recovery is None or recovery.get("status") == "pass")
    )
    return {
        "status": "pass" if passed else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "release_sha": release_sha,
        "fixture_row_ids": list(ROW_IDS),
        "baseline_ms": round(baseline_ms, 3),
        "expected_versions": expected_versions,
        "cycles": cycles,
        "summary": summary,
        "recovery": recovery,
        "final_fixture_state": "unlinked" if active_case_id is None else "recovery_failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(max(1, args.iterations), release_sha=str(args.release_sha).strip())
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
