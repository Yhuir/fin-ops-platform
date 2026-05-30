from __future__ import annotations

from typing import Any

from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


def assert_workbench_stale_preconditions(command: Any) -> None:
    expected_versions = getattr(command, "expected_versions", None)
    if not isinstance(expected_versions, dict) or not expected_versions:
        return

    payload = getattr(command, "payload", None)
    current_state = payload if isinstance(payload, dict) else {}
    action = str(getattr(command, "action_name", "") or "")

    for raw_key, expected_value in expected_versions.items():
        key = str(raw_key)
        if key.startswith("relation:"):
            _assert_relation_precondition(
                action=action,
                key=key,
                expected_value=expected_value,
                current_state=current_state,
            )
            continue
        if key.startswith("row:"):
            _assert_row_precondition(
                action=action,
                key=key,
                expected_value=expected_value,
                current_state=current_state,
            )


def _assert_relation_precondition(
    *,
    action: str,
    key: str,
    expected_value: Any,
    current_state: dict[str, Any],
) -> None:
    expected_case_id = key.removeprefix("relation:")
    current_case_id = str(current_state.get("current_relation_case_id") or expected_case_id)
    current_version = current_state.get("current_relation_version")

    if current_case_id and current_case_id != expected_case_id:
        _raise_conflict(
            action=action,
            reason="stale_relation_identity",
            expected={key: expected_value},
            actual={f"relation:{current_case_id}": current_version},
        )
    if expected_value is not None and current_version is not None and str(current_version) != str(expected_value):
        _raise_conflict(
            action=action,
            reason="stale_relation_version",
            expected={key: expected_value},
            actual={key: current_version},
        )


def _assert_row_precondition(
    *,
    action: str,
    key: str,
    expected_value: Any,
    current_state: dict[str, Any],
) -> None:
    current_status = current_state.get("current_row_status")
    if expected_value is not None and current_status is not None and str(current_status) != str(expected_value):
        _raise_conflict(
            action=action,
            reason="stale_row_status",
            expected={key: expected_value},
            actual={key: current_status},
        )


def _raise_conflict(
    *,
    action: str,
    reason: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    raise WorkbenchWriteConflict(
        action=action,
        reason=reason,
        expected=expected,
        actual=actual,
        message=f"409 workbench_write_conflict: {reason}",
    )
