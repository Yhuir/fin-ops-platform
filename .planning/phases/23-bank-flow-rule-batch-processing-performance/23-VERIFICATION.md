# 第 3 项验证记录：流水规则批量处理链路

## 本地功能与边界

- 目标及隔离后端回归：459 tests passed。
- bank-flow application/route/producer/barrier/relation repository/Workbench 集成组：83 tests passed。
- 前端 page/API：2 files / 43 tests passed。
- Chromium 关键 Browser flow：最终 9/9 passed。首次运行在 reset 写后暴露自动选择标志被空列表清除，修复为跨空列表保持并先定点 1/1 通过，再全量复跑 9/9；没有放宽业务断言。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、TypeScript noEmit、production build、Python compile 和 `git diff --check` 通过。build 只保留既有依赖 CSS/chunk warnings。

## 真实 PostgreSQL

- 使用 visibly disposable 本地 test database，应用当前全部 migrations。
- `test_bank_flow_rule_batch_page_uses_sql_pagination_and_aggregate_summary` 通过：验证 `LIMIT/OFFSET` 当前页、过滤 total、draft presentation、完整 summary filter count/amount 和 fresh source proof。
- 测试数据库在命令退出时自动删除；未触碰生产 schema或业务数据。

## 七类测试

1. Business core：bank-flow schema/ID/error/display/idempotency、选择校验、submit/withdraw/reset状态与历史 ID。
2. Service：paged port、bulk bank read、bulk cancel、一次原子 persist、missing relation显式 batch delta、no-op reset。
3. API contract：分页/summary/freshness、权限/冲突/错误、mutation target envelope和正式 bank-flow error。
4. Read model/cache/job：真实 PostgreSQL paged aggregate、source proof、refresh producer/worker边界和零同步 reset rebuild。
5. Frontend：page size 50、command 后本地可见、后台 reconcile、reset target query、超时/失败/stale交互。
6. E2E：submit-selection、reset、internal transfer、withdraw、Workbench展示和规则保存 Browser 主链路。
7. Regression：no-OA legacy、Workbench relation、operation barrier、bank details和architecture guard。

## 待发布后补录

- 唯一 commit SHA和 release ID。
- 生产页面壳、all/month list、small/large detail、Page Audit 20次分位数。
- 可撤销安全样本的 submit/withdraw command、command-to-local-visible、month read model fresh、Audit/drain耗时。
- reset 不在生产擅自执行全量业务操作；使用生产历史真实操作证据或显式安全窗口，必要时以真实 PostgreSQL生产规模 fixture补足。
- bank-flow、Workbench、bank details、no-OA/turnover隔离 Audit以及 main/origin/main/工作树干净门禁。

## 首轮生产结果与继续门禁

- 已部署 SHA `a3a331b5577e892f4d47fd9f940b0a5f2bc3bf46` / release `main-a3a331b5-20260720030257`，runtime readiness `ready` 且 release identity 一致。
- 20 次测量：页面壳 p95 `108.923ms` pass；all list p95 `539.327ms` fail；2026-07 list p95 `720.336ms` fail 并出现一次 stale/enqueue；Page Audit p95 `265.977ms` pass。
- 因两个 list gate 未通过，本项未关闭。补充优化后目标测试 `103 passed`，`bash scripts/verify.sh lint` 通过；20,000 条 category 合成数据证明 canonical hash 相同，缓存命中从旧 copy+hash 约 `212.869ms` 降至约 `0.005ms`。
- 下一门禁：提交/推送补充代码、部署唯一新 SHA，重复同一 probe；只有 all/month list p95 均 `<=500ms` 且全部 fresh/零 enqueue，才进入安全写验证。
