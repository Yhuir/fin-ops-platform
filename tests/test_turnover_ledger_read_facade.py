from __future__ import annotations

import unittest

from fin_ops_platform.app.turnover_ledger_read_facade import TurnoverLedgerReadFacade


class FakeTurnoverLedgerRoutes:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_ledger(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_ledger", dict(kwargs)))
        return {"rows": [{"relation_id": "rel-1"}], "filters": {"family": kwargs.get("family")}}

    def export_preview(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("export_preview", dict(kwargs)))
        return {"rows": [], "filters": {"family": kwargs.get("family")}}

    def export(self, **kwargs: object) -> tuple[str, bytes]:
        self.calls.append(("export", dict(kwargs)))
        return "turnover.xlsx", b"xlsx"

    def get_relation(self, relation_id: str) -> dict[str, object]:
        self.calls.append(("get_relation", {"relation_id": relation_id}))
        return {"relation": {"relation_id": relation_id}}

    def get_relation_extra(self, relation_id: str) -> dict[str, object]:
        self.calls.append(("get_relation_extra", {"relation_id": relation_id}))
        return {"extra": {"relation_id": relation_id}}


class TurnoverLedgerReadFacadeTests(unittest.TestCase):
    def test_read_facade_delegates_to_turnover_routes_and_returns_plain_payloads(self) -> None:
        routes = FakeTurnoverLedgerRoutes()
        facade = TurnoverLedgerReadFacade(routes=routes)

        self.assertEqual(
            facade.list_ledger(view="grouped", family="company", direction="all", status=None, page=2, page_size=25),
            {"rows": [{"relation_id": "rel-1"}], "filters": {"family": "company"}},
        )
        self.assertEqual(facade.export_preview(family="company", limit=10), {"rows": [], "filters": {"family": "company"}})
        self.assertEqual(facade.export(family="company"), ("turnover.xlsx", b"xlsx"))
        self.assertEqual(facade.get_relation("rel-1"), {"relation": {"relation_id": "rel-1"}})
        self.assertEqual(facade.get_relation_extra("rel-1"), {"extra": {"relation_id": "rel-1"}})

        self.assertEqual(
            routes.calls,
            [
                (
                    "list_ledger",
                    {"view": "grouped", "family": "company", "direction": "all", "status": None, "page": 2, "page_size": 25},
                ),
                ("export_preview", {"family": "company", "limit": 10}),
                ("export", {"family": "company"}),
                ("get_relation", {"relation_id": "rel-1"}),
                ("get_relation_extra", {"relation_id": "rel-1"}),
            ],
        )

    def test_read_facade_propagates_route_errors_for_http_mapping(self) -> None:
        class BrokenRoutes(FakeTurnoverLedgerRoutes):
            def list_ledger(self, **kwargs: object) -> dict[str, object]:
                raise ValueError("bad page")

            def get_relation(self, relation_id: str) -> dict[str, object]:
                raise KeyError(relation_id)

        facade = TurnoverLedgerReadFacade(routes=BrokenRoutes())

        with self.assertRaisesRegex(ValueError, "bad page"):
            facade.list_ledger(view=None, family="all", direction="all", status=None, page=0, page_size=50)
        with self.assertRaises(KeyError):
            facade.get_relation("missing")


if __name__ == "__main__":
    unittest.main()
