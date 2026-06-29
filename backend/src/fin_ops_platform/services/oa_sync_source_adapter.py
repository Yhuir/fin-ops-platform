from __future__ import annotations

from typing import Any

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter


def build_oa_sync_source_adapter(
    *,
    settings: Any,
    attachment_invoice_cache: Any,
) -> Any:
    return MongoOAAdapter(settings=settings, attachment_invoice_cache=attachment_invoice_cache)
