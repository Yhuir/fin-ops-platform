---
phase: 38-etc
plan: "01"
subsystem: ui
tags: [react, heroui, etc, workflow, playwright, performance]
provides:
  - One ETC batch rail and one continuous right workflow surface
  - Four-stage lifecycle projection derived only from existing batch and task facts
  - Removal of page-level plate and keyword UI/request paths
affects: [etc-tickets, imports-etc-invoices, reconciliation-workbench]
tech-stack:
  added: []
  patterns: [pure presentation projection, existing request cancellation, native CSS layout]
key-decisions:
  - "Keep the backend optional filters and formal ETC APIs; remove only the obsolete page-owned search path."
  - "Derive progress in O(1) from already loaded facts and add no stage API, store, timer, read model, worker or dependency."
  - "Use existing HeroUI controls and CSS; keep mutation handlers, permission checks and stale-selection guards unchanged."
requirements-completed: []
completed: 2026-08-01
---

# Phase 38 Plan 01：ETC 票据页面生产闭环

ETC 票据页现已收口为左侧批次 rail 与右侧连续工作面；车牌/关键词前端链路和重复卡片壳已删除，四阶段摘要只投影现有批次、核对、导入和 OA 事实。

## 完成内容

- 三个 bucket 与批次列表合并到单一左 rail；当前批次、四阶段、摘要、任务和记录按一条连续纵向链路排列。
- 新增语义化 `ol` 四阶段：准备核对资料、确认核对结果、导入 ETC 发票、提交 OA 审批；覆盖处理中、失败、部分失败、人工确认、回退、冲突和完成态。
- 删除页面 `plate`/`keyword` state、输入框、请求参数、effect 依赖、旧筛选样式和旧外层卡片 selector；后端/API client 的正式可选参数保持兼容。
- 保留上传、核对、reopen、导入、下载、OA 恢复、人工确认、删除、权限、AbortController 和 stale task 防护。
- 桌面 rail 使用 sticky；390px 窄屏只显示当前阶段，独立导入入口和三 bucket 仍可访问。
- 未新增 npm 包、API、数据库状态、缓存、read model、worker、timer、全局 listener 或并行 fallback。

## 本地验证

- ETC 页面/API 目标 Vitest：101/101 passed。
- 全量前端：73 files，903/903 passed；production build passed，ETC page chunk 68.33kB / gzip 21.31kB。
- ETC + 独立 ETC 导入 Chromium：14/14 passed，其中 ETC 9/9、导入 5/5。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 全部通过。
- 全量 Chromium 前两轮均为 157/158，分别暴露未修改的 OA 待付款和销项收款 mock 首次请求时序波动；两个精确失败用例隔离重跑均通过，未放宽断言。最终完整复跑 158/158 passed。
- 本机 `runtime-check` 因开发环境未配置生产专用 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 而 fail-fast；生产发布门禁使用真实 PostgreSQL runtime contract 验证，不以本地非生产配置替代。

## 发布与生产验证

- 实现提交：`af00cefece8f3420c46bba709e092165f2718dc2`，已推送 `origin/main`。
- Active release：`main-af00cefe-20260801041334`；API、RabbitMQ dispatcher 与 10 个 required worker 均 active，并从该 release 目录运行。
- 发布门禁经过 pre、T+0、T+60、T+300 后保持 candidate active，未回滚；随后 admin AppHealth 和 16-route shell 均通过，mutation 0。
- 生产 ETC 首屏只读 I/O 为 bucket list、精确 batch detail、精确 task；全部 200，list query 仅含 bucket/page/page_size，stepper 新增请求为 0。
- 生产真实已提交批次显示四阶段全部完成；旧搜索输入和旧容器均为 0，桌面 sticky rail/4 列流程/0px 连续面边界符合合同。
- 12 次暖读：list p95 174.9ms、detail p95 102.0ms、task p95 327.3ms，均低于 1s。
- 桌面滚动 118 帧：p50 16.7ms、p95 18.0ms、max 18.4ms；CLS 0.001479，100ms 以上 long task 0。
- 390×844：只显示一个当前阶段、页面横向溢出 0、frame p95 18.4ms、导入入口正确，mutation/console error 均为 0。

## 七类测试评估

1. **Business core：不适用。** 未改变金额、匹配、权限决策或后端状态转换；四阶段是只读展示投影。
2. **Service layer：不适用。** 未改变 service、repository、持久化、审计或后台任务。
3. **API contract：没有变更，回归适用。** `EtcApi` mapper/request 测试和生产 list/detail/task 200 保护既有 response shape；页面不再发送 plate/keyword。
4. **Read model/cache/background job：不适用。** ETC 页面仍为 direct canonical read；发布门禁和 AppHealth 验证现有 queue/worker 健康。
5. **Frontend component/interaction：适用且已覆盖。** 903 个 Vitest 包含 loading/empty/error/permission、三 bucket、四阶段状态矩阵、切换竞态和旧路径负向合同。
6. **E2E business flow：适用且已覆盖。** 本地 ETC/独立导入 14 个场景和生产 ETC/16-route 只读链路覆盖关键跨模块读路径；未写入真实业务数据。
7. **Existing regression：适用且已覆盖。** 全前端、构建、目标/全量 Chromium、生产 route shell 与 AppHealth 共同保护其它页面、导入和 Workbench。

## 剩余风险

- 生产验证按安全边界保持只读，没有创建批次、导入发票或提交真实 OA；写路径由本地确定性组件/E2E 和既有后端合同保护。
- 生产 bucket 从空的未提交切到 7 条已提交时产生 CLS 0.001479，远低于 0.01 本轮严格线和 0.1 Web Vitals 良好线，但不是绝对 0，已保留为真实监控基线。
