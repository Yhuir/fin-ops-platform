---
status: resolved
trigger: "关联台 OA／流水／发票详情抽屉在生产仍加载失败；执行共享详情合同根因修复、提交推送 main、部署并验证生产链路与性能。"
created: "2026-07-31"
updated: "2026-07-31"
---

# Debug Session: workbench-detail-drawer-failure

## Symptoms

- Expected: 关联台列表展示的 exact stable generation 对 OA、银行流水、发票详情都可读；详情 GET 为纯读，打开详情不改变 generation、dirty scope 或 outbox。
- Actual: 生产详情抽屉仍显示加载失败；同一链路可出现 404 `workbench_row_not_found`，随后 generation 切换又出现 409 version conflict。
- Error evidence: `WorkbenchQueryFacade.row_detail(...)` 把 stale source versions 映射为 404，并以 `api_row_detail_source_versions_stale` enqueue refresh；前端把 row-not-found 与 version conflict 一起整页刷新并重试。
- Timeline: 2026-07-30 提交 `f44c60213` 增加 repeatable-read、发布完整性门禁和一次前端重试，但生产症状仍存在。
- Reproduction: 在生产关联台打开 OA／流水／发票详情；使用列表 exact read-model version 请求 `/api/workbench/rows/{row_id}`，同时观察返回合同、active generation、dirty scopes 与 outbox。

## Current Focus

- hypothesis: 共享详情 facade 破坏 stable-generation 读取合同并在 GET 内触发 refresh；前端错误地把真实 404 当成 version conflict 重试。此前完整性门禁可阻止新坏 generation，但错误合同仍掩盖既有 invariant breach。
- test: 分别锁定 stable-but-stale 返回 200 且零 enqueue、真实 row miss 返回 404、可见行缺详情返回独立 503、version conflict 返回 409；OA／流水／发票共享前端仅对 409 重载一次。
- expecting: 三类详情使用列表 exact version 均成功；连续读取不新增 dirty/outbox、不改变 generation；错误码可区分 404/409/503；详情 p95 小于 1 秒。
- next_action: 读取生产部署/验证入口并先做只读生产基线；随后用最小共享边界修复与回归测试证明根因。

## Evidence

- 2026-07-31: `main` 与 `origin/main` 同为 `b0d0155c9`，工作区在创建本调试记录前干净。
- 2026-07-31: CodeGraph 确认详情调用链为 React `fetchWorkbenchRowDetail` -> Workbench row route -> `WorkbenchQueryFacade.row_detail` -> `PostgresReadModelRepository.get_workbench_row_detail`。
- 2026-07-31: facade 当前在 stale source versions 分支执行 enqueue，随后返回 404 `workbench_row_not_found`。
- 2026-07-31: frontend `isWorkbenchReadModelRejected` 当前把 404 row-not-found、stale/not-fresh 和 409 version conflict 合并为同一重载重试条件。
- 2026-07-31: 既有发布门禁与 active consistency Audit 已检查可见非 summary group row 必须有同 generation `workbench_rows` 详情行。
- 2026-07-31: 生产首屏 218 个可见 row 的并发 6 基线中，11 个请求先返回伪 404 并触发 refresh，随后 205 个请求因 generation 切换返回 409；active generation 从 `...1e163b...` 变为 `...2713d2...`，刷新收敛后再次变为 `...e29d33...`。OA 45 个全 409；银行 128 个为 11×404、2×200、115×409；发票 45 个全 409。
- 2026-07-31: 最小修复已删除 row detail 第二次 source freshness proof 与 GET enqueue；新增 404/409/503 分层、miss 冷分支 invariant 检查、前端 409-only retry/abort 和 summary 非详情入口。
- 2026-07-31: 本地目标回归通过：backend 224 passed；frontend 156 passed。

## Eliminated

- 三个独立 UI 组件故障：OA、流水、发票共用同一详情状态机、API 和后端 facade/repository。
- 浏览器缓存：失败发生在带 exact generation/version 的服务端 API 合同中。
- 缺少 repeatable-read：`f44c60213` 已增加同快照校验；当前剩余错误发生在快照读取后的 facade stale 分支。

## Resolution

- root_cause: row detail 在 exact active generation 快照成功读取后又对最新 canonical source 做第二次 freshness proof；mismatch 被错误映射为 404 且 GET enqueue refresh，前端又把 404 当 409 重载重试，形成伪缺失、代际切换与后续冲突级联。
- fix: stable generation detail 直接纯读返回；404/409/503 精确分层；detail miss 冷分支只检查 active group membership、不读 payload fallback；前端只对 409 重试一次并 abort 关闭/替换请求；summary 不提供 row detail。
- verification: 生产修复前 218-row 基线复现级联；本地目标 backend 224、frontend 156，全量 backend 3850、frontend 884、Chromium 158、Ruff/docs/build 全部通过。生产修复后验证由本次发布门禁与独立详情矩阵继续关闭。
- files_changed: shared row-detail error/repository/facade、Workbench drawer/API/card、对应 backend/frontend tests、Workbench module/API docs。
