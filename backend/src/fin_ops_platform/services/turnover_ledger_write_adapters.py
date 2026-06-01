from __future__ import annotations

from typing import Any, Callable


class TurnoverLedgerExtraRepositoryAdapter:
    def __init__(self, *, repository_factory: Callable[[Any], Any]) -> None:
        self._repository_factory = repository_factory

    def save_extra(self, extra: dict[str, object], *, transaction: Any) -> None:
        relation_id = str(extra.get("relation_id") or "").strip()
        if not relation_id:
            raise ValueError("relation_id is required.")
        repository = self._repository_factory(transaction)
        repository.save_turnover_ledger_extras({"extras": {relation_id: dict(extra)}})


class TurnoverLedgerTagSelectionSettingsAdapter:
    def __init__(
        self,
        *,
        repository_factory: Callable[[Any], Any] | None = None,
        writer: Callable[..., Any] | None = None,
    ) -> None:
        if repository_factory is None and writer is None:
            raise ValueError("repository_factory or writer is required.")
        self._repository_factory = repository_factory
        self._writer = writer

    def save_tag_selection_settings(
        self,
        *,
        next_snapshot: dict[str, object],
        audit_event: dict[str, object],
        transaction: Any,
    ) -> None:
        if self._writer is not None:
            self._writer(
                next_snapshot=dict(next_snapshot),
                audit_event=dict(audit_event),
                transaction=transaction,
            )
            return
        if self._repository_factory is None:
            raise RuntimeError("repository_factory is required.")
        repository = self._repository_factory(transaction)
        save_app_settings = getattr(repository, "save_app_settings", None)
        if callable(save_app_settings):
            save_app_settings(dict(next_snapshot))
        else:
            save_settings = getattr(repository, "save_settings", None)
            if not callable(save_settings):
                raise RuntimeError("settings repository must expose save_app_settings or save_settings.")
            save_settings("app_settings", dict(next_snapshot))
        append_audit = getattr(repository, "append_audit", None)
        if callable(append_audit):
            append_audit(dict(audit_event))


class TurnoverLedgerRelationRepositoryAdapter:
    def __init__(self, *, repository_factory: Callable[[Any], Any]) -> None:
        self._repository_factory = repository_factory

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        repository = self._repository_factory(transaction)
        confirm = getattr(repository, "confirm_relation", None)
        if not callable(confirm):
            raise RuntimeError("turnover relation repository must expose confirm_relation.")
        return dict(
            confirm(
                bank_row_ids=list(bank_row_ids or []),
                actor_id=actor_id,
                note=note,
            )
            or {}
        )

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        repository = self._repository_factory(transaction)
        withdraw = getattr(repository, "withdraw_relation", None)
        if not callable(withdraw):
            raise RuntimeError("turnover relation repository must expose withdraw_relation.")
        return dict(
            withdraw(
                relation_id=relation_id,
                actor_id=actor_id,
                note=note,
            )
            or {}
        )


class TurnoverLedgerBankdetailPortAdapter:
    def __init__(self, *, repository_factory: Callable[[Any], Any]) -> None:
        self._repository_factory = repository_factory

    def apply_turnover_category_updates(
        self,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
        transaction: Any,
    ) -> dict[str, object]:
        repository = self._repository_factory(transaction)
        apply_updates = getattr(repository, "apply_turnover_category_updates", None)
        if not callable(apply_updates):
            raise RuntimeError("bankdetail repository must expose apply_turnover_category_updates.")
        return dict(
            apply_updates(
                [dict(update) for update in list(updates or [])],
                actor_id=actor_id,
            )
            or {}
        )


