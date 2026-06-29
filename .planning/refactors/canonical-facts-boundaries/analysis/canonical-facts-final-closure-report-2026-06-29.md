# Canonical Facts Final Closure Audit - 2026-06-29

## Result

Status: final-closed.

The canonical facts refactor has closed the production source-of-truth deletion surface. The final GridFS worker blocker was removed in the coordinated 07/08 deletion slice recorded in `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-final-blocker-audit.md`.

## Evidence

Commands run for this audit:

```bash
git diff --name-only -- backend/src/fin_ops_platform/services/read_model_manifest.py backend/src/fin_ops_platform/services/read_model_scope_policy.py backend/src/fin_ops_platform/services/read_model_refresh_gateway.py backend/src/fin_ops_platform/services/read_model_query_gateway.py backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/services/runtime_worker_registry.py backend/src/fin_ops_platform/services/operation_freshness_barrier.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py docs/architecture/module-boundaries/read-model-contracts.md docs/modules/read-models .planning/refactors/modular-io-boundaries/autonomous
rg -n "build_application\(|app\._|application\._|_state_store|_initialize_runtime_services|ApplicationStateStore|local_pickle|Mongo|mongo|GridFS|gridfs|state:" backend/src/fin_ops_platform/tools -g '*.py'
rg -n "reconcile_(workbench|cost_statistics|tax_offset)_read_model|fin_ops_platform\.tools\.exporters|ExportDefinition|gridfs_files_manifest|import_postgres_staging|transform_staging_to_postgres|postgres_transform|check_import_fact_consistency|reconcile_postgres_migration" backend/src tests -g '*.py'
```

Findings:

- 07-owned read-model/runtime files have no diff from this 08 slice.
- Old exporter/reconcile/staging/transform/import-consistency names remain only in `tests/test_platform_runtime_boundary_guards.py` removal guards.
- Direct `Application._*`, `_state_store` and `_initialize_runtime_services` use is absent from tool files. Retained tools call `backend/src/fin_ops_platform/tools/runtime_application.py`, which delegates to public `Application.tool_runtime_ports()`.
- Tool mentions of `legacy_mongo_id` are PostgreSQL compatibility identifiers used by audit/repair SQL, not App Mongo source-of-truth access.

## Closed Surface

The following old production source-of-truth classes are removed or guarded:

- App Mongo export / manifest / exporter definition package.
- Shadow/dual state-store modules and rehearsal/preflight/convergence tools.
- PostgreSQL staging transform and migration reconcile tools.
- Legacy read-model reconcile tools that used application private builders/API paths as oracles.
- OA attachment audit direct Mongo tool/service/test.
- ApplicationStateStore App Mongo/GridFS runtime fields, detailed collection helpers, full snapshot bootstrap, Mongo settings loader and Mongo-only branches.
- PostgresStateStore `app.app_settings state:*` canonical/runtime snapshot read/write helpers.
- Turnover legacy fallback facades.
- Legacy ETC `/api/etc/batches*` backend route/services and frontend client calls.

## Former Blocker Resolved

`file_object.gridfs_migration` is no longer production-worker reachable. The coordinated deletion removed the registry registration, worker flag/handler, legacy GridFS migration service/config, file-migration deploy env examples and RabbitMQ dispatch event in one slice.

### Operational Tool Boundary

`backend/src/fin_ops_platform/tools/runtime_application.py` still exists for retained operational tools:

- bank auto-tag restore;
- historical ETC migration/link/cleanup.

It no longer reaches into `Application._*`, `_state_store` or `_initialize_runtime_services`; those dependencies are exposed through public app-owned tool ports. The adapter no longer uses the old `full snapshot application` helper name, and `Application.tool_runtime_ports()` no longer exposes the full `state_store`; tool initialization uses `Application.tool_runtime_state_snapshot()` for the small state subset required by retained operational tools. Delete this adapter only when the retained tools are retired or folded into owner module CLIs without duplicating app dependency assembly.

### Local Store Boundary Accepted

`ApplicationStateStore` / local pickle is accepted as non-production fixture/tooling I/O, not a business source of truth. It no longer opens App Mongo/GridFS, no longer participates in production factory wiring, and no production app/service/tool path imports it.

Evidence:

- `state_store_factory.build_state_store(...)` requires `FIN_OPS_APP_STORAGE_BACKEND=postgres`.
- `test_production_runtime_paths_do_not_import_local_state_store` guards app/service/tool paths from importing local `state_store.py`.
- `test_production_services_do_not_type_bind_to_local_application_state_store` guards ordinary production services from binding to `ApplicationStateStore`.
- `test_application_state_store_does_not_open_app_mongo_snapshot_source` and related guards keep App Mongo/GridFS out of the local fixture store.

## Closure Decision

Continue status: `done`.

No final closure blocker remains for 08 canonical facts. Future work is normal maintenance: keep guards green, retire retained operational tools when their runbooks are no longer needed, and avoid reintroducing legacy source-of-truth paths.

Update: `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-final-blocker-audit.md` confirms no remaining production source-of-truth deletion slice after coordinated removal of `file_object.gridfs_migration`.

Update: `.planning/refactors/canonical-facts-boundaries/analysis/canonical-facts-wave-6-tool-runtime-state-port-closure.md` records the follow-up tool runtime state port narrowing.

## Verification To Keep

Before any future change that touches this boundary, rerun:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v
bash scripts/verify.sh docs
git diff --check
```

Known caveat: if the full platform runtime guard suite includes unrelated 07 NEXT-PROMPT expectation failures, do not fix those from canonical facts work.
