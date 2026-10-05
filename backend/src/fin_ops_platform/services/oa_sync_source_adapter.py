from __future__ import annotations

from typing import Any

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.postgres_repositories.oa_source_identity import PostgresOASourceIdentityRepository


def build_oa_sync_source_adapter(
    *,
    settings: Any,
    attachment_invoice_cache: Any,
    connection: Any,
) -> MongoOAAdapter:
    return MongoOAAdapter(
        settings=settings,
        attachment_invoice_cache=attachment_invoice_cache,
        identity_loader=PostgresOASourceIdentityRepository(connection).load_identities,
    )
