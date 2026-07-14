---
status: resolved
trigger: "ETC票据管理确认对账后，在ETC发票导入页导入ZIP并开始预览，/api/etc/import/preview 返回 504 Gateway Time-out。"
created: 2026-07-14
updated: 2026-07-14
---

# Debug Session: etc-invoice-preview-504

## Symptoms

- Expected behavior: ETC 对账任务确认后，选择该任务并上传 ETC ZIP，预览应在请求时限内返回可导入发票及对账筛选结果。
- Actual behavior: 上传约 59 个 ZIP 后开始预览，页面收到 HTML 形式的 `504 Gateway Time-out`，预览表为空。
- Error messages: `ETC 接口返回了 HTML 页面：504 /api/etc/import/preview`；响应标题为 `504 Gateway Time-out`。
- Timeline: 2026-07-14 截图所示；触发条件是 ETC 票据管理完成确认对账后进入 ETC 发票导入。
- Reproduction: 在 `/imports/etc-invoices` 选择已确认的 ETC 对账任务，上传多份 ZIP（截图为 59 份），点击“开始预览”。

## Current Focus

- hypothesis: task-aware preview calls `EtcService.inspect_import_zips` twice, and each inspect independently rebuilds attachment presence twice by calling `_stored_invoice_file_exists` for XML and PDF on every existing ETC invoice. In production (293 existing ETC invoices, MinIO object storage) this causes 2,344 synchronous SQL + MinIO GET/hash probes before session persistence; serial verified-object storage/reload for 59 new ZIPs further extends the request past nginx's 60-second upstream deadline.
- test: pin the exact `_stored_invoice_file_exists`/object-storage call chain and verify call-count multiplication from source; contrast it with the matcher microbenchmarks and production route telemetry.
- expecting: source confirms `2 inspect calls × 2 baseline builds × 2 attachment paths × 293 invoices = 2,344` remote existence checks, with no bulk metadata path or request-scoped cache; the HTML 504 is the proxy consequence, not the causal defect.
- next_action: deploy through the documented release path and repeat the production 59-ZIP preview smoke; retain nginx's current timeout so the application latency regression remains observable.
- reasoning_checkpoint:
  - evidence_for: the task-aware service deterministically performs two inspections; each inspection deterministically constructs attachment state twice; production has 293 existing invoices backed by MinIO; every state check performs one SQL lookup plus a full object GET/size/hash verification; a direct call-count probe measured 1,172 checks for one inspection and 2,344 for the task-aware two-inspection path.
  - evidence_against: ZIP parsing alone completes the repository's 120-invoice mixed archive test in 0.168 seconds; the global requirement matcher can be pathological for ambiguous unsatisfiable inputs, but the 2,344 remote reads occur independently of uploaded invoice contents and therefore do not require matcher pathology to explain this incident.
  - conclusion: the confirmed root cause is preview-only attachment-state construction crossing a physical object-read boundary inside nested per-invoice loops. Serial durable upload verification and immediate rehydration are secondary request-latency amplifiers. Nginx's 504 is the observed deadline, not the defect.

## Evidence

