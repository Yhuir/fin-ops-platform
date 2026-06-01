from __future__ import annotations

from typing import Any


class TurnoverLedgerReadFacade:
    def __init__(self, *, routes: Any) -> None:
        self._routes = routes

    def list_ledger(
        self,
        *,
        view: str | None,
        family: str,
        direction: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        return self._routes.list_ledger(
            view=view,
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )

    def export_preview(self, *, family: str, limit: int) -> dict[str, object]:
        return self._routes.export_preview(family=family, limit=limit)

    def export(self, *, family: str) -> tuple[str, bytes]:
        return self._routes.export(family=family)

    def get_relation(self, relation_id: str) -> dict[str, object]:
        return self._routes.get_relation(relation_id)

    def get_relation_extra(self, relation_id: str) -> dict[str, object]:
        return self._routes.get_relation_extra(relation_id)
