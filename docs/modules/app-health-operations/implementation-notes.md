# 系统状态 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- App Health / App Status 是全局运行事实的只读投影，不是页面状态聚合器。前端只展示后端 `app_status`，不能用当前 route、表格 loading 或组件本地状态推导 green/yellow/red。
- 绿色状态必须有 readiness 证明。registry 中的 read model 如果缺少 readiness 记录，必须 busy/yellow；runtime snapshot unavailable 必须 blocked/red，不能空 green。
- Operations dashboard 是 admin-only 只读入口，不执行 retry、acknowledge、requeue、republish 或 repair。运维动作仍走 runbook/CLI/API 专门入口。
- Registry 强一致是本模块的核心防线：新增页面、read model、worker、job type 或 dependency 时，必须同步 domain/read model/job/dependency/worker registries 和测试。
- 本模块首轮闭环状态为 `documented-risk`：本地测试覆盖 service/API/UI contract，真实 systemd/RabbitMQ/Redis/Nginx SSE/大库指标仍需 staging/生产 smoke。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-12 - App Status current-effective blocker

- 目标：修复历史 cost statistics legacy scope、历史 dead-letter/outbox failure 把当前页面同步状态长期拖成 busy/failed 的问题。
- 影响范围：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`AppStatusOverviewService`、`/api/app-health.app_status.domains[]` 的诊断字段、App Health / App Status 文档、outbox App Status 热路径索引。
- 关键决策：`read_model_statuses[*].scopes[]` 只保留 current-effective scope；成本统计 legacy scope `all` 和裸 `YYYY-MM` 进入 `historical_scopes[]`。outbox `failed/dead_lettered/publish_failed` 只有在没有后续同 scope `done` 事件、且没有后续同 scope fresh readiness 时才参与当前状态。新增 `domains[*].historical_read_model_scopes[]` 只做历史诊断，不作为 fresh 证明。新增 `0067_app_status_current_effective_outbox_index.sql`，保护 App Status current-effective outbox 查询不退化为全表扫描。
- 文档影响：更新 `docs/dev/api-contracts.md`、`docs/app-architecture/runtime-and-ownership.md`、本模块 `state-machine.md` 和 `tests.md`。
- 测试覆盖：新增 legacy cost scope、historical read model scope diagnostics、covered outbox failure 回归测试；保留旧 missing/failed/worker/runtime unavailable/API contract 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v`。
- 未测风险：本地 fake connection 已覆盖语义；真实生产数据仍需要部署后 smoke `/api/app-health`，确认 historical failures 不再影响 current App Status，同时 repair 脚本仍需在后续阶段处理历史 dirty/dead-letter 记录。
- 后续事项：生产 repair 阶段应 dry-run 旧 cost statistics scope、covered dead-letter 和 readiness 记录，写审计/回滚记录后再清理；不要把语义过滤当作数据修复完成。

## 2026-06-11 - app-health-operations 测试闭环首轮

- 目标：补齐 App Health / App Status 的影响面、七类测试矩阵、状态机、验证命令和真实环境风险。
- 影响范围：`AppHealthOperationsPage`、`AppStatusIndicator`、`AppHealthStatusContext`、App Health API、App Status overview、RuntimeMonitoringRepository、registries、readiness backfill、runtime queue ops。
- 关键决策：不新增低价值代码测试；已有后端/前端测试覆盖主要状态优先级、API shape、runtime facts、registry、dashboard 和全局 icon 行为。本轮补齐文档闭环。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 app health/status/runtime monitoring/readiness/worker registry/runtime queue；前端覆盖 dashboard、App Status mapper/provider/icon、SSE/轮询和 BroadcastChannel。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Nginx/OA iframe SSE、真实大库 dashboard metrics、pg_stat_statements 配置。
- 后续事项：如果生产出现状态误判，先补 regression test 到 App Status overview 或 runtime repository，再登记到 `docs/dev/regression-bug-bank.md`。
