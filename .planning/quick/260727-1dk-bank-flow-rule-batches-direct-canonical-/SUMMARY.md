# 流水规则批次页面直读迁移总结

## 结果

- 页面列表、summary、分页和详情改为 PostgreSQL canonical query repository。
- 列表在一个 `REPEATABLE READ READ ONLY` snapshot 中固定执行 2 次 SELECT；详情固定执行 4 次。
- 正式关系只读取 `app.workbench_pair_relations.status='active'`。
- 页面/API 删除 read-model status/version、refresh enqueue、202 和后台 polling；每次成功写操作只重新 GET 一次。
- 保留 relation command、CAS、幂等、审计、冻结 requirement/tag metadata、内部转账金额和 changed-batch delta writer。

## 验证

- Backend target + no-OA/relation regression：147 passed。
- Runtime/auth boundary：220 passed。
- Frontend component/API/policy/relation regression：87 passed。
- Chromium 页面直读相关 8 条通过；共享 Workbench confirm-preview fixture 的旧 DTO 仍失败，已登记 HANDOFF。
- TypeScript noEmit、production build、ruff、docs gate 和 diff check 通过。
- Disposable PostgreSQL 在 projection 空表时验证 canonical list/summary/detail/active relation；测试库已删除。
- 10,000 批次本机样本：列表 p50 780.802ms / p95 1621.686ms，详情 p50 15.408ms / p95 17.266ms；组合 SQL execution 397.194–449.873ms，shared read blocks 0，不新增索引。

## 主控 HANDOFF

- whole-repo 清理 bank-flow read-model reader/refresh/producer/persistence、manifest/worker/App Status/deploy/RabbitMQ/Page Audit 和 projection table/migration references。
- 旧 refresh persistence 同时写 canonical batch/event 与 projection；删除 worker 前必须确认 canonical draft writer 或把候选完整收敛进 canonical query。
- 修复并重跑共享 Workbench confirm-preview fixture（BRB-E2E-003）。
- 合并后执行生产 HTTP 性能、权限/审计、可逆 submit/withdraw/reset、跨页回归和 deploy 验证。
