from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.read_model_scope_policy import (
    DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ReadModelScopePolicyRegistry,
)
from fin_ops_platform.services.turnover_bank_row_version import turnover_bank_row_version
from fin_ops_platform.services.turnover_ledger_write_facade import TurnoverLedgerWriteFacade
from fin_ops_platform.services.turnover_ledger_write_uow import TurnoverLedgerWriteUnitOfWork
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_distribution_mapper import relation_dicts_from_distribution_payload

TURNOVER_MANUAL_CLOSURE_RELATION_MODE = "turnover_manual_closure"


class TurnoverLedgerWritePreconditionError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = 409
        self.error_code = error_code
        self.payload = dict(payload or {})


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


class TurnoverLedgerLocalRuntimeSupport:
    def __init__(
        self,
        *,
        app_settings_service: Any,
        bank_details_service: Any,
        turnover_ledger_service: Any,
        turnover_ledger_api_routes: Any,
        live_workbench_service: Any,
        category_service_from_snapshot: Callable[[dict[str, object]], Any],
        auto_category_service_factory: Callable[[Any], Any],
        effective_category_provider_factory: Callable[[Any, Any], Any],
        relation_service_from_snapshot: Callable[[dict[str, object]], Any],
        extra_service_builder: Callable[[object], object],
        emit_persistence_warning: Callable[..., None],
        postgres_repository_factory: Callable[[Any], Any],
        category_service_rebinder: Callable[[Any, Any, Any], None] | None = None,
        relation_service_rebinder: Callable[[Any], None] | None = None,
        extra_service_rebinder: Callable[[Any], None] | None = None,
    ) -> None:
        self._app_settings_service = app_settings_service
        self._bank_details_service = bank_details_service
        self._turnover_ledger_service = turnover_ledger_service
        self._turnover_ledger_api_routes = turnover_ledger_api_routes
        self._live_workbench_service = live_workbench_service
        self._category_service_from_snapshot = category_service_from_snapshot
        self._auto_category_service_factory = auto_category_service_factory
        self._effective_category_provider_factory = effective_category_provider_factory
        self._relation_service_from_snapshot = relation_service_from_snapshot
        self._extra_service_builder = extra_service_builder
        self._emit_persistence_warning = emit_persistence_warning
        self._postgres_repository_factory = postgres_repository_factory
        self._category_service_rebinder = category_service_rebinder
        self._relation_service_rebinder = relation_service_rebinder
        self._extra_service_rebinder = extra_service_rebinder
        self._current_category_service: Any = None
        self._current_auto_category_service: Any = None
        self._current_effective_category_provider: Any = None
        self._current_relation_service: Any = None
        self._current_extra_service: Any = None

    @property
    def category_service(self) -> Any:
        return self._current_category_service

    @property
    def auto_category_service(self) -> Any:
        return self._current_auto_category_service

    @property
    def effective_category_provider(self) -> Any:
        return self._current_effective_category_provider

    @property
    def relation_service(self) -> Any:
        return self._current_relation_service

    @property
    def extra_service(self) -> Any:
        return self._current_extra_service

    def persistence_repository(self, transaction: object, *, state_store: object) -> object:
        if callable(getattr(transaction, "execute", None)):
            return self._postgres_repository_factory(transaction)
        return state_store

    def replace_bank_transaction_category_snapshot(self, snapshot: dict[str, object]) -> None:
        category_service = self._category_service_from_snapshot(dict(snapshot))
        auto_category_service = self._auto_category_service_factory(category_service)
        effective_category_provider = self._effective_category_provider_factory(
            category_service,
            auto_category_service,
        )
        self._current_category_service = category_service
        self._current_auto_category_service = auto_category_service
        self._current_effective_category_provider = effective_category_provider
        if callable(self._category_service_rebinder):
            self._category_service_rebinder(
                category_service,
                auto_category_service,
                effective_category_provider,
            )
        if self._app_settings_service is not None:
            setattr(self._app_settings_service, "_bank_transaction_category_service", category_service)
            setattr(self._app_settings_service, "_bank_transaction_auto_category_service", auto_category_service)
        if self._bank_details_service is not None:
            setattr(self._bank_details_service, "_category_service", category_service)
            setattr(self._bank_details_service, "_auto_category_service", auto_category_service)
        if self._turnover_ledger_service is not None:
            setattr(self._turnover_ledger_service, "_category_service", category_service)
            setattr(self._turnover_ledger_service, "_category_provider", effective_category_provider)
        if self._live_workbench_service is not None:
            setattr(self._live_workbench_service, "_category_provider", effective_category_provider)

    def replace_turnover_relation_snapshot(self, snapshot: dict[str, object]) -> None:
        relation_service = self._relation_service_from_snapshot(dict(snapshot))
        self._current_relation_service = relation_service
        if callable(self._relation_service_rebinder):
            self._relation_service_rebinder(relation_service)
        if self._turnover_ledger_service is not None:
            setattr(self._turnover_ledger_service, "_relation_service", relation_service)
        if self._turnover_ledger_api_routes is not None:
            setattr(self._turnover_ledger_api_routes, "_relation_service", relation_service)

    def replace_turnover_ledger_extra_snapshot(self, snapshot: dict[str, object]) -> None:
        extra_service = self._extra_service_builder(snapshot)
        self._current_extra_service = extra_service
        if callable(self._extra_service_rebinder):
            self._extra_service_rebinder(extra_service)
        if self._turnover_ledger_api_routes is not None:
            setattr(self._turnover_ledger_api_routes, "_extra_service", extra_service)
        if self._turnover_ledger_service is not None:
            setattr(self._turnover_ledger_service, "_extra_service", extra_service)

    def refresh_app_settings_snapshot(self, snapshot: dict[str, object]) -> None:
        if self._app_settings_service is None:
            return
        setattr(self._app_settings_service, "_snapshot", dict(snapshot))
        configure_category_service = getattr(self._app_settings_service, "_configure_category_service", None)
        if callable(configure_category_service):
            configure_category_service(dict(snapshot))

    def save_bank_transaction_categories_snapshot(self, state_store: object, snapshot: dict[str, object]) -> None:
        save_categories = getattr(state_store, "save_bank_transaction_categories", None)
        if not callable(save_categories):
            raise RuntimeError("state store must expose save_bank_transaction_categories.")
        try:
            save_categories(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="bank_transaction_categories_updated",
                detail=str(exc),
            )

    def save_turnover_relations_snapshot(self, state_store: object, snapshot: dict[str, object]) -> None:
        save_relations = getattr(state_store, "save_turnover_relations", None)
        if not callable(save_relations):
            raise RuntimeError("state store must expose save_turnover_relations.")
        try:
            save_relations(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_relations_updated",
                detail=str(exc),
            )

    def save_turnover_ledger_extras_snapshot(self, state_store: object, snapshot: dict[str, object]) -> None:
        save_extras = getattr(state_store, "save_turnover_ledger_extras", None)
        if not callable(save_extras):
            raise RuntimeError("state store must expose save_turnover_ledger_extras.")
        try:
            save_extras(dict(snapshot))
        except Exception as exc:
            self._emit_persistence_warning(
                operation="turnover_ledger_extra_updated",
                detail=str(exc),
            )


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
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, idempotency_key
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
        postgres_idempotency_store_factory: Callable[[Any], Any],
        local_idempotency_store_provider: Callable[[], Any],
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._app_settings_service = app_settings_service
        self._refresh_snapshot = refresh_snapshot
        self._tenant_id = tenant_id
        self._postgres_settings_repository_factory = postgres_settings_repository_factory
        self._postgres_idempotency_store_factory = postgres_idempotency_store_factory
        self._local_idempotency_store_provider = local_idempotency_store_provider

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
            idempotency_store = self._postgres_idempotency_store_factory(connection)
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
            idempotency_store = self._local_idempotency_store_provider()
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=SimpleNamespace(),
            extra_repository=SimpleNamespace(),
            settings_port=settings_port,
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
            idempotency_store=idempotency_store,
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
        postgres_idempotency_store_factory: Callable[[Any], Any],
        local_idempotency_store_provider: Callable[[], Any],
        pair_relation_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
        relation_facade: Any | None = None,
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
        self._postgres_idempotency_store_factory = postgres_idempotency_store_factory
        self._local_idempotency_store_provider = local_idempotency_store_provider
        self._pair_relation_service = pair_relation_service
        self._relation_command_service_factory = relation_command_service_factory
        self._relation_facade = relation_facade

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
            idempotency_store = self._postgres_idempotency_store_factory(connection)
            workbench_pair_port = (
                TurnoverLedgerWorkbenchPairPort(
                    pair_relation_service=self._pair_relation_service,
                    relation_command_service_factory=self._relation_command_service_factory,
                    relation_facade=self._relation_facade,
                )
                if self._pair_relation_service is not None or self._relation_command_service_factory is not None
                else None
            )
        else:
            if not ReadModelRefreshGateway(queue_repository=self._queue_repository).can_enqueue():
                return None
            local_adapters = TurnoverLedgerLocalWithdrawRelationAdapterSet(
                state_store=self._state_store,
                relation_service=self._relation_service,
                routes=self._routes,
                replace_snapshot=self._replace_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = (
                TurnoverLedgerLocalClosureConnection(
                    relation_snapshot_provider=local_adapters.relation_snapshot,
                    replace_relation_snapshot=self._replace_snapshot,
                    save_relation_snapshot=local_adapters.save_snapshot,
                    pair_relation_service=self._pair_relation_service,
                    save_pair_snapshot=lambda snapshot: self._state_store.save_workbench_pair_relations(dict(snapshot)),
                )
                if self._pair_relation_service is not None
                else local_adapters.connection()
            )
            relation_repository = local_adapters.relation_repository()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
            idempotency_store = self._local_idempotency_store_provider()
            workbench_pair_port = (
                TurnoverLedgerWorkbenchPairPort(
                    pair_relation_service=self._pair_relation_service,
                    relation_command_service_factory=self._relation_command_service_factory,
                    relation_facade=self._relation_facade,
                )
                if self._pair_relation_service is not None or self._relation_command_service_factory is not None
                else None
            )
        stale_precondition_port = TurnoverLedgerRelationStalePreconditionPort(
            relation_detail_provider=self._routes.get_relation
        )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=relation_repository,
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=stale_precondition_port,
            idempotency_store=idempotency_store,
            workbench_pair_port=workbench_pair_port,
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
        postgres_idempotency_store_factory: Callable[[Any], Any],
        local_idempotency_store_provider: Callable[[], Any],
        pair_relation_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
        relation_facade: Any | None = None,
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
        self._postgres_idempotency_store_factory = postgres_idempotency_store_factory
        self._local_idempotency_store_provider = local_idempotency_store_provider
        self._pair_relation_service = pair_relation_service
        self._relation_command_service_factory = relation_command_service_factory
        self._relation_facade = relation_facade

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
            idempotency_store = self._postgres_idempotency_store_factory(connection)
            workbench_pair_port = (
                TurnoverLedgerWorkbenchPairPort(
                    pair_relation_service=self._pair_relation_service,
                    relation_command_service_factory=self._relation_command_service_factory,
                    relation_facade=self._relation_facade,
                )
                if self._pair_relation_service is not None or self._relation_command_service_factory is not None
                else None
            )
        else:
            if not ReadModelRefreshGateway(queue_repository=self._queue_repository).can_enqueue():
                return None
            local_adapters = TurnoverLedgerLocalConfirmRelationAdapterSet(
                state_store=self._state_store,
                relation_service=self._relation_service,
                routes=self._routes,
                bank_rows_provider=self._bank_rows_provider,
                replace_snapshot=self._replace_snapshot,
                emit_persistence_warning=self._emit_persistence_warning,
            )
            connection = (
                TurnoverLedgerLocalClosureConnection(
                    relation_snapshot_provider=local_adapters.relation_snapshot,
                    replace_relation_snapshot=self._replace_snapshot,
                    save_relation_snapshot=local_adapters.save_snapshot,
                    pair_relation_service=self._pair_relation_service,
                    save_pair_snapshot=lambda snapshot: self._state_store.save_workbench_pair_relations(dict(snapshot)),
                )
                if self._pair_relation_service is not None
                else local_adapters.connection()
            )
            relation_repository = local_adapters.relation_repository()
            dirty_outbox_writer = TurnoverLedgerLocalDirtyOutboxWriter(
                queue_repository=self._queue_repository
            )
            idempotency_store = self._local_idempotency_store_provider()
            workbench_pair_port = (
                TurnoverLedgerWorkbenchPairPort(
                    pair_relation_service=self._pair_relation_service,
                    relation_command_service_factory=self._relation_command_service_factory,
                    relation_facade=self._relation_facade,
                )
                if self._pair_relation_service is not None or self._relation_command_service_factory is not None
                else None
            )
        stale_precondition_port = TurnoverLedgerBankRowStalePreconditionPort(
            bank_rows_provider=self._bank_rows_provider
        )
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=relation_repository,
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=SimpleNamespace(),
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=stale_precondition_port,
            idempotency_store=idempotency_store,
            workbench_pair_port=workbench_pair_port,
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
        postgres_idempotency_store_factory: Callable[[Any], Any],
        local_idempotency_store_provider: Callable[[], Any],
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
        self._postgres_idempotency_store_factory = postgres_idempotency_store_factory
        self._local_idempotency_store_provider = local_idempotency_store_provider

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
            idempotency_store = self._postgres_idempotency_store_factory(connection)
        else:
            if not ReadModelRefreshGateway(queue_repository=self._queue_repository).can_enqueue():
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
            idempotency_store = self._local_idempotency_store_provider()
        uow = TurnoverLedgerWriteUnitOfWork(
            connection=connection,
            relation_repository=SimpleNamespace(),
            extra_repository=SimpleNamespace(),
            settings_port=SimpleNamespace(),
            bankdetail_port=bankdetail_port,
            dirty_outbox_writer=dirty_outbox_writer,
            stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
            idempotency_store=idempotency_store,
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
        current_extra_reader: Callable[[str], dict[str, object]],
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
        self._current_extra_reader = current_extra_reader
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
            if not ReadModelRefreshGateway(queue_repository=self._queue_repository).can_enqueue():
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
            stale_precondition_port=TurnoverLedgerRelationExtraStalePreconditionPort(
                current_extra_reader=self._current_extra_reader
            ),
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
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, expected_versions, idempotency_key
        self._relation_rebuild()
        result = self._routes.confirm_relation(
            bank_row_ids=list(bank_row_ids or []),
            actor=actor_id,
            note=note,
        )
        self._after_mutation(list(affected_months or []))
        return dict(result or {})


class TurnoverLedgerClosureLegacyFallbackFacade:
    def __init__(
        self,
        *,
        relation_rebuild: Callable[[], None],
        routes: Any,
        after_mutation: Callable[[list[str]], None],
        pair_relation_service: Any,
        relation_command_service_factory: Callable[..., Any] | None = None,
        relation_facade: Any | None = None,
    ) -> None:
        self._relation_rebuild = relation_rebuild
        self._routes = routes
        self._after_mutation = after_mutation
        self._pair_port = TurnoverLedgerWorkbenchPairPort(
            pair_relation_service=pair_relation_service,
            relation_command_service_factory=relation_command_service_factory,
            relation_facade=relation_facade,
        )

    def confirm_zero_difference_closure(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, expected_versions, idempotency_key
        self._pair_port.assert_turnover_manual_closure_write_precondition(
            bank_row_ids=list(bank_row_ids or []),
            affected_months=list(affected_months or []),
            transaction=SimpleNamespace(),
        )
        self._relation_rebuild()
        relation = dict(
            self._routes.confirm_zero_difference_closure(
                bank_row_ids=list(bank_row_ids or []),
                actor=actor_id,
                note=note,
            )
            or {}
        )
        pair_relation = self._pair_port.create_turnover_manual_closure(
            relation=relation,
            bank_row_ids=list(bank_row_ids or []),
            actor_id=actor_id,
            note=note,
            affected_months=list(affected_months or []),
            transaction=SimpleNamespace(),
        )
        self._after_mutation(list(affected_months or []))
        return {
            "turnover_relation": relation,
            "relation": relation,
            "workbench_pair_relation": dict(pair_relation or {}),
            "affected_months": list(affected_months or []),
        }

    def withdraw_cash_closure_case(
        self,
        *,
        cash_closure_case_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, idempotency_key
        pair_relation = self._pair_port.withdraw_cash_closure_case(
            case_id=cash_closure_case_id,
            actor_id=actor_id,
            note=note,
            transaction=SimpleNamespace(),
        )
        affected_months = [
            str(month)
            for month in list(pair_relation.get("affected_months") or [])
            if str(month).strip()
        ]
        self._after_mutation(list(affected_months))
        return {
            "relation_id": "",
            "status": "withdrawn",
            "workbench_pair_relation": dict(pair_relation or {}),
            "affected_months": list(affected_months),
        }


def _turnover_closure_visibility_freshness_targets(affected_months: list[str]) -> list[dict[str, str]]:
    normalized_months: list[str] = []
    for month in list(affected_months or []):
        scope_key = str(month or "").strip()
        if not scope_key or scope_key == "all" or scope_key in normalized_months:
            continue
        normalized_months.append(scope_key)
    return [
        {"read_model_key": "turnover_ledger", "scope_key": "all"},
        *[
            {"read_model_key": "workbench_relation", "scope_key": scope_key}
            for scope_key in normalized_months
        ],
    ]


class TurnoverLedgerConfirmRequestBoundaryFacade:
    def __init__(
        self,
        *,
        facade: Any,
        affected_months_resolver: Callable[[list[str]], list[str]],
    ) -> None:
        self._facade = facade
        self._affected_months_resolver = affected_months_resolver

    def confirm_relation_from_request(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_bank_row_ids = [
            str(row_id).strip()
            for row_id in list(bank_row_ids or [])
            if str(row_id).strip()
        ]
        affected_months = self._affected_months_resolver(list(normalized_bank_row_ids))
        confirm_kwargs = {
            "bank_row_ids": normalized_bank_row_ids,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "note": note,
            "affected_months": affected_months,
            "expected_versions": dict(expected_versions or {}),
        }
        if idempotency_key:
            confirm_kwargs["idempotency_key"] = idempotency_key
        result = self._facade.confirm_relation(**confirm_kwargs)
        payload = dict(result or {})
        payload["affected_months"] = list(affected_months)
        return payload

    def confirm_zero_difference_closure_from_request(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_bank_row_ids = [
            str(row_id).strip()
            for row_id in list(bank_row_ids or [])
            if str(row_id).strip()
        ]
        affected_months = self._affected_months_resolver(list(normalized_bank_row_ids))
        closure_kwargs = {
            "bank_row_ids": normalized_bank_row_ids,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "note": note,
            "affected_months": affected_months,
            "expected_versions": dict(expected_versions or {}),
        }
        if idempotency_key:
            closure_kwargs["idempotency_key"] = idempotency_key
        confirm = getattr(self._facade, "confirm_zero_difference_closure", None)
        if not callable(confirm):
            raise RuntimeError("turnover ledger closure facade is not configured.")
        payload = dict(confirm(**closure_kwargs) or {})
        payload["affected_months"] = list(affected_months)
        payload["freshness_targets"] = _turnover_closure_visibility_freshness_targets(
            affected_months
        )
        return payload

    def withdraw_cash_closure_case_from_request(
        self,
        *,
        cash_closure_case_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_case_id = str(cash_closure_case_id or "").strip()
        if not normalized_case_id:
            raise TurnoverRelationValidationError(
                "invalid_cash_closure_case_id",
                "cash_closure_case_id is required.",
            )
        withdraw = getattr(self._facade, "withdraw_cash_closure_case", None)
        if not callable(withdraw):
            raise RuntimeError("turnover ledger cash closure withdraw facade is not configured.")
        withdraw_kwargs = {
            "cash_closure_case_id": normalized_case_id,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "note": note,
        }
        if idempotency_key:
            withdraw_kwargs["idempotency_key"] = idempotency_key
        payload = dict(withdraw(**withdraw_kwargs) or {})
        affected_months = [
            str(month)
            for month in list(payload.get("affected_months") or [])
            if str(month).strip()
        ]
        payload["affected_months"] = affected_months
        payload["freshness_targets"] = _turnover_closure_visibility_freshness_targets(affected_months)
        return payload


class TurnoverLedgerWithdrawRequestBoundaryError(ValueError):
    def __init__(self, *, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class TurnoverLedgerRelationStalePreconditionPort:
    def __init__(self, *, relation_detail_provider: Callable[[str], dict[str, object]]) -> None:
        self._relation_detail_provider = relation_detail_provider

    def assert_current(self, *, expected_versions: dict[str, object], transaction: object) -> None:
        _ = transaction
        for raw_key, expected_value in dict(expected_versions or {}).items():
            key = str(raw_key)
            if not key.startswith("relation:"):
                continue
            relation_id = key.removeprefix("relation:")
            if not relation_id:
                continue
            detail = self._relation_detail_provider(relation_id)
            relation = dict(detail.get("relation") or {})
            current_version = relation.get("version")
            if str(current_version) != str(expected_value):
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_relation_conflict",
                    message="往来款关系已变化，请刷新后重试。",
                )


class TurnoverLedgerBankRowStalePreconditionPort:
    def __init__(self, *, bank_rows_provider: Callable[[], list[dict[str, object]]]) -> None:
        self._bank_rows_provider = bank_rows_provider

    def assert_current(self, *, expected_versions: dict[str, object], transaction: object) -> None:
        _ = transaction
        expected_by_transaction_id: dict[str, object] = {}
        for raw_key, expected_value in dict(expected_versions or {}).items():
            key = str(raw_key)
            if not key.startswith("turnover_bank_row:"):
                continue
            transaction_id = key.removeprefix("turnover_bank_row:").strip()
            if transaction_id:
                expected_by_transaction_id[transaction_id] = expected_value
        if not expected_by_transaction_id:
            return
        rows_by_transaction_id = {
            str(row.get("id") or row.get("transaction_id") or "").strip(): dict(row)
            for row in list(self._bank_rows_provider() or [])
            if str(row.get("id") or row.get("transaction_id") or "").strip()
        }
        for transaction_id, expected_value in expected_by_transaction_id.items():
            row = rows_by_transaction_id.get(transaction_id)
            current_version = None if row is None else self._bank_row_version(row)
            if str(current_version) != str(expected_value):
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_relation_conflict",
                    message="银行流水状态已变化，请刷新后重试。",
                )

    @staticmethod
    def _bank_row_version(row: dict[str, object]) -> object:
        return turnover_bank_row_version(row)


class TurnoverLedgerRelationExtraStalePreconditionPort:
    def __init__(self, *, current_extra_reader: Callable[[str], dict[str, object]]) -> None:
        self._current_extra_reader = current_extra_reader

    def assert_current(self, *, expected_versions: dict[str, object], transaction: object) -> None:
        _ = transaction
        for raw_key, expected_value in dict(expected_versions or {}).items():
            key = str(raw_key)
            if not key.startswith("turnover_relation_extra:"):
                continue
            relation_id = key.removeprefix("turnover_relation_extra:").strip()
            if not relation_id:
                continue
            current_payload = self._current_extra_reader(relation_id)
            current_extra = current_payload.get("extra") if isinstance(current_payload, dict) else None
            current_updated_at = ""
            if isinstance(current_extra, dict):
                current_updated_at = str(current_extra.get("updated_at") or "")
            if str(expected_value or "") != current_updated_at:
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_relation_extra_conflict",
                    message="往来款补充信息已更新，请刷新后重试。",
                )


class TurnoverLedgerWithdrawRequestBoundaryFacade:
    def __init__(
        self,
        *,
        facade: Any,
        relation_detail_provider: Callable[[str], dict[str, object]],
        affected_months_resolver: Callable[[list[str]], list[str]],
    ) -> None:
        self._facade = facade
        self._relation_detail_provider = relation_detail_provider
        self._affected_months_resolver = affected_months_resolver

    def withdraw_relation_from_request(
        self,
        *,
        relation_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        detail = self._relation_detail_provider(relation_id)
        relation = dict(detail.get("relation") or {})
        if str(relation.get("source") or "") != "manual":
            raise TurnoverLedgerWithdrawRequestBoundaryError(
                status_code=400,
                error_code="system_relation_cannot_withdraw",
                message="系统自动生成的往来款关系不能直接撤回，请先人工确认或调整银行流水标签。",
            )
        normalized_idempotency_key = str(idempotency_key or "").strip()
        if not normalized_idempotency_key and str(relation.get("status") or "") == "withdrawn":
            raise TurnoverLedgerWithdrawRequestBoundaryError(
                status_code=409,
                error_code="relation_already_withdrawn",
                message="该往来款关系已撤回，请刷新后重试。",
            )
        bank_row_ids = [str(row_id) for row_id in list(relation.get("bank_row_ids") or [])]
        affected_months = self._affected_months_resolver(list(bank_row_ids))
        expected_versions: dict[str, object] = {}
        try:
            expected_versions[f"relation:{relation_id}"] = int(relation.get("version") or 0)
        except (TypeError, ValueError):
            expected_versions = {}
        withdraw_kwargs = {
            "relation_id": relation_id,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "note": note,
            "affected_months": affected_months,
            "expected_versions": expected_versions,
        }
        if normalized_idempotency_key:
            withdraw_kwargs["idempotency_key"] = normalized_idempotency_key
        result = self._facade.withdraw_relation(**withdraw_kwargs)
        payload = dict(result or {})
        payload["affected_months"] = list(affected_months)
        return payload


class TurnoverLedgerBankRowTagsRequestBoundaryFacade:
    def __init__(
        self,
        *,
        facade_provider: Callable[[], Any],
        legacy_fallback_provider: Callable[[], Any],
        target_validator: Callable[[list[str]], None],
        affected_months_resolver: Callable[[list[str]], list[str]],
    ) -> None:
        self._facade_provider = facade_provider
        self._legacy_fallback_provider = legacy_fallback_provider
        self._target_validator = target_validator
        self._affected_months_resolver = affected_months_resolver

    def update_bank_row_tags_batch_from_request(
        self,
        *,
        updates: list[dict[str, object]],
        actor_id: str,
        tenant_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_updates = [dict(update) for update in list(updates or [])]
        transaction_ids = [
            str(update.get("transaction_id") or "").strip()
            for update in normalized_updates
            if str(update.get("transaction_id") or "").strip()
        ]
        self._target_validator(list(transaction_ids))
        affected_months = self._affected_months_resolver(list(transaction_ids))
        facade = self._facade_provider()
        if facade is None:
            facade = self._legacy_fallback_provider()
        update_kwargs = {
            "updates": normalized_updates,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "affected_months": affected_months,
        }
        if idempotency_key:
            update_kwargs["idempotency_key"] = idempotency_key
        result = facade.update_bank_row_tags_batch(**update_kwargs)
        payload = dict(result or {})
        payload["affected_months"] = list(affected_months)
        payload["turnover_ledger_invalidated"] = True
        payload["workbench_invalidated"] = True
        return payload


class TurnoverLedgerRelationExtraRequestBoundaryError(ValueError):
    def __init__(self, *, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class TurnoverLedgerRelationExtraRequestBoundaryFacade:
    def __init__(
        self,
        *,
        facade_provider: Callable[[], Any],
        current_extra_reader: Callable[[str], dict[str, object]],
    ) -> None:
        self._facade_provider = facade_provider
        self._current_extra_reader = current_extra_reader

    def update_relation_extra_from_request(
        self,
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str],
    ) -> dict[str, object]:
        normalized_payload = dict(payload or {})
        expected_versions = normalized_payload.get("expected_versions")
        idempotency_key = str(
            normalized_payload.get("idempotency_key") or normalized_payload.get("idempotencyKey") or ""
        ).strip() or None
        if isinstance(expected_versions, dict):
            expected_key = f"turnover_relation_extra:{relation_id}"
            if expected_key in expected_versions:
                current_payload = self._current_extra_reader(relation_id)
                current_extra = current_payload.get("extra") if isinstance(current_payload, dict) else None
                current_updated_at = ""
                if isinstance(current_extra, dict):
                    current_updated_at = str(current_extra.get("updated_at") or "")
                if str(expected_versions.get(expected_key) or "") != current_updated_at:
                    raise TurnoverLedgerRelationExtraRequestBoundaryError(
                        status_code=409,
                        error_code="turnover_relation_extra_conflict",
                        message="往来款补充信息已更新，请刷新后重试。",
                    )
        facade = self._facade_provider()
        result = facade.update_relation_extra(
            relation_id=relation_id,
            payload=normalized_payload,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope_keys=list(scope_keys or ["all"]),
            expected_versions=expected_versions if isinstance(expected_versions, dict) else None,
            idempotency_key=idempotency_key,
        )
        response_payload = dict(result or {})
        response_payload["turnover_ledger_invalidated"] = True
        return response_payload


class TurnoverLedgerTagSelectionRequestBoundaryFacade:
    def __init__(self, *, facade_provider: Callable[[], Any]) -> None:
        self._facade_provider = facade_provider

    def update_tag_selection_from_request(
        self,
        *,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        facade = self._facade_provider()
        return dict(
            facade.update_tag_selection(
                payload=dict(payload or {}),
                actor_id=actor_id,
                tenant_id=tenant_id,
                scope_keys=["all"],
                idempotency_key=idempotency_key,
            )
            or {}
        )


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
        pair_relation_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
        relation_facade: Any | None = None,
    ) -> None:
        self._routes = routes
        self._after_mutation = after_mutation
        self._pair_port = (
            TurnoverLedgerWorkbenchPairPort(
                pair_relation_service=pair_relation_service,
                relation_command_service_factory=relation_command_service_factory,
                relation_facade=relation_facade,
            )
            if pair_relation_service is not None or relation_command_service_factory is not None
            else None
        )

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
        if self._pair_port is not None:
            self._pair_port.assert_turnover_manual_closure_withdrawable(
                relation_id=relation_id,
                transaction=SimpleNamespace(),
            )
        result = self._routes.withdraw_relation(
            relation_id=relation_id,
            actor=actor_id,
            note=note,
        )
        if self._pair_port is not None:
            relation = dict(result.get("relation") if isinstance(result.get("relation"), dict) else result)
            result["workbench_pair_relation"] = self._pair_port.withdraw_turnover_manual_closure(
                relation=relation,
                actor_id=actor_id,
                note=note,
                transaction=SimpleNamespace(),
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
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, idempotency_key
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

    def confirm_zero_difference_closure(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        repository = self._repository_factory(transaction)
        confirm = getattr(repository, "confirm_zero_difference_closure", None)
        if not callable(confirm):
            raise RuntimeError("turnover relation repository must expose confirm_zero_difference_closure.")
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


class TurnoverLedgerWorkbenchPairPort:
    def __init__(
        self,
        *,
        pair_relation_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
        relation_facade: Any | None = None,
    ) -> None:
        self._pair_relation_service = pair_relation_service
        self._relation_command_service_factory = relation_command_service_factory
        self._relation_facade = relation_facade

    def create_turnover_manual_closure(
        self,
        *,
        relation: dict[str, object],
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        affected_months: list[str],
        transaction: Any,
    ) -> dict[str, object]:
        relation_id = str(relation.get("relation_id") or "").strip()
        if not relation_id:
            raise RuntimeError("turnover closure relation must include relation_id.")
        normalized_row_ids = [
            str(row_id).strip()
            for row_id in list(bank_row_ids or [])
            if str(row_id).strip()
        ]
        case_id = f"turnover:{relation_id}"
        principal_amount = str(relation.get("principal_amount") or "0.00")
        settled_amount = str(relation.get("settled_amount") or "0.00")
        relation_evidence = relation.get("evidence")
        turnover_closure_mode = (
            str(relation_evidence.get("closure_mode") or "").strip()
            if isinstance(relation_evidence, dict)
            else ""
        ) or "manual_zero_difference_pair"
        amount_check = {
            "status": "matched",
            "direction": "turnover_manual_closure",
            "principal_amount": principal_amount,
            "settled_amount": settled_amount,
            "amount_delta": "0.00",
            "requires_note": False,
        }
        special_metadata = {
            "source": "turnover_ledger",
            "turnover_relation_id": relation_id,
            "turnover_closure_mode": turnover_closure_mode,
            "turnover_closure_bank_row_ids": list(normalized_row_ids),
        }
        evidence = {
            "source": "turnover_ledger",
            "turnover_relation_id": relation_id,
            "bank_row_ids": list(normalized_row_ids),
        }
        relation_command_service = self._relation_command_service(transaction)
        if relation_command_service is not None:
            active_relations = self._active_relations_for_row_ids_from_command(
                relation_command_service,
                normalized_row_ids,
            )
            merge_relations = [
                dict(active_relation)
                for active_relation in active_relations
                if str(active_relation.get("case_id") or "").strip() != case_id
            ]
            self._assert_mergeable_turnover_manual_closure_relations(
                merge_relations,
                selected_bank_row_ids=normalized_row_ids,
            )
            merged_row_ids, merged_row_types = self._merged_turnover_manual_closure_rows(
                selected_bank_row_ids=normalized_row_ids,
                merge_relations=merge_relations,
            )
            try:
                result = relation_command_service.confirm_relation(
                    case_id=case_id,
                    row_ids=merged_row_ids,
                    row_types=merged_row_types,
                    relation_mode=TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
                    actor_id=actor_id,
                    month_scope=self._month_scope(affected_months),
                    note=note,
                    amount_check=amount_check,
                    special_metadata=special_metadata,
                    evidence=evidence,
                    display_tags=["外部往来款手动闭环"],
                    before_relations=merge_relations if merge_relations else None,
                    replace_existing=bool(merge_relations),
                    history_operation_type="turnover_manual_closure_confirm",
                )
            except WorkbenchRelationCommandError as exc:
                raise self._command_precondition_error(exc) from exc
            return dict(result.get("relation") if isinstance(result, dict) and isinstance(result.get("relation"), dict) else result or {})

        raise self._command_unavailable_error(
            case_id=case_id,
            row_ids=normalized_row_ids,
            action="turnover_manual_closure_confirm",
        )

    def assert_turnover_manual_closure_write_precondition(
        self,
        *,
        bank_row_ids: list[str],
        affected_months: list[str],
        transaction: Any,
    ) -> None:
        relation_command_service = self._relation_command_service(transaction)
        if relation_command_service is None:
            raise self._command_unavailable_error(
                case_id="",
                row_ids=[
                    str(row_id).strip()
                    for row_id in list(bank_row_ids or [])
                    if str(row_id).strip()
                ],
                action="turnover_manual_closure_precondition",
            )
        try:
            relation_command_service.assert_write_precondition(
                row_ids=[
                    str(row_id).strip()
                    for row_id in list(bank_row_ids or [])
                    if str(row_id).strip()
                ],
                month_scope=self._month_scope(affected_months),
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_precondition_error(exc) from exc

    def assert_turnover_manual_closure_withdrawable(
        self,
        *,
        relation_id: str,
        transaction: Any,
        bank_row_ids: list[str] | None = None,
    ) -> None:
        _ = transaction
        case_id = self._turnover_case_id(relation_id)
        if not case_id:
            raise TurnoverLedgerWritePreconditionError(
                error_code="invalid_relation_id",
                message="relation_id is required.",
            )
        active_relation = self._active_relation_by_case_id_from_facade(case_id, list(bank_row_ids or []))
        if active_relation is not None:
            if not self._is_turnover_manual_closure_withdrawable_from_turnover(active_relation):
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_closure_withdraw_requires_workbench",
                    message="外部往来闭环已在关联台补齐 OA/发票，请到关联台撤回完整关系。",
                )
            return
        if self._relation_facade is not None and bank_row_ids:
            return
        if self._pair_relation_service is None:
            return
        active_relation = self._active_relation_by_case_id(case_id)
        if active_relation is None:
            return
        if not self._is_turnover_manual_closure_withdrawable_from_turnover(active_relation):
            raise TurnoverLedgerWritePreconditionError(
                error_code="turnover_closure_withdraw_requires_workbench",
                message="外部往来闭环已在关联台补齐 OA/发票，请到关联台撤回完整关系。",
            )

    def withdraw_turnover_manual_closure(
        self,
        *,
        relation: dict[str, object],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        relation_id = str(relation.get("relation_id") or "").strip()
        case_id = self._turnover_case_id(relation_id)
        if not case_id:
            return {}
        bank_row_ids = [
            str(row_id).strip()
            for row_id in list(relation.get("bank_row_ids") or [])
            if str(row_id).strip()
        ]
        self.assert_turnover_manual_closure_withdrawable(
            relation_id=relation_id,
            transaction=transaction,
            bank_row_ids=list(bank_row_ids),
        )
        relation_command_service = self._relation_command_service(transaction)
        if relation_command_service is not None:
            try:
                result = relation_command_service.withdraw_relation(
                    case_id=case_id,
                    actor_id=actor_id,
                    reason=note,
                    history_operation_type="turnover_manual_closure_withdraw",
                )
            except WorkbenchRelationCommandError as exc:
                if exc.error_code == "workbench_relation_not_found":
                    return {}
                raise self._command_precondition_error(exc) from exc
            relation_result = dict(
                result.get("relation")
                if isinstance(result, dict) and isinstance(result.get("relation"), dict)
                else result or {}
            )
            if isinstance(result, dict) and isinstance(result.get("restored_relations"), list):
                relation_result["restored_relations"] = [
                    dict(item)
                    for item in list(result.get("restored_relations") or [])
                    if isinstance(item, dict)
                ]
            return relation_result
        raise self._command_unavailable_error(
            case_id=case_id,
            row_ids=bank_row_ids,
            action="turnover_manual_closure_withdraw",
        )

    def withdraw_cash_closure_case(
        self,
        *,
        case_id: str,
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            raise TurnoverLedgerWritePreconditionError(
                error_code="invalid_cash_closure_case_id",
                message="cash_closure_case_id is required.",
            )
        relation_command_service = self._relation_command_service(transaction)
        if relation_command_service is None:
            raise self._command_unavailable_error(
                case_id=normalized_case_id,
                row_ids=[],
                action="cash_closure_withdraw",
            )
        try:
            result = relation_command_service.withdraw_relation(
                case_id=normalized_case_id,
                actor_id=actor_id,
                reason=note,
                history_operation_type="turnover_cash_closure_withdraw",
            )
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                raise TurnoverLedgerWritePreconditionError(
                    error_code="cash_closure_relation_not_found",
                    message="收支闭环关系已变化，请刷新后重试。",
                    payload=exc.payload,
                ) from exc
            raise self._command_precondition_error(exc) from exc
        relation_result = dict(
            result.get("relation")
            if isinstance(result, dict) and isinstance(result.get("relation"), dict)
            else result or {}
        )
        if isinstance(result, dict):
            relation_result["affected_months"] = [
                str(month)
                for month in list(result.get("affected_months") or [])
                if str(month).strip()
            ]
            relation_result["affected_row_ids"] = [
                str(row_id)
                for row_id in list(result.get("affected_row_ids") or [])
                if str(row_id).strip()
            ]
            if isinstance(result.get("restored_relations"), list):
                relation_result["restored_relations"] = [
                    dict(item)
                    for item in list(result.get("restored_relations") or [])
                    if isinstance(item, dict)
                ]
        return relation_result

    @staticmethod
    def _active_relations_for_row_ids_from_command(
        relation_command_service: Any,
        row_ids: list[str],
    ) -> list[dict[str, object]]:
        reader = getattr(relation_command_service, "active_relations_for_row_ids", None)
        if not callable(reader):
            return []
        relations = reader([
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ])
        return [
            dict(relation)
            for relation in list(relations or [])
            if isinstance(relation, dict)
        ]

    @classmethod
    def _assert_mergeable_turnover_manual_closure_relations(
        cls,
        relations: list[dict[str, object]],
        *,
        selected_bank_row_ids: list[str],
    ) -> None:
        selected = {
            str(row_id).strip()
            for row_id in list(selected_bank_row_ids or [])
            if str(row_id).strip()
        }
        for relation in list(relations or []):
            row_ids = [
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            ]
            row_types = cls._normalized_relation_row_types(relation)
            if not row_ids or not row_types or len(row_ids) != len(row_types):
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_relation_conflict",
                    message="关联台关系结构不完整，请到关联台处理后重试。",
                    payload={"case_id": str(relation.get("case_id") or "")},
                )
            relation_bank_rows = {
                row_id
                for row_id, row_type in zip(row_ids, row_types, strict=False)
                if row_type == "bank"
            }
            if not selected.intersection(relation_bank_rows):
                continue
            relation_mode = str(relation.get("relation_mode") or "").strip()
            if relation_mode == TURNOVER_MANUAL_CLOSURE_RELATION_MODE:
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_relation_conflict",
                    message="所选流水已存在外部往来闭环，请先撤回原闭环后再重新确认。",
                    payload={"case_id": str(relation.get("case_id") or "")},
                )
            if set(row_types).issubset({"oa", "bank"}) and "oa" in row_types:
                continue
            raise TurnoverLedgerWritePreconditionError(
                error_code="turnover_closure_requires_workbench",
                message="所选流水已在关联台补齐发票或属于其他业务关系，请到关联台处理完整关系。",
                payload={
                    "case_id": str(relation.get("case_id") or ""),
                    "row_types": list(row_types),
                },
            )

    @classmethod
    def _merged_turnover_manual_closure_rows(
        cls,
        *,
        selected_bank_row_ids: list[str],
        merge_relations: list[dict[str, object]],
    ) -> tuple[list[str], list[str]]:
        merged_row_ids: list[str] = []
        merged_row_types: list[str] = []

        def append(row_id: str, row_type: str) -> None:
            normalized_row_id = str(row_id or "").strip()
            normalized_row_type = str(row_type or "").strip()
            if not normalized_row_id or not normalized_row_type:
                return
            if normalized_row_id in merged_row_ids:
                return
            merged_row_ids.append(normalized_row_id)
            merged_row_types.append(normalized_row_type)

        for relation in list(merge_relations or []):
            row_ids = [
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            ]
            row_types = cls._normalized_relation_row_types(relation)
            for row_id, row_type in zip(row_ids, row_types, strict=False):
                append(row_id, row_type)
        for row_id in list(selected_bank_row_ids or []):
            append(str(row_id), "bank")
        return merged_row_ids, merged_row_types

    def _relation_command_service(self, transaction: Any) -> Any | None:
        if self._relation_command_service_factory is None:
            return None
        try:
            return self._relation_command_service_factory(transaction)
        except TypeError:
            return self._relation_command_service_factory(transaction=transaction)

    @staticmethod
    def _command_precondition_error(exc: WorkbenchRelationCommandError) -> TurnoverLedgerWritePreconditionError:
        if exc.error_code == "workbench_relation_active_row_conflict":
            message = "银行流水已存在关联台闭环关系，请刷新后重试。"
        elif exc.error_code in {"workbench_relation_read_model_not_fresh", "workbench_relation_read_model_unavailable"}:
            message = "关联台关系状态正在刷新，请稍后重试。"
        else:
            message = exc.message or exc.error_code
        return TurnoverLedgerWritePreconditionError(
            error_code="turnover_relation_conflict",
            message=message,
            payload=exc.payload,
        )

    @staticmethod
    def _command_unavailable_error(
        *,
        case_id: str,
        row_ids: list[str],
        action: str,
    ) -> TurnoverLedgerWritePreconditionError:
        return TurnoverLedgerWritePreconditionError(
            error_code="workbench_relation_command_unavailable",
            message="关联台关系写入服务不可用，请稍后重试。",
            payload={
                "case_id": case_id,
                "row_ids": [
                    str(row_id).strip()
                    for row_id in list(row_ids or [])
                    if str(row_id).strip()
                ],
                "action": action,
            },
        )

    @staticmethod
    def _turnover_case_id(relation_id: str) -> str:
        normalized_relation_id = str(relation_id or "").strip()
        return f"turnover:{normalized_relation_id}" if normalized_relation_id else ""

    def _active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        if self._pair_relation_service is None:
            return None
        get_by_case_id = getattr(self._pair_relation_service, "get_active_relation_by_case_id", None)
        if callable(get_by_case_id):
            active_relation = get_by_case_id(case_id)
            return dict(active_relation) if isinstance(active_relation, dict) else None
        list_active = getattr(self._pair_relation_service, "list_active_relations", None)
        if callable(list_active):
            for relation in list(list_active() or []):
                if isinstance(relation, dict) and str(relation.get("case_id") or "") == case_id:
                    return dict(relation)
        return None

    def _active_relation_by_case_id_from_facade(
        self,
        case_id: str,
        row_ids: list[str],
    ) -> dict[str, object] | None:
        if self._relation_facade is None or not row_ids:
            return None
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return None
        try:
            payload = reader(
                [str(row_id) for row_id in list(row_ids or []) if str(row_id).strip()],
                require_fresh=True,
                reason="turnover_manual_closure_withdraw_precheck",
            )
        except TypeError:
            payload = reader([str(row_id) for row_id in list(row_ids or []) if str(row_id).strip()])
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("status") or payload.get("read_model_status") or "fresh")
        if status != "fresh":
            raise TurnoverLedgerWritePreconditionError(
                error_code="turnover_relation_conflict",
                message="关联台关系状态正在刷新，请稍后重试。",
            )
        for relation in relation_dicts_from_distribution_payload(payload):
            if str(relation.get("case_id") or "") == case_id:
                return dict(relation)
        for group in list(payload.get("groups") or []):
            if not isinstance(group, dict):
                continue
            group_id = str(group.get("group_id") or "").strip()
            payload_dict = group.get("payload") if isinstance(group.get("payload"), dict) else {}
            payload_group_id = str(payload_dict.get("group_id") or payload_dict.get("case_id") or "").strip()
            if case_id not in {group_id, payload_group_id}:
                continue
            return {
                "case_id": case_id,
                "relation_mode": str(payload_dict.get("relation_mode") or group.get("relation_mode") or ""),
                "row_ids": list(payload_dict.get("row_ids") or group.get("row_ids") or []),
                "row_types": list(payload_dict.get("row_types") or group.get("row_types") or []),
                "special_metadata": dict(payload_dict.get("special_metadata") or {})
                if isinstance(payload_dict.get("special_metadata"), dict)
                else {},
            }
        return None

    @staticmethod
    def _is_turnover_manual_closure_withdrawable_from_turnover(relation: dict[str, object]) -> bool:
        if str(relation.get("relation_mode") or "").strip() != TURNOVER_MANUAL_CLOSURE_RELATION_MODE:
            return False
        row_types = TurnoverLedgerWorkbenchPairPort._normalized_relation_row_types(relation)
        return bool(row_types) and set(row_types).issubset({"oa", "bank"})

    @staticmethod
    def _normalized_relation_row_types(relation: dict[str, object]) -> list[str]:
        return [
            str(row_type).strip()
            for row_type in list(relation.get("row_types") or [])
            if str(row_type).strip()
        ]

    @staticmethod
    def _month_scope(affected_months: list[str]) -> str:
        months = [
            str(month).strip()
            for month in list(affected_months or [])
            if str(month).strip()
        ]
        return months[0] if len(months) == 1 else "all"


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

    def confirm_zero_difference_closure(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: Any,
    ) -> dict[str, object]:
        self._rebuild_relation_snapshot()
        confirm = getattr(self._relation_service, "confirm_zero_difference_closure", None)
        if not callable(confirm):
            raise RuntimeError("relation_service must expose confirm_zero_difference_closure.")
        relation = dict(
            confirm(
                bank_row_ids=list(bank_row_ids or []),
                actor=actor_id,
                note=note,
            )
            or {}
        )
        self._save_relation_snapshot(transaction)
        return {"relation": relation}

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
        scope_policy_registry: ReadModelScopePolicyRegistry = DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ) -> None:
        self._queue_repository = queue_repository
        self._tenant_id = str(tenant_id or "default")
        self._priority = str(priority or "normal")
        self._trace_id = str(trace_id).strip() if trace_id else None
        self._scope_policy_registry = scope_policy_registry

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
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_keys = self._scope_policy_registry.normalize_and_validate(
            normalized_scope_type,
            [str(scope_key or "all") for scope_key in list(scope_keys or ["all"])],
        )
        for scope_key in normalized_scope_keys:
            events.append(
                enqueue(
                    transaction=transaction,
                    scope_type=normalized_scope_type,
                    scope_key=scope_key,
                    reason=reason,
                    tenant_id=self._tenant_id,
                    priority=self._priority,
                    trace_id=self._trace_id,
                    metadata={"action_name": str((payload or {}).get("action_name") or "").strip()},
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
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh.")
        refresh_reason = (
            "turnover_relation_extra_changed"
            if reason == "relation_extra_update"
            else reason
        )
        return refresh_gateway.enqueue_many_events(
            scope_type,
            [str(scope_key or "all") for scope_key in list(scope_keys or ["all"])],
            reason=refresh_reason,
        )


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


class TurnoverLedgerLocalClosureConnection:
    def __init__(
        self,
        *,
        relation_snapshot_provider: Callable[[], dict[str, object]],
        replace_relation_snapshot: Callable[[dict[str, object]], None],
        save_relation_snapshot: Callable[[dict[str, object]], None],
        pair_relation_service: Any,
        save_pair_snapshot: Callable[[dict[str, object]], None],
    ) -> None:
        self._relation_snapshot_provider = relation_snapshot_provider
        self._replace_relation_snapshot = replace_relation_snapshot
        self._save_relation_snapshot = save_relation_snapshot
        self._pair_relation_service = pair_relation_service
        self._save_pair_snapshot = save_pair_snapshot

    @contextmanager
    def transaction(self) -> Any:
        previous_relation_snapshot = dict(self._relation_snapshot_provider() or {})
        previous_pair_snapshot = dict(self._pair_relation_service.snapshot() or {})
        try:
            yield SimpleNamespace()
        except Exception:
            self._replace_relation_snapshot(dict(previous_relation_snapshot))
            self._save_relation_snapshot(dict(previous_relation_snapshot))
            self._replace_pair_snapshot(previous_pair_snapshot)
            self._save_pair_snapshot(dict(previous_pair_snapshot))
            raise
        else:
            self._save_relation_snapshot(dict(self._relation_snapshot_provider() or {}))
            self._save_pair_snapshot(dict(self._pair_relation_service.snapshot() or {}))

    def _replace_pair_snapshot(self, snapshot: dict[str, object]) -> None:
        restored = type(self._pair_relation_service).from_snapshot(snapshot)
        self._pair_relation_service._pair_relations = deepcopy(restored._pair_relations)
        self._pair_relation_service._pair_relation_history = deepcopy(restored._pair_relation_history)


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

    def confirm_zero_difference_closure(
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
        confirm = getattr(self._routes, "confirm_zero_difference_closure", None)
        if not callable(confirm):
            raise RuntimeError("turnover relation routes must expose confirm_zero_difference_closure.")
        return {"relation": dict(
            confirm(
                bank_row_ids=list(bank_row_ids),
                actor=actor_id,
                note=note,
            )
            or {}
        )}

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
