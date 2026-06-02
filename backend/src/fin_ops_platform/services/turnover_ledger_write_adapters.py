from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.services.turnover_ledger_write_facade import TurnoverLedgerWriteFacade
from fin_ops_platform.services.turnover_ledger_write_uow import TurnoverLedgerWriteUnitOfWork


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


class TurnoverLedgerLocalTagSelectionConnection:
    def __init__(
        self,
        *,
        settings_snapshot_provider: Callable[[], dict[str, object]],
        save_snapshot: Callable[[dict[str, object]], None],
        refresh_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._settings_snapshot_provider = settings_snapshot_provider
        self._save_snapshot = save_snapshot
        self._refresh_snapshot = refresh_snapshot

    @contextmanager
    def transaction(self) -> Any:
        previous_snapshot = dict(self._settings_snapshot_provider() or {})
        try:
            yield SimpleNamespace()
        except Exception:
            self._save_snapshot(dict(previous_snapshot))
            self._refresh_snapshot(dict(previous_snapshot))
            raise


class TurnoverLedgerLocalTagSelectionSettingsWriter:
    def __init__(
        self,
        *,
        save_snapshot: Callable[[dict[str, object]], None],
        refresh_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._save_snapshot = save_snapshot
        self._refresh_snapshot = refresh_snapshot

    def save_tag_selection_settings(
        self,
        *,
        next_snapshot: dict[str, object],
        audit_event: dict[str, object],
        transaction: Any,
    ) -> None:
        _ = audit_event, transaction
        snapshot = dict(next_snapshot)
        self._save_snapshot(snapshot)
        self._refresh_snapshot(snapshot)


class TurnoverLedgerLocalTagSelectionAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        app_settings_service: Any,
        refresh_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._state_store = state_store
        self._app_settings_service = app_settings_service
        self._refresh_snapshot = refresh_snapshot

    def connection(self) -> TurnoverLedgerLocalTagSelectionConnection:
        return TurnoverLedgerLocalTagSelectionConnection(
            settings_snapshot_provider=self.settings_snapshot,
            save_snapshot=self.save_snapshot,
            refresh_snapshot=self._refresh_snapshot,
        )

    def settings_writer(self) -> TurnoverLedgerLocalTagSelectionSettingsWriter:
        return TurnoverLedgerLocalTagSelectionSettingsWriter(
            save_snapshot=self.save_snapshot,
            refresh_snapshot=self._refresh_snapshot,
        )

    def settings_snapshot(self) -> dict[str, object]:
        return dict(getattr(self._app_settings_service, "_snapshot", {}) or {})

    def save_snapshot(self, snapshot: dict[str, object]) -> None:
        self._state_store.save_app_settings(dict(snapshot))


class TurnoverLedgerTagSelectionLegacyFallbackFacade:
    def __init__(
        self,
        *,
        app_settings_service: Any,
        clear_read_model: Callable[[], None],
        enqueue_refresh: Callable[[list[str]], None],
    ) -> None:
        self._app_settings_service = app_settings_service
        self._clear_read_model = clear_read_model
        self._enqueue_refresh = enqueue_refresh

    def update_tag_selection(
        self,
        *,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str],
    ) -> dict[str, object]:
        _ = tenant_id
        result = self._app_settings_service.update_turnover_ledger_tag_selection(
            payload,
            actor_id=actor_id,
        )
        self._clear_read_model()
        self._enqueue_refresh(list(scope_keys or ["all"]))
        return result


class TurnoverLedgerTagSelectionLegacyFallbackAdapterSet:
    def __init__(
        self,
        *,
        app_settings_service: Any,
        clear_read_model: Callable[[], None],
        enqueue_refresh: Callable[..., None],
    ) -> None:
        self._app_settings_service = app_settings_service
        self._clear_read_model = clear_read_model
        self._enqueue_refresh = enqueue_refresh

    def facade(self) -> TurnoverLedgerTagSelectionLegacyFallbackFacade:
        return TurnoverLedgerTagSelectionLegacyFallbackFacade(
            app_settings_service=self._app_settings_service,
            clear_read_model=self._clear_read_model,
            enqueue_refresh=self.enqueue_refresh,
        )

    def enqueue_refresh(self, scope_keys: list[str]) -> None:
        self._enqueue_refresh(
            list(scope_keys or []),
            reason="turnover_ledger_tag_selection_changed",
        )


class TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder:
    def __init__(
        self,
        *,
        state_store: Any,
        queue_repository: Any,
        app_settings_service: Any,
        refresh_snapshot: Callable[[dict[str, object]], None],
        tenant_id: str,
        postgres_settings_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._app_settings_service = app_settings_service
        self._refresh_snapshot = refresh_snapshot
        self._tenant_id = tenant_id
        self._postgres_settings_repository_factory = postgres_settings_repository_factory

    def build(self) -> TurnoverLedgerWriteFacade | None:
        storage_backend = str(getattr(self._state_store, "storage_backend", "") or "").strip()
        if storage_backend == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
            if connection is None or not callable(enqueue_in_transaction):
                return None
            settings_port = TurnoverLedgerTagSelectionSettingsAdapter(
                repository_factory=self._postgres_settings_repository_factory
            )
            dirty_outbox_writer = TurnoverLedgerDirtyOutboxWriter(
                queue_repository=self._queue_repository,
                tenant_id=self._tenant_id,
            )
        else:
            local_adapters = TurnoverLedgerLocalTagSelectionAdapterSet(
                state_store=self._state_store,
                app_settings_service=self._app_settings_service,
                refresh_snapshot=self._refresh_snapshot,
            )
            connection = local_adapters.connection()
            settings_port = local_adapters.settings_writer()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=SimpleNamespace(),
            extra_repository=SimpleNamespace(),
            settings_port=settings_port,
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
        )
        return TurnoverLedgerWriteFacade(
            uow=uow,
            app_settings_service=self._app_settings_service,
        )


class TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder:
    def __init__(
        self,
        *,
        state_store: Any,
        queue_repository: Any,
        relation_service: Any,
        routes: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
        tenant_id: str,
        persistence_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._relation_service = relation_service
        self._routes = routes
        self._bank_rows_provider = bank_rows_provider
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning
        self._tenant_id = tenant_id
        self._persistence_repository_factory = persistence_repository_factory

    def build(self) -> TurnoverLedgerWriteFacade | None:
        storage_backend = str(getattr(self._state_store, "storage_backend", "") or "").strip()
        if storage_backend == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
            if connection is None or not callable(enqueue_in_transaction):
                return None
            relation_repository = TurnoverLedgerRelationWritePort(
                relation_service=self._relation_service,
                routes=self._routes,
                bank_rows_provider=self._bank_rows_provider,
                persistence_repository_factory=self._persistence_repository_factory,
            )
            dirty_outbox_writer = TurnoverLedgerDirtyOutboxWriter(
                queue_repository=self._queue_repository,
                tenant_id=self._tenant_id,
            )
        else:
            enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
            if not callable(enqueue):
                return None
            local_adapters = TurnoverLedgerLocalWithdrawRelationAdapterSet(
                state_store=self._state_store,
                relation_service=self._relation_service,
                routes=self._routes,
                replace_snapshot=self._replace_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = local_adapters.connection()
            relation_repository = local_adapters.relation_repository()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=relation_repository,
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
        )
        return TurnoverLedgerWriteFacade(uow=uow)


class TurnoverLedgerConfirmPrimaryWriteFacadeBuilder:
    def __init__(
        self,
        *,
        state_store: Any,
        queue_repository: Any,
        relation_service: Any,
        routes: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
        tenant_id: str,
        persistence_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._relation_service = relation_service
        self._routes = routes
        self._bank_rows_provider = bank_rows_provider
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning
        self._tenant_id = tenant_id
        self._persistence_repository_factory = persistence_repository_factory

    def build(self) -> TurnoverLedgerWriteFacade | None:
        storage_backend = str(getattr(self._state_store, "storage_backend", "") or "").strip()
        if storage_backend == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
            if connection is None or not callable(enqueue_in_transaction):
                return None
            relation_repository = TurnoverLedgerRelationWritePort(
                relation_service=self._relation_service,
                routes=self._routes,
                bank_rows_provider=self._bank_rows_provider,
                persistence_repository_factory=self._persistence_repository_factory,
            )
            dirty_outbox_writer = TurnoverLedgerDirtyOutboxWriter(
                queue_repository=self._queue_repository,
                tenant_id=self._tenant_id,
            )
        else:
            enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
            if not callable(enqueue):
                return None
            local_adapters = TurnoverLedgerLocalConfirmRelationAdapterSet(
                state_store=self._state_store,
                relation_service=self._relation_service,
                routes=self._routes,
                bank_rows_provider=self._bank_rows_provider,
                replace_snapshot=self._replace_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = local_adapters.connection()
            relation_repository = local_adapters.relation_repository()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=relation_repository,
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
        )
        return TurnoverLedgerWriteFacade(uow=uow)


class TurnoverLedgerBankRowTagsPrimaryWriteFacadeBuilder:
    def __init__(
        self,
        *,
        state_store: Any,
        queue_repository: Any,
        category_service: Any,
        relation_service: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        replace_category_snapshot: Callable[[dict[str, object]], None],
        replace_relation_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
        tenant_id: str,
        persistence_repository_factory: Callable[[Any], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._category_service = category_service
        self._relation_service = relation_service
        self._bank_rows_provider = bank_rows_provider
        self._replace_category_snapshot = replace_category_snapshot
        self._replace_relation_snapshot = replace_relation_snapshot
        self._emit_persistence_warning = emit_persistence_warning
        self._tenant_id = tenant_id
        self._persistence_repository_factory = persistence_repository_factory

    def build(self) -> TurnoverLedgerWriteFacade | None:
        storage_backend = str(getattr(self._state_store, "storage_backend", "") or "").strip()
        if storage_backend == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
            if connection is None or not callable(enqueue_in_transaction):
                return None
            bankdetail_port = TurnoverLedgerBankdetailWritePort(
                category_service=self._category_service,
                relation_service=self._relation_service,
                bank_rows_provider=self._bank_rows_provider,
                persistence_repository_factory=self._persistence_repository_factory,
            )
            dirty_outbox_writer = TurnoverLedgerDirtyOutboxWriter(
                queue_repository=self._queue_repository,
                tenant_id=self._tenant_id,
            )
        else:
            enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
            if not callable(enqueue):
                return None
            local_adapters = TurnoverLedgerLocalBankRowTagsAdapterSet(
                state_store=self._state_store,
                category_service=self._category_service,
                relation_service=self._relation_service,
                bank_rows_provider=self._bank_rows_provider,
                replace_category_snapshot=self._replace_category_snapshot,
                replace_relation_snapshot=self._replace_relation_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = local_adapters.connection()
            bankdetail_port = local_adapters.bankdetail_port()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=SimpleNamespace(),
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=bankdetail_port,
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
        )
        return TurnoverLedgerWriteFacade(uow=uow)


class TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder:
    def __init__(
        self,
        *,
        state_store: Any,
        queue_repository: Any,
        routes: Any,
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
        extra_service: Any,
        row_provider: Callable[..., dict[str, object] | None],
        tenant_id: str,
        postgres_extra_repository_factory: Callable[[Any], Any],
        postgres_idempotency_store_factory: Callable[[Any], Any],
        local_idempotency_store_provider: Callable[[], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._routes = routes
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning
        self._extra_service = extra_service
        self._row_provider = row_provider
        self._tenant_id = tenant_id
        self._postgres_extra_repository_factory = postgres_extra_repository_factory
        self._postgres_idempotency_store_factory = postgres_idempotency_store_factory
        self._local_idempotency_store_provider = local_idempotency_store_provider

    def build(self) -> TurnoverLedgerWriteFacade | None:
        storage_backend = str(getattr(self._state_store, "storage_backend", "") or "").strip()
        if storage_backend == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            enqueue_in_transaction = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
            if connection is None or not callable(enqueue_in_transaction):
                return None
            extra_repository = TurnoverLedgerExtraRepositoryAdapter(
                repository_factory=self._postgres_extra_repository_factory
            )
            dirty_outbox_writer = TurnoverLedgerDirtyOutboxWriter(
                queue_repository=self._queue_repository,
                tenant_id=self._tenant_id,
            )
            idempotency_store = self._postgres_idempotency_store_factory(connection)
        else:
            enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
            if not callable(enqueue):
                return None
            local_adapters = TurnoverLedgerLocalRelationExtraAdapterSet(
                state_store=self._state_store,
                routes=self._routes,
                replace_snapshot=self._replace_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = local_adapters.connection()
            extra_repository = local_adapters.extra_repository()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
            idempotency_store = self._local_idempotency_store_provider()
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=SimpleNamespace(),
            extra_repository=extra_repository,
            settings_port=SimpleNamespace(),
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
            idempotency_store=idempotency_store,
        )
        return TurnoverLedgerWriteFacade(
            uow=uow,
            extra_normalizer=TurnoverLedgerExtraNormalizerAdapter(
                extra_service=self._extra_service,
            ),
            row_provider=self._row_provider,
        )


class TurnoverLedgerLocalRelationExtraAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        routes: Any,
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
    ) -> None:
        self._state_store = state_store
        self._routes = routes
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning

    def connection(self) -> "TurnoverLedgerLocalRelationExtraConnection":
        return TurnoverLedgerLocalRelationExtraConnection(
            extras_snapshot_provider=self.extras_snapshot,
            replace_snapshot=self._replace_snapshot,
            save_snapshot=self.save_snapshot,
        )

    def extra_repository(self) -> "TurnoverLedgerLocalExtraRepository":
        return TurnoverLedgerLocalExtraRepository(
            extras_snapshot_provider=self.extras_snapshot,
            replace_snapshot=self._replace_snapshot,
        )

    def extras_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._routes, "extras_snapshot", None)
        if callable(snapshot):
            return dict(snapshot() or {})
        return {}

    def save_snapshot(self, snapshot: dict[str, object]) -> None:
        save_extras = getattr(self._state_store, "save_turnover_ledger_extras", None)
        if not callable(save_extras):
            raise RuntimeError("state store must expose save_turnover_ledger_extras.")
        try:
            save_extras(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_ledger_extra_updated",
                detail=str(exc),
            )


class TurnoverLedgerRelationExtraLegacyFallbackFacade:
    def __init__(
        self,
        *,
        routes: Any,
        persist_extra: Callable[[], None],
        clear_read_model: Callable[[], None],
        enqueue_refresh: Callable[[list[str]], None],
    ) -> None:
        self._routes = routes
        self._persist_extra = persist_extra
        self._clear_read_model = clear_read_model
        self._enqueue_refresh = enqueue_refresh

    def update_relation_extra(
        self,
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str],
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, expected_versions, idempotency_key
        result = self._routes.update_relation_extra(
            relation_id,
            payload,
            actor=actor_id,
        )
        self._persist_extra()
        self._clear_read_model()
        self._enqueue_refresh(list(scope_keys or ["all"]))
        return result


class TurnoverLedgerRelationExtraLegacyFallbackAdapterSet:
    def __init__(
        self,
        *,
        routes: Any,
        persist_extra_best_effort: Callable[..., None],
        clear_read_model: Callable[[], None],
        enqueue_refresh: Callable[..., None],
    ) -> None:
        self._routes = routes
        self._persist_extra_best_effort = persist_extra_best_effort
        self._clear_read_model = clear_read_model
        self._enqueue_refresh = enqueue_refresh

    def facade(self) -> TurnoverLedgerRelationExtraLegacyFallbackFacade:
        return TurnoverLedgerRelationExtraLegacyFallbackFacade(
            routes=self._routes,
            persist_extra=self.persist_extra,
            clear_read_model=self._clear_read_model,
            enqueue_refresh=self.enqueue_refresh,
        )

    def persist_extra(self) -> None:
        self._persist_extra_best_effort(operation="turnover_ledger_extra_updated")

    def enqueue_refresh(self, scope_keys: list[str]) -> None:
        self._enqueue_refresh(
            list(scope_keys or []),
            reason="turnover_relation_extra_changed",
        )


class TurnoverLedgerRelationMutationInvalidationLegacyAdapter:
    def __init__(
        self,
        *,
        persist_relations: Callable[..., None],
        invalidate_workbench_after_category_mutation: Callable[[list[str]], bool],
        clear_read_model: Callable[[], None],
        enqueue_refresh: Callable[..., bool],
    ) -> None:
        self._persist_relations = persist_relations
        self._invalidate_workbench_after_category_mutation = invalidate_workbench_after_category_mutation
        self._clear_read_model = clear_read_model
        self._enqueue_refresh = enqueue_refresh

    def after_relation_mutation(self, affected_months: list[str]) -> None:
        self._persist_relations(operation="turnover_relation_mutation_pre_invalidation")
        self._invalidate_workbench_after_category_mutation(list(affected_months or []))
        self._persist_relations(operation="turnover_relation_mutation")
        self._clear_read_model()
        self._enqueue_refresh(
            ["all"],
            reason="turnover_relation_changed",
        )


class TurnoverLedgerConfirmLegacyFallbackFacade:
    def __init__(
        self,
        *,
        relation_rebuild: Callable[[], None],
        routes: Any,
        after_mutation: Callable[[list[str]], None],
    ) -> None:
        self._relation_rebuild = relation_rebuild
        self._routes = routes
        self._after_mutation = after_mutation

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
    ) -> dict[str, object]:
        _ = tenant_id
        self._relation_rebuild()
        result = self._routes.confirm_relation(
            bank_row_ids=list(bank_row_ids or []),
            actor=actor_id,
            note=note,
        )
        self._after_mutation(list(affected_months or []))
        return dict(result or {})


class TurnoverLedgerConfirmLegacyFallbackAdapterSet:
    def __init__(
        self,
        *,
        relation_service: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        routes: Any,
        after_mutation: Callable[[list[str]], None],
    ) -> None:
        self._relation_service = relation_service
        self._bank_rows_provider = bank_rows_provider
        self._routes = routes
        self._after_mutation = after_mutation

    def facade(self) -> TurnoverLedgerConfirmLegacyFallbackFacade:
        return TurnoverLedgerConfirmLegacyFallbackFacade(
            relation_rebuild=self.relation_rebuild,
            routes=self._routes,
            after_mutation=self._after_mutation,
        )

    def relation_rebuild(self) -> None:
        rebuild = getattr(self._relation_service, "rebuild_from_bank_rows", None)
        if callable(rebuild):
            rebuild(self._bank_rows_provider())


class TurnoverLedgerWithdrawLegacyFallbackFacade:
    def __init__(
        self,
        *,
        routes: Any,
        after_mutation: Callable[[list[str]], None],
    ) -> None:
        self._routes = routes
        self._after_mutation = after_mutation

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, expected_versions
        result = self._routes.withdraw_relation(
            relation_id=relation_id,
            actor=actor_id,
            note=note,
        )
        self._after_mutation(list(affected_months or []))
        return dict(result or {})


class TurnoverLedgerBankRowTagsLegacyFallbackFacade:
    def __init__(
        self,
        *,
        category_service: Any,
        save_category_snapshot: Callable[[dict[str, object]], None],
        relation_rebuild: Callable[[list[dict[str, object]]], None],
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        after_mutation: Callable[[list[str]], None],
    ) -> None:
        self._category_service = category_service
        self._save_category_snapshot = save_category_snapshot
        self._relation_rebuild = relation_rebuild
        self._bank_rows_provider = bank_rows_provider
        self._after_mutation = after_mutation

    def update_bank_row_tags_batch(
        self,
        *,
        updates: list[dict[str, object]],
        actor_id: str,
        tenant_id: str,
        affected_months: list[str],
    ) -> dict[str, object]:
        _ = tenant_id
        result = self._category_service.apply_turnover_updates(
            [dict(update) for update in list(updates or [])],
            actor=actor_id,
        )
        self._save_category_snapshot(dict(self._category_service.snapshot() or {}))
        self._relation_rebuild([dict(row) for row in list(self._bank_rows_provider() or [])])
        self._after_mutation(list(affected_months or []))
        return dict(result or {})


class TurnoverLedgerBankRowTagsLegacyFallbackAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        category_service: Any,
        relation_rebuild: Callable[[list[dict[str, object]]], None],
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        after_mutation: Callable[[list[str]], None],
    ) -> None:
        self._state_store = state_store
        self._category_service = category_service
        self._relation_rebuild = relation_rebuild
        self._bank_rows_provider = bank_rows_provider
        self._after_mutation = after_mutation

    def facade(self) -> TurnoverLedgerBankRowTagsLegacyFallbackFacade:
        return TurnoverLedgerBankRowTagsLegacyFallbackFacade(
            category_service=self._category_service,
            save_category_snapshot=self.save_category_snapshot,
            relation_rebuild=self._relation_rebuild,
            bank_rows_provider=self._bank_rows_provider,
            after_mutation=self._after_mutation,
        )

    def save_category_snapshot(self, snapshot: dict[str, object]) -> None:
        self._state_store.save_bank_transaction_categories(dict(snapshot))


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
        self._rebuild_relation_snapshot()
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

    def _rebuild_relation_snapshot(self) -> None:
        rebuild = getattr(self._relation_service, "rebuild_from_bank_rows", None)
        if not callable(rebuild):
            raise RuntimeError("relation_service must expose rebuild_from_bank_rows.")
        rebuild([dict(row) for row in list(self._bank_rows_provider() or [])])

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


class TurnoverLedgerLocalDirtyOutboxWriter:
    def __init__(self, *, queue_repository: Any) -> None:
        self._queue_repository = queue_repository

    def enqueue_refresh(
        self,
        *,
        transaction: Any,
        scope_type: str,
        scope_keys: list[str],
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> list[Any]:
        _ = transaction, payload
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh.")
        events: list[Any] = []
        refresh_reason = (
            "turnover_relation_extra_changed"
            if reason == "relation_extra_update"
            else reason
        )
        for scope_key in list(scope_keys or ["all"]):
            events.append(
                enqueue(
                    scope_type=scope_type,
                    scope_key=str(scope_key or "all"),
                    reason=refresh_reason,
                )
            )
        return events


class TurnoverLedgerLocalRelationExtraConnection:
    def __init__(
        self,
        *,
        extras_snapshot_provider: Callable[[], dict[str, object]],
        replace_snapshot: Callable[[dict[str, object]], None],
        save_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._extras_snapshot_provider = extras_snapshot_provider
        self._replace_snapshot = replace_snapshot
        self._save_snapshot = save_snapshot

    @contextmanager
    def transaction(self) -> Any:
        previous_snapshot = dict(self._extras_snapshot_provider() or {})
        try:
            yield SimpleNamespace()
        except Exception:
            self._replace_snapshot(dict(previous_snapshot))
            self._save_snapshot(dict(previous_snapshot))
            raise
        else:
            current_snapshot = dict(self._extras_snapshot_provider() or {})
            self._save_snapshot(current_snapshot)


class TurnoverLedgerLocalExtraRepository:
    def __init__(
        self,
        *,
        extras_snapshot_provider: Callable[[], dict[str, object]],
        replace_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._extras_snapshot_provider = extras_snapshot_provider
        self._replace_snapshot = replace_snapshot

    def save_extra(self, extra: dict[str, object], *, transaction: Any) -> None:
        _ = transaction
        relation_id = str(extra.get("relation_id") or "").strip()
        if not relation_id:
            raise ValueError("relation_id is required.")
        current_snapshot = dict(self._extras_snapshot_provider() or {})
        extras = [
            dict(item)
            for item in list(current_snapshot.get("extras") or [])
            if isinstance(item, dict) and str(item.get("relation_id") or "").strip() != relation_id
        ]
        extras.append(dict(extra))
        self._replace_snapshot(
            {
                "version": current_snapshot.get("version") or 1,
                "extras": extras,
            }
        )


class TurnoverLedgerLocalRelationConnection:
    def __init__(
        self,
        *,
        relation_snapshot_provider: Callable[[], dict[str, object]],
        replace_snapshot: Callable[[dict[str, object]], None],
        save_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._relation_snapshot_provider = relation_snapshot_provider
        self._replace_snapshot = replace_snapshot
        self._save_snapshot = save_snapshot

    @contextmanager
    def transaction(self) -> Any:
        previous_snapshot = dict(self._relation_snapshot_provider() or {})
        try:
            yield SimpleNamespace()
        except Exception:
            self._replace_snapshot(dict(previous_snapshot))
            self._save_snapshot(dict(previous_snapshot))
            raise
        else:
            current_snapshot = dict(self._relation_snapshot_provider() or {})
            self._save_snapshot(current_snapshot)


class TurnoverLedgerLocalRelationRepository:
    def __init__(
        self,
        *,
        routes: Any,
        relation_rebuild: Callable[[], None] | None = None,
    ) -> None:
        self._routes = routes
        self._relation_rebuild = relation_rebuild

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        _ = transaction
        if self._relation_rebuild is not None:
            self._relation_rebuild()
        return dict(
            self._routes.confirm_relation(
                bank_row_ids=list(bank_row_ids),
                actor=actor_id,
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
        _ = transaction
        return dict(
            self._routes.withdraw_relation(
                relation_id=relation_id,
                actor=actor_id,
                note=note,
            )
            or {}
        )


class TurnoverLedgerLocalConfirmRelationAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        relation_service: Any,
        routes: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
    ) -> None:
        self._state_store = state_store
        self._relation_service = relation_service
        self._routes = routes
        self._bank_rows_provider = bank_rows_provider
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning

    def connection(self) -> TurnoverLedgerLocalRelationConnection:
        return TurnoverLedgerLocalRelationConnection(
            relation_snapshot_provider=self.relation_snapshot,
            replace_snapshot=self._replace_snapshot,
            save_snapshot=self.save_snapshot,
        )

    def relation_repository(self) -> TurnoverLedgerLocalRelationRepository:
        return TurnoverLedgerLocalRelationRepository(
            routes=self._routes,
            relation_rebuild=self.rebuild_relations,
        )

    def relation_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._relation_service, "snapshot", None)
        if callable(snapshot):
            return dict(snapshot() or {})
        return {}

    def save_snapshot(self, snapshot: dict[str, object]) -> None:
        save_relations = getattr(self._state_store, "save_turnover_relations", None)
        if not callable(save_relations):
            raise RuntimeError("state store must expose save_turnover_relations.")
        try:
            save_relations(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_relations_updated",
                detail=str(exc),
            )

    def rebuild_relations(self) -> None:
        rebuild = getattr(self._relation_service, "rebuild_from_bank_rows", None)
        if callable(rebuild):
            rebuild(self._bank_rows_provider())


class TurnoverLedgerLocalWithdrawRelationAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        relation_service: Any,
        routes: Any,
        replace_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
    ) -> None:
        self._state_store = state_store
        self._relation_service = relation_service
        self._routes = routes
        self._replace_snapshot = replace_snapshot
        self._emit_persistence_warning = emit_persistence_warning

    def connection(self) -> TurnoverLedgerLocalRelationConnection:
        return TurnoverLedgerLocalRelationConnection(
            relation_snapshot_provider=self.relation_snapshot,
            replace_snapshot=self._replace_snapshot,
            save_snapshot=self.save_snapshot,
        )

    def relation_repository(self) -> TurnoverLedgerLocalRelationRepository:
        return TurnoverLedgerLocalRelationRepository(routes=self._routes)

    def relation_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._relation_service, "snapshot", None)
        if callable(snapshot):
            return dict(snapshot() or {})
        return {}

    def save_snapshot(self, snapshot: dict[str, object]) -> None:
        save_relations = getattr(self._state_store, "save_turnover_relations", None)
        if not callable(save_relations):
            raise RuntimeError("state store must expose save_turnover_relations.")
        try:
            save_relations(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_relations_updated",
                detail=str(exc),
            )


class TurnoverLedgerLocalBankRowTagsAdapterSet:
    def __init__(
        self,
        *,
        state_store: Any,
        category_service: Any,
        relation_service: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
        replace_category_snapshot: Callable[[dict[str, object]], None],
        replace_relation_snapshot: Callable[[dict[str, object]], None],
        emit_persistence_warning: Callable[..., None],
    ) -> None:
        self._state_store = state_store
        self._category_service = category_service
        self._relation_service = relation_service
        self._bank_rows_provider = bank_rows_provider
        self._replace_category_snapshot = replace_category_snapshot
        self._replace_relation_snapshot = replace_relation_snapshot
        self._emit_persistence_warning = emit_persistence_warning

    def connection(self) -> TurnoverLedgerLocalBankRowTagsConnection:
        return TurnoverLedgerLocalBankRowTagsConnection(
            category_snapshot_provider=self.category_snapshot,
            relation_snapshot_provider=self.relation_snapshot,
            replace_category_snapshot=self._replace_category_snapshot,
            replace_relation_snapshot=self._replace_relation_snapshot,
            save_category_snapshot=self.save_category_snapshot,
            save_relation_snapshot=self.save_relation_snapshot,
        )

    def bankdetail_port(self) -> TurnoverLedgerLocalBankdetailPort:
        return TurnoverLedgerLocalBankdetailPort(
            category_service=self._category_service,
            relation_service=self._relation_service,
            bank_rows_provider=self._bank_rows_provider,
        )

    def category_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._category_service, "snapshot", None)
        if callable(snapshot):
            return dict(snapshot() or {})
        return {}

    def relation_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._relation_service, "snapshot", None)
        if callable(snapshot):
            return dict(snapshot() or {})
        return {}

    def save_category_snapshot(self, snapshot: dict[str, object]) -> None:
        save_categories = getattr(self._state_store, "save_bank_transaction_categories", None)
        if not callable(save_categories):
            raise RuntimeError("state store must expose save_bank_transaction_categories.")
        try:
            save_categories(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="bank_transaction_categories_updated",
                detail=str(exc),
            )

    def save_relation_snapshot(self, snapshot: dict[str, object]) -> None:
        save_relations = getattr(self._state_store, "save_turnover_relations", None)
        if not callable(save_relations):
            raise RuntimeError("state store must expose save_turnover_relations.")
        try:
            save_relations(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_relations_updated",
                detail=str(exc),
            )


class TurnoverLedgerLocalBankRowTagsConnection:
    def __init__(
        self,
        *,
        category_snapshot_provider: Callable[[], dict[str, object]],
        relation_snapshot_provider: Callable[[], dict[str, object]],
        replace_category_snapshot: Callable[[dict[str, object]], None],
        replace_relation_snapshot: Callable[[dict[str, object]], None],
        save_category_snapshot: Callable[[dict[str, object]], None],
        save_relation_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._category_snapshot_provider = category_snapshot_provider
        self._relation_snapshot_provider = relation_snapshot_provider
        self._replace_category_snapshot = replace_category_snapshot
        self._replace_relation_snapshot = replace_relation_snapshot
        self._save_category_snapshot = save_category_snapshot
        self._save_relation_snapshot = save_relation_snapshot

    @contextmanager
    def transaction(self) -> Any:
        previous_category_snapshot = dict(self._category_snapshot_provider() or {})
        previous_relation_snapshot = dict(self._relation_snapshot_provider() or {})
        try:
            yield SimpleNamespace()
        except Exception:
            self._replace_category_snapshot(dict(previous_category_snapshot))
            self._replace_relation_snapshot(dict(previous_relation_snapshot))
            self._save_category_snapshot(dict(previous_category_snapshot))
            self._save_relation_snapshot(dict(previous_relation_snapshot))
            raise
        else:
            self._save_category_snapshot(dict(self._category_snapshot_provider() or {}))
            self._save_relation_snapshot(dict(self._relation_snapshot_provider() or {}))


class TurnoverLedgerLocalBankdetailPort:
    def __init__(
        self,
        *,
        category_service: Any,
        relation_service: Any,
        bank_rows_provider: Callable[[], list[dict[str, object]]],
    ) -> None:
        self._category_service = category_service
        self._relation_service = relation_service
        self._bank_rows_provider = bank_rows_provider

    def apply_turnover_category_updates(
        self,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
        transaction: Any,
    ) -> dict[str, object]:
        _ = transaction
        result = self._category_service.apply_turnover_updates(
            list(updates or []),
            actor=actor_id,
        )
        self._relation_service.rebuild_from_bank_rows(self._bank_rows_provider())
        return dict(result or {})


class TurnoverLedgerExtraNormalizerAdapter:
    def __init__(self, *, extra_service: Any) -> None:
        self._extra_service = extra_service

    def __call__(self, *, relation_id: str, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        normalize = getattr(self._extra_service, "normalize_update", None)
        if not callable(normalize):
            raise RuntimeError("extra_service must expose normalize_update.")
        return dict(normalize(relation_id, payload, actor=actor_id))
