from __future__ import annotations

from typing import Any, Callable


class TurnoverLedgerQueryService:
    def __init__(
        self,
        *,
        legacy_payload_builder: Callable[..., dict[str, Any]],
    ) -> None:
        self._legacy_payload_builder = legacy_payload_builder

    def list_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
        view: str | None = None,
    ) -> dict[str, Any]:
        _ = view
        return self._legacy_payload_builder(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
        )
