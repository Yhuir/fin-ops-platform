"""Cash-only SQL and transaction boundary. Never reads app, audit, job or OA."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from fin_ops_platform.services.cash_domain import CashError

TABLES = frozenset({"accounts", "categories", "bill_labels", "settings", "flows", "items", "settlements", "task_templates", "task_occurrences"})


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError("Invalid internal SQL identifier")
    return '"' + value + '"'


def _row(row):
    if row is None:
        return None
    return {key: str(value) if isinstance(value, UUID) else value for key, value in row.items()}


class CashTransaction:
    def __init__(self, raw) -> None:
        self.raw = raw
        self._bumped: set[tuple[str, str]] = set()
        self._new: set[tuple[str, str]] = set()
        self._deleted: set[tuple[str, str]] = set()

    @staticmethod
    def table(table):
        if table not in TABLES:
            raise ValueError("Not a cash business table")
        return "cash." + _identifier(table)

    def get(self, table, entity_id, lock=None, *, required=True):
        suffix = {None: "", "share": " FOR SHARE", "update": " FOR UPDATE"}[lock]
        row = _row(self.raw.fetch_one(f"SELECT * FROM {self.table(table)} WHERE id=%s{suffix}", (entity_id,)))
        if row is None and required:
            raise CashError("cash_not_found", "现金记录不存在或已删除。", 404)
        return row

    def rows(self, table, filters=None, *, order="id", limit=None):
        clauses, params = [], []
        for key, value in (filters or {}).items():
            if value is None:
                clauses.append(f"{_identifier(key)} IS NULL")
            else:
                clauses.append(f"{_identifier(key)}=%s")
                params.append(value)
        sql = f"SELECT * FROM {self.table(table)}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY " + _identifier(order)
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        return [_row(row) for row in self.raw.fetch_all(sql, tuple(params))]

    def lock_rows(self, table, ids, mode="update"):
        ids = sorted(set(value for value in ids if value is not None))
        if not ids:
            return {}
        sql = f"SELECT * FROM {self.table(table)} WHERE id=ANY(%s::uuid[]) ORDER BY id FOR " + {"share": "SHARE", "update": "UPDATE"}[mode]
        rows = [_row(row) for row in self.raw.fetch_all(sql, (ids,))]
        return {row["id"]: row for row in rows}

    def insert(self, table, values):
        keys = list(values)
        params = tuple(Jsonb(value) if isinstance(value, dict) else value for value in values.values())
        sql = f"INSERT INTO {self.table(table)} ({','.join(_identifier(key) for key in keys)}) VALUES ({','.join(['%s']*len(keys))}) ON CONFLICT (id) DO NOTHING RETURNING *"
        row = _row(self.raw.fetch_one(sql, params))
        if row is not None:
            self._new.add((table, str(row["id"])))
        return row

    def update(self, table, entity_id, values, *, bump=True):
        if not values and not bump:
            return self.get(table, entity_id)
        entries = [f"{_identifier(key)}=%s" for key in values]
        params = [Jsonb(value) if isinstance(value, dict) else value for value in values.values()]
        marker = (table, str(entity_id))
        if bump and marker not in self._bumped and marker not in self._new:
            entries.append("version=version+1")
            self._bumped.add(marker)
        entries.append("updated_at=now()")
        params.append(entity_id)
        row = _row(self.raw.fetch_one(f"UPDATE {self.table(table)} SET {','.join(entries)} WHERE id=%s RETURNING *", tuple(params)))
        if row is None:
            raise CashError("cash_not_found", "现金记录不存在或已删除。", 404)
        return row

    def delete(self, table, entity_id):
        count = self.raw.execute(f"DELETE FROM {self.table(table)} WHERE id=%s", (entity_id,))
        if count:
            self._deleted.add((table, str(entity_id)))
        return count

    def was_deleted(self, entity_type, entity_id):
        return self.raw.fetch_one("SELECT id FROM cash.deleted_submission_ids WHERE entity_type=%s AND id=%s", (entity_type, entity_id)) is not None

    def remember_deleted(self, entity_type, entity_id):
        self.raw.execute("INSERT INTO cash.deleted_submission_ids(entity_type,id) VALUES (%s,%s) ON CONFLICT (entity_type,id) DO NOTHING", (entity_type, entity_id))

    def relations(self, *, flow_ids=(), item_ids=()):
        """Bounded relation graph for explicit mutation roots, not whole-pool loading."""
        flows = sorted(set(flow_ids))
        items = sorted(set(item_ids))
        owned = [_row(row) for row in self.raw.fetch_all("SELECT * FROM cash.items WHERE origin_flow_id=ANY(%s::uuid[]) ORDER BY id", (flows,))] if flows else []
        item_ids = sorted(set(items) | {row["id"] for row in owned})
        settlements = [_row(row) for row in self.raw.fetch_all("SELECT * FROM cash.settlements WHERE flow_id=ANY(%s::uuid[]) OR item_id=ANY(%s::uuid[]) OR source_item_id=ANY(%s::uuid[]) ORDER BY id", (flows, item_ids, item_ids))]
        refs = [_row(row) for row in self.raw.fetch_all("SELECT * FROM cash.items WHERE related_obligation_id=ANY(%s::uuid[]) OR ticket_source_id=ANY(%s::uuid[]) ORDER BY id", (item_ids, item_ids))] if item_ids else []
        all_items = set(item_ids) | {row["id"] for row in refs}
        all_flows = set(flows)
        for settlement in settlements:
            all_items.update(value for value in (settlement["item_id"], settlement["source_item_id"]) if value)
            if settlement["flow_id"]:
                all_flows.add(settlement["flow_id"])
        return {"flow_ids": sorted(all_flows), "item_ids": sorted(all_items), "owned": owned, "settlements": settlements, "references": refs}

    def settlements_for_items(self, ids):
        ids = sorted(set(ids))
        if not ids:
            return []
        return [_row(row) for row in self.raw.fetch_all("SELECT * FROM cash.settlements WHERE item_id=ANY(%s::uuid[]) OR source_item_id=ANY(%s::uuid[]) ORDER BY id", (ids, ids))]

    def flow_budget(self, flow_id):
        return self.raw.fetch_one("""
          SELECT coalesce((SELECT sum(original_amount) FROM cash.items WHERE origin_flow_id=%s AND type='loan'),0)
            +coalesce((SELECT sum(amount) FROM cash.settlements WHERE flow_id=%s AND kind IN ('cash_repayment','company_collection')),0) AS obligation,
           coalesce((SELECT sum(original_amount) FROM cash.items WHERE origin_flow_id=%s AND type='expense'),0)
            +coalesce((SELECT sum(amount) FROM cash.settlements WHERE flow_id=%s AND kind IN ('expense_payment','expense_refund')),0) AS expense
        """, (flow_id, flow_id, flow_id, flow_id))

    def earliest_account_flow(self, account_id):
        return self.raw.fetch_one("SELECT min(occurred_on) AS day FROM cash.flows WHERE from_account_id=%s OR to_account_id=%s", (account_id, account_id))["day"]

    def account_is_referenced(self, account_id):
        return self.raw.fetch_one("SELECT EXISTS(SELECT 1 FROM cash.flows WHERE from_account_id=%s OR to_account_id=%s) OR EXISTS(SELECT 1 FROM cash.task_templates WHERE default_account_id=%s) AS used", (account_id, account_id, account_id))["used"]

    def category_is_referenced(self, category_id):
        return self.raw.fetch_one("SELECT EXISTS(SELECT 1 FROM cash.flows WHERE category_id=%s) OR EXISTS(SELECT 1 FROM cash.task_templates WHERE default_category_id=%s) AS used", (category_id, category_id))["used"]

    def personal_items(self):
        return [_row(row) for row in self.raw.fetch_all("SELECT * FROM cash.items WHERE ledger_group='personal' ORDER BY id")]


class CashRepository:
    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Cash requires its own PostgreSQL connection.")
        self.connection = connection

    @contextmanager
    def transaction(self, readonly=False):
        with self.connection.transaction() as raw:
            if readonly:
                raw.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            raw.execute("SET LOCAL lock_timeout='500ms'")
            yield CashTransaction(raw)