- 2026-07-14: screenshot shows 59 selected ZIP files, an ETC reconciliation task with version 19 and 68 ETC tickets, and an HTML 504 response from `/api/etc/import/preview`.
- 2026-07-14: CodeGraph identifies `EtcImportPreviewService.preview` (`backend/src/fin_ops_platform/services/etc_import_preview_service.py:37`) as the task-aware entry service. Its `_build_preview` calls `preview_etc_zip_for_task`, rebuilds allowlisted ZIPs, then calls `inspect_import_zips` twice: once for filtered uploads and once for all uploads (`:134-146`).
- 2026-07-14: `EtcService.inspect_import_zips` (`backend/src/fin_ops_platform/services/etc_service.py:1314`) itself runs both `_process_import_zips(..., persist=False)` and `_calculate_import_preview_audit(uploads)` (`:1318-1320`), so each invocation is already two parsing/audit passes.
- 2026-07-14: production `PostgresEtcImportSessionStore.save_preview` stores every original upload serially before one repository save (`backend/src/fin_ops_platform/services/etc_import_session_store.py:105-145`); this is synchronous inside the preview request.
- 2026-07-14: module contracts explicitly list “真实大 ZIP” and “Nginx 代理和大数据浏览器 smoke” as remaining untested risks; the existing 120-invoice synthetic test covers parser counts but not task-aware global reconciliation matching or end-to-end preview latency (`docs/modules/imports-etc-invoices/boundary-io.md`, `tests.md`, `implementation-notes.md`).
- 2026-07-14: the web client permits 300 seconds (`ETC_FILE_UPLOAD_TIMEOUT_MS` in `web/src/features/etc/api.ts:581,1651-1655`), but `deploy/oa/nginx.fin-ops.conf.example:55-62` sets no `proxy_read_timeout`, so nginx's default upstream read timeout remains the earlier terminating boundary (normally 60 seconds). This explains the HTML 504 shape but is not by itself the application root cause.
- 2026-07-14: production read-only `/api/etc/reconciliation-tasks/ready-for-import` identifies the affected ready task at version 19 with 59 ticket-root items, 38 expected requirements and a required invoice total of 68; the repository's existing tests do not cover this task-aware production volume.
- 2026-07-14: production read-only `/api/etc/invoices?page_size=1` reports 293 existing ETC invoices; sampled attachment references use `minio://`, and `/health/ready` reports the MinIO object-storage backend.
- 2026-07-14: source call count is `2 task-aware inspect_import_zips calls × 2 preview-state comprehensions per inspect × 2 stored paths (XML/PDF) × 293 existing invoices = 2,344` synchronous existence checks before durable session save. Each production existence check crosses the SQL/object-storage boundary and verifies object bytes/hash rather than consulting already-loaded attachment metadata.
- 2026-07-14: durable session persistence is an additional amplifier: `PostgresEtcImportSessionStore.save_preview` stores 59 uploads serially; production verified-object writes perform temporary PUT/GET verification, final PUT/GET verification and temporary delete, then `save_preview` calls `self.get(...)`, which reloads all 59 final objects.
- 2026-07-14: production `/health/ready` API performance contains no completed `POST /api/etc/import/preview` sample for the reported attempt even though adjacent operations on the same task are present, consistent with nginx timing out while the synchronous backend path continues or fails to complete.
- 2026-07-14: the exact physical-read chain is `EtcService._process_import_zips` (`backend/src/fin_ops_platform/services/etc_service.py:1555-1570`) and `_calculate_import_preview_audit` (`:1447-1457`) → `_stored_invoice_file_exists` (`:2615-2621`) → `PostgresStateStore.etc_invoice_file_exists` (`backend/src/fin_ops_platform/app/postgres_state_store.py:471-480`) → `_read_object_file` (`:1479-1496`). `_read_object_file` first performs `_file_object_for_storage_uri` SQL lookup (`:1449-1459`), then `get_object`, byte-length validation, and SHA-256 validation; this is not a metadata/HEAD existence check.
- 2026-07-14: a direct service-level call-count probe with 293 synthetic existing invoices and a spy on `_stored_invoice_file_exists` measured 1,172 calls for one `inspect_import_zips([])` invocation and 2,344 calls for the two invocations made by task-aware preview, exactly matching the source-derived formula.
- 2026-07-14: the existing mixed-ZIP parser regression (`EtcServiceTests.test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate`) processed 120 synthetic invoices, including duplicate and malformed entries, in 0.168 seconds of test time (1.12 seconds including process startup). This rules out ordinary ZIP/XML parsing as a sufficient explanation for the 60-second failure.
- 2026-07-14: the durable-write amplifier is `PostgresEtcImportSessionStore.save_preview` (`backend/src/fin_ops_platform/services/etc_import_session_store.py:105-145`) → `PostgresStateStore.store_etc_import_archive` (`backend/src/fin_ops_platform/app/postgres_state_store.py:406-438`) → `_store_object_file` (`:1239-1324`) → `write_verified_object` (`backend/src/fin_ops_platform/services/file_object_migration.py:27-74`). Each upload performs temporary PUT/GET, final PUT/GET, and temporary delete; `save_preview` then calls `self.get`, whose loop (`etc_import_session_store.py:147-170`) downloads every just-written final object again.
- 2026-07-14: `_calculate_import_preview_audit` also performs a canonical-invoice existence query per unique candidate (`backend/src/fin_ops_platform/services/etc_service.py:1531-1540`; PostgreSQL implementation `backend/src/fin_ops_platform/services/postgres_repositories/core.py:389-402`). This is a lesser SQL N+1 amplifier, but it does not account for the much larger 2,344 full-object read/hash operations.
- 2026-07-14: implementation replaced preview-only physical probes with `_preview_invoice_file_exists` in `_calculate_import_preview_audit` and `_process_import_zips(..., persist=False)`. Verified `minio://`/`s3://` references are treated as present during classification; persisted imports still use `_stored_invoice_file_exists`, and local/unknown references fall through to the physical check.
- 2026-07-14: `PostgresEtcImportSessionStore.save_preview` now returns the already-built `persisted` session after verified archive writes and repository commit, removing the immediate `self.get`/whole-session object re-download without changing later validate/worker durable reload behavior.

