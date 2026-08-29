from __future__ import annotations


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


def requires_data_mutation(method: str, route_path: str) -> bool:
    """Fail closed for protected requests except known read-only operations."""
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
