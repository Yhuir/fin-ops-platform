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

## 第二轮生产结果与继续门禁

- SHA `1be049026` / release `main-1be04902-20260720032126` 标准部署成功；API、dispatcher 与 22 workers active，release identity一致。
- 20 次测量：页面壳 p95 `114.584ms` pass；all list p95 `244.072ms` pass；2026-07 list p95 `541.278ms` fail但20/20 fresh、零 enqueue；Page Audit p95 `294.511ms` pass。
- 补充 durable freshness实现后，application/legacy no-OA目标组通过；真实 disposable PostgreSQL应用全部 migrations并通过 mixed-source fail-closed integration test。全量 repository boundary组仍有已知 cost-statistics fan-out fixture failure，与本 diff无关且未修改断言。
- 下一门禁仍是新 SHA部署后的相同20次采样；month list未达到 `<=500ms` 前不进入写验证。

## 最终生产读结果

- SHA `a5e5b795a` 已部署为 release `main-a5e5b795-20260720032959`；API、dispatcher 与 22 个 workers active，migration 0001–0111 current。
- 20 次测量全部通过：页面壳 p95 `130.237ms`；all list p95 `272.284ms`；2026-07 month list p95 `260.943ms`；Page Audit p95 `322.560ms`。80/80 响应成功，两个列表均 20/20 `fresh` 且零 enqueue。
- 详情读取分别选择 1-row 与 33-row 批次，各测量 20 次：small detail p95 `175.940ms`，large detail p95 `337.446ms`；40/40 低于 `500ms` 门槛。
- `bank-flow-rule-batches`、`reconciliation-workbench`、`bank-details`、`turnover-ledger`、`cost-statistics` 五个直接/上下游 Page Audit 均为 `pass / fresh / drained / ready`、0 issue。

## 生产写验证安全门

- 按运行手册在首个生产 mutation 前执行 `app-health-operations` 全系统 Audit。门禁返回 `issues_found`：`tax-offset`、`input-invoice-usage`、`output-invoice-collections`、`settings` 四个既有页面 integrity 未通过；freshness 仍为 fresh、queue drained。
- 安全门在任何业务写之前终止，确认本轮未创建、提交、撤回或修改任何生产批次/关系/业务数据。
- 这四个页面不属于第 3 项允许修改的模块范围；为保持九页面严格串行和无污染 I/O，本阶段不绕过全系统写门禁，也不跨模块夹带修复。submit→fresh→withdraw→fresh 的受控生产写证据移入主控流程最终系统门：相关页面完成且全系统预检通过后再执行。
- 因此第 3 项代码、生产读性能、详情性能、目标页 Audit 与跨页只读隔离已达到门槛；唯一延后项是被全局前置门禁阻止的真实生产写样本，不得误报为已执行。
