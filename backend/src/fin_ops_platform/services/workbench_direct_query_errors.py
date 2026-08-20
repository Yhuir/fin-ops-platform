from __future__ import annotations


class WorkbenchDirectQueryUnavailable(RuntimeError):
    """A known retryable PostgreSQL failure prevented a complete direct query."""


class WorkbenchRelationPreviewSelectionError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_TRANSIENT_SQLSTATES = frozenset(
    {
        "53300",  # too_many_connections
        "55P03",  # lock_not_available
        "57014",  # query_canceled / statement_timeout
        "57P01",  # admin_shutdown
        "57P02",  # crash_shutdown
        "57P03",  # cannot_connect_now
    }
)


def is_transient_postgres_query_error(error: BaseException) -> bool:
    sqlstate = str(
        getattr(error, "sqlstate", None)
        or getattr(error, "pgcode", None)
        or ""
    ).strip()
    if sqlstate.startswith("08") or sqlstate in _TRANSIENT_SQLSTATES:
        return True
    class_name = error.__class__.__name__.lower()
    if class_name in {
        "connectiontimeout",
        "operationalerror",
        "pooltimeout",
        "querycanceled",
    }:
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "canceling statement due to statement timeout",
            "connection is closed",
            "connection refused",
            "connection timed out",
            "server closed the connection unexpectedly",
            "timeout expired",
        )
    )


def is_workbench_data_integrity_query_error(error: BaseException) -> bool:
    """Return whether a fail-closed SQL invariant rejected canonical data.

    Direct Workbench SQL deliberately evaluates guarded divisions after it has
    detected malformed relation/member or synthetic-row identities.  Those
    failures describe unavailable canonical page data, not invalid HTTP input,
    and must never be exposed as a generic 500 or misreported as a 400.
    """

    sqlstate = str(
        getattr(error, "sqlstate", None)
        or getattr(error, "pgcode", None)
        or ""
    ).strip()
    return sqlstate == "22012"  # division_by_zero from an explicit SQL guard


__all__ = [
    "WorkbenchDirectQueryUnavailable",
    "WorkbenchRelationPreviewSelectionError",
    "is_workbench_data_integrity_query_error",
    "is_transient_postgres_query_error",
]
