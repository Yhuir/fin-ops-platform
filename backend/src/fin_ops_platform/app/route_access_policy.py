from __future__ import annotations

from fin_ops_platform.services.access_control_service import ALL_PAGE_KEYS, ASSIGNABLE_PAGE_KEYS


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_READ_ONLY_POST_ROUTES = frozenset(
    {
        "/api/input-invoice-usage/oa-reverse/preview",
        "/api/pending-invoices/attach-existing-invoices/preview",
        "/api/pending-invoices/invoice-candidates/batch",
        "/api/tax-offset/calculate",
        "/api/workbench/actions/confirm-link/preview",
        "/api/workbench/actions/receipt-draft",
        "/api/workbench/actions/withdraw-link/preview",
        "/imports/invoices/manual/recognize",
    }
)

_ADMIN_ONLY_PREFIXES = (
    "/api/operations/history",
    "/api/workbench/settings/access-control",
    "/api/workbench/settings/oa-applicant-credentials",
    "/api/workbench/settings/data-reset",
)

_ROUTE_PAGE_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/api/workbench/settings", ("settings",)),
    ("/api/workbench/oa-invoice-supplements", ("reconciliation-workbench",)),
    ("/api/workbench", ("reconciliation-workbench",)),
    ("/reconciliation", ("reconciliation-workbench",)),
    ("/api/cost-statistics", ("cost-statistics",)),
    ("/api/bank-details", ("bank-details",)),
    ("/api/no-oa-bank-batches", ("bank-details",)),
    ("/api/oa-pending-payments", ("oa-pending-payments",)),
    ("/api/oa-sync", ("oa-pending-payments",)),
    ("/api/bank-flow-rule-batches", ("bank-flow-rule-batches",)),
    ("/api/batch-accounting", ("batch-accounting",)),
    ("/api/turnover-ledger", ("turnover-ledger",)),
    ("/api/etc/import", ("imports.etc-invoices",)),
    ("/api/etc", ("etc-tickets",)),
    ("/api/tax-offset", ("tax-offset",)),
    ("/api/pending-invoices", ("pending-invoices",)),
    ("/api/input-invoice-usage", ("input-invoice-usage",)),
    ("/api/output-invoice-collections", ("output-invoice-collections",)),
    ("/api/operations/history", ("operation-history",)),
    ("/api/operations/app-health-dashboard", ("app-health-operations",)),
    ("/api/operations/app-health", ("app-health-operations",)),
    ("/api/operations/import-history", ("app-health-operations",)),
    ("/api/app-health", ("app-health-operations",)),
    ("/api/imports/bank-transaction-batches", ("imports.bank-transactions",)),
    ("/imports/bank-transactions", ("imports.bank-transactions",)),
    ("/imports/invoices", ("imports.invoices",)),
    ("/imports/etc-invoices", ("imports.etc-invoices",)),
    ("/imports/batches", ("imports.bank-transactions", "imports.invoices", "imports.etc-invoices")),
    ("/imports/files", ("imports.bank-transactions", "imports.invoices", "imports.etc-invoices")),
    ("/imports/templates", ("imports.bank-transactions", "imports.invoices", "imports.etc-invoices")),
    (
        "/api/import-facts",
        ("reconciliation-workbench", "imports.bank-transactions", "imports.invoices", "imports.etc-invoices"),
    ),
    ("/api/background-jobs", tuple(sorted(ASSIGNABLE_PAGE_KEYS))),
)


def is_state_changing_request(method: str, route_path: str) -> bool:
    """Classify requests for durable operation audit, independent of authorization."""
    normalized_method = method.upper()
    if normalized_method in _SAFE_METHODS:
        return False
    if normalized_method != "POST":
        return True
    if route_path in _READ_ONLY_POST_ROUTES:
        return False
    return not (
        route_path.startswith("/api/pending-invoices/rows/")
        and route_path.endswith("/attach-existing-invoice/preview")
    )


def is_admin_only_route(route_path: str) -> bool:
    return any(_matches_prefix(route_path, prefix) for prefix in _ADMIN_ONLY_PREFIXES)


def page_keys_for_route(route_path: str) -> tuple[str, ...] | None:
    for prefix, page_keys in _ROUTE_PAGE_PREFIXES:
        if _matches_prefix(route_path, prefix):
            return page_keys
    return None


def audit_page_key_for_route(route_path: str) -> str:
    page_keys = page_keys_for_route(route_path)
    return page_keys[0] if page_keys else "application"


def registered_page_keys() -> frozenset[str]:
    return frozenset(page_key for _prefix, page_keys in _ROUTE_PAGE_PREFIXES for page_key in page_keys)


def missing_page_keys() -> frozenset[str]:
    return ALL_PAGE_KEYS.difference(registered_page_keys())


def _matches_prefix(route_path: str, prefix: str) -> bool:
    normalized = prefix.rstrip("/")
    return route_path == normalized or route_path.startswith(f"{normalized}/")
