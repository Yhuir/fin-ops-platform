---
status: complete
completed_at: 2026-07-27
scope: reconciliation-workbench
---

# 关联台 PostgreSQL canonical facts 直读总结

## 完成内容

- initial、groups 分页、group detail、row detail、ignored rows 和 relation preview 已切到 `PostgresWorkbenchCanonicalQueryRepository`。
- 页面 repository 在一个 `REPEATABLE READ READ ONLY` snapshot 内组合 canonical OA、银行、发票、ETC facts 与 active formal relations；固定服务端分页、批量 hydration 和 2 秒 statement timeout。
- 删除页面 generation/Redis/freshness/status/SSE/polling/202/fallback 运行时链，公开 payload 不再含 read-model/source-version 字段。
- 前端移除 `expected_read_model_version`，mutation 成功后直接重新 GET。
- relation UoW 在同一写事务内重新验证 canonical identities/types；active ownership、business version、idempotency 和 audit 继续由正式 relation command/repository 保护。
- 更新 reconciliation-workbench、workbench-relations、canonical-facts、batch-accounting、permissions-and-audit、API、app architecture 和 monitoring 文档。

## 删除内容

- `workbench_events_active_stream_registry.py`
- `workbench_groups_page_cache.py`
- `workbench_query_freshness_service.py`
- `workbench_refresh_status_payload.py`
- `workbench_refresh_status_payload_provider.py`
- 对应页面独占 tests、server routes、frontend API/types/polling/SSE/write gate 分支。

## 共享 HANDOFF

- Workbench active-generation tables/builder/worker/manifest/registry/env。
- `PostgresReadModelRepository` generation readers 和 batch-accounting 专属 loaders。
- `workbench_relation` distribution/worker/freshness facade。
- generation consistency/Audit/repair/retention/diagnostic tools。

这些资源仍有 batch-accounting、App Health/Audit 或运维调用方，本任务未删除。

## 验证

- `bash scripts/verify.sh lint`
- 关联台及范围外回归后端套件：757 tests passed。
- 关联台 Vitest：131 tests passed。
- `npm run build`：passed。
- `npx playwright test e2e/workbench-stale-error-flow.spec.ts --project=chromium`：7 passed。
- `bash scripts/verify.sh docs`
- `git diff --check`

## 性能证据与风险

- default empty initial 固定 10 条数据库语句（含 transaction setup）；groups 固定 4 条；missing group/row detail 各 3 条；transaction selection validation 固定 1 条。
- 最大 page size 200 仍一次 hydration；20-row preview 每种 canonical kind 一次批量 loader。
- recording-double empty initial 小于 100ms；repository statement timeout 为 2 秒。
- 本机没有 `FIN_OPS_TEST_POSTGRES_URL`，未取得真实 PostgreSQL planner、最大月份/`all`、连接池并发或生产 p95 证据；这些由主控合并部署后验证。
