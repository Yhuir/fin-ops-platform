from __future__ import annotations

from dataclasses import dataclass, field


class OASourceIdentityConflict(ValueError):
    """A source identifier has more than one proven canonical owner."""


@dataclass
class OASourceIdentities:
    owners: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    def canonical_id(self, source_id: str) -> str:
        owner = self.owners.get(source_id)
        alias = self.aliases.get(source_id)
        if owner and alias and owner != alias:
            raise OASourceIdentityConflict(f"oa_source_identity_conflict: {source_id}")
        return owner or alias or source_id

    def add_owner(self, source_id: str, row_id: str) -> None:
        previous = self.owners.get(source_id) or self.aliases.get(source_id)
        if previous and previous != row_id:
            raise OASourceIdentityConflict(f"oa_source_identity_conflict: {source_id}")
        self.owners[source_id] = row_id


def source_document_row_id(apply_type: str, document_id: str) -> str:
    prefix = {"支付申请": "oa-pay-", "日常报销": "oa-exp-"}.get(apply_type)
    if not document_id or prefix is None:
        raise OASourceIdentityConflict("oa_source_identity_missing")
    return prefix + document_id