class TurnoverLedgerRelationWritePort:
    def __init__(
        self,
        *,
        relation_service: Any,
        routes: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        persistence_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._relation_service = relation_service
        self._routes = routes
        self._bank_rows_provider = bank_rows_provider
        self._persistence_repository_factory = persistence_repository_factory

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        confirm = getattr(self._routes, "confirm_relation", None)
        if not callable(confirm):
            raise RuntimeError("turnover relation routes must expose confirm_relation.")
        result = dict(
            confirm(
                bank_row_ids=list(bank_row_ids or []),
                actor=actor_id,
                note=note,
            )
            or {}
        )
        rebuild = getattr(self._relation_service, "rebuild_from_bank_rows", None)
        if not callable(rebuild):
            raise RuntimeError("relation_service must expose rebuild_from_bank_rows.")
        rebuild([dict(row) for row in list(self._bank_rows_provider() or [])])
        self._save_relation_snapshot(transaction)
        return result

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        withdraw = getattr(self._routes, "withdraw_relation", None)
        if not callable(withdraw):
            raise RuntimeError("turnover relation routes must expose withdraw_relation.")
        result = dict(
            withdraw(
                relation_id=relation_id,
                actor=actor_id,
                note=note,
            )
            or {}
        )
        self._save_relation_snapshot(transaction)
        return result

    def _save_relation_snapshot(self, transaction: Any) -> None:
        snapshot = getattr(self._relation_service, "snapshot", None)
        if not callable(snapshot):
            raise RuntimeError("relation_service must expose snapshot.")
        repository = self._persistence_repository_factory(transaction)
        save = getattr(repository, "save_turnover_relations", None)
        if not callable(save):
            raise RuntimeError("turnover persistence repository must expose save_turnover_relations.")
        save(dict(snapshot() or {}))


class TurnoverLedgerBankdetailWritePort:
    def __init__(
        self,
        *,
        category_service: Any,
        relation_service: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        persistence_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._category_service = category_service
        self._relation_service = relation_service
        self._bank_rows_provider = bank_rows_provider
        self._persistence_repository_factory = persistence_repository_factory

    def apply_turnover_category_updates(
        self,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
        transaction: Any,
    ) -> dict[str, object]:
        apply_updates = getattr(self._category_service, "apply_turnover_updates", None)
        if not callable(apply_updates):
            raise RuntimeError("category_service must expose apply_turnover_updates.")
        result = dict(
            apply_updates(
                [dict(update) for update in list(updates or [])],
                actor=actor_id,
            )
            or {}
        )
        rebuild = getattr(self._relation_service, "rebuild_from_bank_rows", None)
        if not callable(rebuild):
            raise RuntimeError("relation_service must expose rebuild_from_bank_rows.")
        rebuild([dict(row) for row in list(self._bank_rows_provider() or [])])
        repository = self._persistence_repository_factory(transaction)
        save_categories = getattr(repository, "save_bank_transaction_categories", None)
        if not callable(save_categories):
            raise RuntimeError(
                "turnover persistence repository must expose save_bank_transaction_categories."
            )
        category_snapshot = getattr(self._category_service, "snapshot", None)
        if not callable(category_snapshot):
            raise RuntimeError("category_service must expose snapshot.")
        save_categories(dict(category_snapshot() or {}))
        save_relations = getattr(repository, "save_turnover_relations", None)
        if not callable(save_relations):
            raise RuntimeError("turnover persistence repository must expose save_turnover_relations.")
        relation_snapshot = getattr(self._relation_service, "snapshot", None)
        if not callable(relation_snapshot):
            raise RuntimeError("relation_service must expose snapshot.")
        save_relations(dict(relation_snapshot() or {}))
        return result


class TurnoverLedgerDirtyOutboxWriter:
    def __init__(
        self,
        *,
        queue_repository: Any,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> None:
        self._queue_repository = queue_repository
        self._tenant_id = str(tenant_id or "default")
        self._priority = str(priority or "normal")
        self._trace_id = str(trace_id).strip() if trace_id else None

    def enqueue_refresh(
        self,
        *,
        transaction: Any,
        scope_type: str,
        scope_keys: list[str],
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> list[Any]:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
        if not callable(enqueue):
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh_in_transaction.")
        events = []
        for scope_key in list(scope_keys or ["all"]):
            events.append(
                enqueue(
                    transaction=transaction,
                    scope_type=scope_type,
                    scope_key=str(scope_key or "all"),
                    reason=reason,
                    tenant_id=self._tenant_id,
                    priority=self._priority,
                    trace_id=self._trace_id,
                )
            )
        return events


class TurnoverLedgerExtraNormalizerAdapter:
    def __init__(self, *, extra_service: Any) -> None:
        self._extra_service = extra_service

    def __call__(self, *, relation_id: str, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        normalize = getattr(self._extra_service, "normalize_update", None)
        if not callable(normalize):
            raise RuntimeError("extra_service must expose normalize_update.")
        return dict(normalize(relation_id, payload, actor=actor_id))