## Eliminated

- ZIP/XML parsing as the primary cause: the 120-invoice mixed archive regression completes far below the proxy deadline, while the attachment-read multiplication occurs even with an empty upload list.
- Reconciliation task loading or repeated task persistence as the primary cause: the route loads the task once; the dominant multiplication is over all previously imported ETC invoices inside `EtcService`, after task lookup.
- Nginx timeout configuration as the root cause: the absent `proxy_read_timeout` explains why the client sees HTML 504 at about 60 seconds, but increasing it leaves unbounded synchronous work and resource usage unchanged.
- Global requirement matching as the sole cause: microbenchmarks confirm exponential behavior is possible for ambiguous unsatisfiable candidate sets (and should be bounded separately), but a normal unique 59-to-59 match completed in 0.0025 seconds and the production-size 2,344 remote reads happen regardless of matcher shape.
- Durable session writes as the sole cause: they occur after the deterministic historical-attachment scan. They materially extend the same request, but removing them alone leaves the primary O(existing invoices × object downloads) defect.

## Resolution

- root_cause: `EtcImportPreviewService._build_preview` calls `EtcService.inspect_import_zips` twice (`backend/src/fin_ops_platform/services/etc_import_preview_service.py:134-146`). Each inspect rebuilds existing-invoice attachment state in both `_process_import_zips(..., persist=False)` and `_calculate_import_preview_audit`, and both builders call `_stored_invoice_file_exists` for XML and PDF on every existing invoice. With 293 production invoices, the preview performs 2,344 serial SQL + full MinIO GET/size/hash operations before saving the 59 uploaded ZIPs. The proxy reaches its 60-second upstream read deadline and returns the observed HTML 504. Serial verified storage plus `save_preview -> self.get` adds 59 immediate final-object re-downloads and worsens the timeout.
- fix: implemented `_preview_invoice_file_exists` in `EtcService`: preview classification trusts only verified object-reference schemes (`minio://` and `s3://`) and otherwise retains the existing physical check. `_calculate_import_preview_audit` uses the preview helper; `_process_import_zips` selects the helper only when `persist=False`, so actual writes retain physical attachment verification. `PostgresEtcImportSessionStore.save_preview` returns `persisted` after verified writes and repository commit instead of immediately reloading every archive. Nginx timeout was not increased, and the two-inspection/matcher structure was not broadly refactored.
- verification: added `EtcServiceTests.test_preview_does_not_download_verified_object_attachments_for_existing_invoices` and `EtcImportSessionStoreTests.test_durable_save_does_not_redownload_archives_after_verified_write`. Main-track verification reports 49 targeted ETC tests passing, Ruff passing on changed Python files, and docs verification passing. Diagnostic verification also covered CodeGraph call-chain/impact inspection, production read-only task/invoice/storage telemetry, the exact 293-invoice call-count probe, the 120-invoice parser regression, and matcher microbenchmarks. The full `tests/test_etc_backend.py` run remains blocked by pre-existing unrelated dirty workbench behavior (`Durable Workbench matching dirty queue is unavailable`; a workbench job is stuck in `persist_items`), not by these ETC changes. A post-deploy real 59-ZIP production smoke remains necessary.
- files_changed:
  - `backend/src/fin_ops_platform/services/etc_service.py`
  - `backend/src/fin_ops_platform/services/etc_import_session_store.py`
  - `tests/test_etc_backend.py`
  - `tests/test_etc_import_session_store.py`
  - `docs/modules/imports-etc-invoices/boundary-io.md`
  - `docs/modules/imports-etc-invoices/implementation-notes.md`
  - `docs/modules/imports-etc-invoices/tests.md`
  - `.planning/debug/etc-invoice-preview-504.md`
