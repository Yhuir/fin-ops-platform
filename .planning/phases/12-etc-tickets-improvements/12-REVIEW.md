---
status: issues_found
phase: "12"
depth: standard
files_reviewed: 22
findings:
  critical: 5
  warning: 5
  info: 1
  total: 11
---

# Phase 12 ETC Tickets Code Review

## 结论

Phase 12 的三 bucket、窄读和锁外 OA I/O 方向合理，但当前实现还不能判定为可安全部署。审查发现 5 个 Critical：两个前端跨批次错对象操作风险、一个 OA finalize 部分提交无法收敛、一个跨进程全量 snapshot 覆盖风险，以及一个会掩盖长期 creating 的 Audit 时间源缺陷。

本报告只做静态/结构审查；未修改业务代码、未运行部署或生产操作、未提交。CodeGraph 已用于确认 `save_etc_state` 的调用/影响面，显示 ETC API、import/service 写入共同汇入同一全量 snapshot 持久化边界。

## Critical

### CR-01：暂存列表的显式批次操作会被旧 `draftResult` 改写为另一个批次

- **证据：** `web/src/pages/EtcTicketManagementPage.tsx:1757-1761` 中 `resolveOaActionBatch(batch)` 只要存在 `draftResult` 就无条件返回它，忽略调用方显式传入的 `batch`；暂存列表按钮在 `web/src/pages/EtcTicketManagementPage.tsx:1859-1873` 明确把当前行 batch 传给该 handler。`draftResult` 在用户关闭创建结果弹窗时不会清除（`web/src/pages/EtcTicketManagementPage.tsx:2954-2989`）。
- **可复现路径：** 创建批次 A 的 OA 草稿后关闭弹窗但不确认；切换到“暂存”，选择批次 B；点击 B 的“已提交”或“未提交”。请求仍使用 A 的 `businessBatchId/version`。
- **影响：** 用户可在看到 B 时修改 A，属于错误对象写入和业务数据完整性问题。
- **修复门：** 显式 `batch` 必须优先于 transient `draftResult`；关闭/切换 selection 时要么清理 transient target，要么仅让弹窗专用 handler 使用它。新增至少两个 staged batches 的组件/E2E 测试，断言按钮请求的 ID/version 等于当前行。

### CR-02：切换批次后旧 `selectedTask` 仍可操作，可能把上传/核对写到上一批次

- **证据：** selection effect 在 `web/src/pages/EtcTicketManagementPage.tsx:872-900` 开始新 detail 请求时没有同步清空 `selectedTask`，直到新 batch detail 返回后才设置 `taskLoading` 并请求新 task；行切换只清空两个 batch detail（`web/src/pages/EtcTicketManagementPage.tsx:2179-2183`）。任务可写性只依赖旧 `selectedTask`（`web/src/pages/EtcTicketManagementPage.tsx:1254-1255`），上传、确认、删除源文件等控件没有受 `detailLoading` 阻断。
- **可复现路径：** 批次 A task 已加载且可写；点击批次 B，在 B detail 尚未返回的窗口内点击上传、确认核对或删除来源；handler 仍携带 A 的 task ID/version。
- **影响：** UI 当前选中 B，但 mutation 落到 A，属于跨批次污染 I/O。
- **修复门：** selection 改变时同步清空 task/task errors 并立即进入 task loading，或把 task 状态与 businessBatchId 绑定且所有 mutation 校验 owner ID；增加延迟 detail/task 请求的交互测试，证明切换期间所有 task mutation disabled 且不会请求旧 task。

### CR-03：OA batch finalize 与 reconciliation task 元数据分两次持久化，第二次失败后没有可重放修复路径

- **证据：** `EtcService.complete_business_batch_oa_draft` 先把 business/submission batch 持久化为 pending（`backend/src/fin_ops_platform/services/etc_service.py:1176-1202`），应用服务随后才独立调用 `record_oa_draft_created`（`backend/src/fin_ops_platform/services/etc_business_batch_application_service.py:283-297`）。如果第二次持久化失败，batch 已是 `oa_confirmation_pending`；下一次相同 create 请求会先被 action contract 拒绝（`backend/src/fin_ops_platform/services/etc_business_batch_application_service.py:279-281`、`:43-54`），无法进入 service 的相同-key replay。管理员 recover 也只接受 creating（`backend/src/fin_ops_platform/services/etc_service.py:1261-1268`），恢复采纳路径存在同样的先 batch、后 task 分裂（`backend/src/fin_ops_platform/services/etc_business_batch_application_service.py:317-334`）。
- **影响：** 数据库/任务 store 短暂失败可留下“batch 已暂存、task 未登记草稿”的永久半写状态；客户端得到失败但无法安全重试收敛。当前 Page Audit 也没有核对 task 的 `oa_draft_batch_id/oa_draft_status/etc_batch_id`，因此可能仍显示通过。
- **修复门：** 不要求新增通用框架，但必须选择一个现有持久化边界闭合这两个事实：同事务写入，或允许 pending 同-key replay 幂等补齐 task metadata；recover adoption 也必须可幂等补齐。补应用服务 partial-failure 测试：第一次 task persist 失败、第二次同-key 调用收敛且不创建第二个 OA/submission batch；Audit 必须识别未补齐 task metadata。

### CR-04：锁外 OA I/O 后仍用进程内旧 snapshot 全量 upsert，可能覆盖独立 import worker 的并发更新

- **证据：** prepare 后释放进程内 `RLock`，OA I/O 完成后 finalize 直接修改原内存对象并调用 `_persist()`（`backend/src/fin_ops_platform/services/etc_service.py:1171-1202`、`:2602-2605`）。`save_etc_state` 不是 target batch CAS，而是遍历并 upsert snapshot 中全部 invoice/import/submission/business batch（`backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py:931-1082`）；business batch conflict update 直接覆盖 status/version/raw payload，没有 `where version = expected` 条件（`:1048-1065`）。CodeGraph impact 也确认 import/service/API writers 共用该入口。
- **可复现路径：** API 进程 prepare A 后等待 OA；独立 import worker 更新已有批次/发票 B；API finalize A 使用 OA 前的内存 snapshot 全量保存，把 B 的新 status/version/raw payload 回写成旧值。
- **影响：** 锁外 I/O 本意是隔离性能，但当前持久化粒度会把等待窗口扩大为跨进程 lost update，可能污染其他 ETC 批次和 worker 结果。
- **修复门：** finalize/fail/unknown/recover 只持久化本次 attempt 涉及的 business batch、submission batch、invoice/import 引用，并在 PostgreSQL 使用 version/attempt 条件更新；或 finalize 前重新加载并合并非目标 facts，但不能用无条件全量 snapshot 覆盖。增加两个独立 service/store 实例的并发测试，证明 B 的 worker 更新不会被 A finalize 回滚。

### CR-05：Audit 用会被任意 ETC 全量保存刷新的 formal `updated_at` 判断 creating 超时

- **证据：** stale 判定优先取 formal row `updated_at`（`backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py:734-735`）。但每次 `save_etc_state` 都 upsert 全部 business batches，并对每个 conflict 执行 `updated_at = now()`（`backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py:1055-1065`），即使该 creating batch 的业务 payload/version 没变。
- **影响：** 只要系统内其它 ETC 批次持续有导入或操作，一个已永久卡死的 `oa_draft_creating` 就会不断刷新 formal 时间，永远达不到 15 分钟门槛，Page Audit 可错误通过。
- **修复门：** stale clock 必须来自目标 batch 的 durable attempt 时间（payload `updated_at`、`oa_draft_prepared`/`oa_draft_outcome_unknown` 事件时间或专用现有事实），不能使用全量 upsert 的物理行时间。新增“无关批次保存刷新 formal updated_at，但目标 payload attempt 已超过 15 分钟”测试并断言 fail。

## Warning

### WR-01：缺失 reconciliation task 被当成 OA action ready

- **证据：** `evaluate_etc_oa_draft_action` 仅在 task 非空时校验状态，task 为 `None` 直接返回 ready（`backend/src/fin_ops_platform/services/etc_business_batch_application_service.py:62-71`）；command 的 `_assert_reconciliation_task_allows_oa_draft` 同样在 task 缺失时直接返回（`:541-550`）。
- **影响：** canonical task 丢失/查询异常的 batch 仍可创建 OA 草稿，随后跳过 task 元数据登记；这与“对账任务已完成才可提交”和 fail-closed 要求相反。
- **修复门：** task 缺失应返回稳定 `reconciliation_task_missing` action/command 错误；补 list/detail/command 三处共用资格测试。

### WR-02：管理员恢复接口把任意非空值强转为 `confirmedNotCreated=true`

- **证据：** `backend/src/fin_ops_platform/app/routes_etc.py:203-212` 使用 `bool(payload.get(...))`；JSON 字符串 `"false"`、`"0"` 等都会被解释为 true，且 route 没有类型校验。
- **影响：** 管理员或脚本发送类型错误时可能把真实结果未知的 attempt 错误标记为“确认未创建”，随后允许新建第二个 OA 草稿。
- **修复门：** trust boundary 只接受 JSON boolean；缺失、字符串、数字全部 400/422。补错误类型和 mutually-exclusive recovery contract 测试。

### WR-03：业务 detail 与精确 task 仍串行形成不必要瀑布

- **证据：** summary 已包含 `taskId`，但页面先等待 business detail（`web/src/pages/EtcTicketManagementPage.tsx:876-881`），再发起 task detail（`:882-884`）。
- **影响：** “核心详情 ready”耗时至少为两个请求之和；固定 I/O 次数测试无法证明高性能 wall time。
- **修复门：** selection 确定后用 summary `taskId` 并行请求 business detail 与精确 task，仍各一次且共享同一 AbortController；错误分别渐进展示。增加 deferred-promise 测试证明 task 不等待 business detail 才发出。

### WR-04：人工确认后会重复请求同一 bucket list

- **证据：** `handleManualBusinessBatchOaStatus` 先 `setActiveStatus(nextStatus)`，又显式 `await loadBatches(undefined, nextStatus)`（`web/src/pages/EtcTicketManagementPage.tsx:1816-1824`）；`activeStatus` 改变会重建 `loadBatches` 并再次触发 effect（`:821-859`）。
- **影响：** 每次 staged→submitted/unsubmitted 都会产生两个相同 list GET，增加写后可见耗时和数据库负载，违反固定热链预算。
- **修复门：** 状态切换只保留一个 reload owner；补 mutation 后 network count 测试，断言 list GET 恰好一次。

### WR-05：Audit 把 not-submitted 的历史成员关系继续计为当前 owner，可能误报合法重用

- **证据：** 对 not-submitted，代码正确地把 expected current owners 设为空（`backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py:491-502`），但随后仍把其 retained `invoice_ids` 加入 `linked_invoice_owners`（`:513-515`），并对任何两个 visible batches 的 retained membership 报 multiple owners（`:590-597`）。
- **影响：** not-submitted 释放 invoice 后，如果该 invoice 被另一个合法 batch 使用，旧 batch 为保留核对历史仍声明 membership，Audit 会把“历史 membership + 当前 owner”误报成两个当前 owner，使正常操作后 audit 不通过。
- **修复门：** multiple-current-owner 只统计会占用 invoice 的状态；not-submitted retained membership 另做 referential/history check。补“旧 not-submitted 保留成员、新 active batch 成为 current owner”的合法 fixture。

## Info

### IN-01：新增但未使用的恢复权限异常类

- **证据：** `backend/src/fin_ops_platform/services/etc_service.py:173-174` 定义 `EtcOADraftRecoveryPermissionError`，全仓无调用；实际权限错误使用 `EtcBusinessBatchScopeError`。
- **影响：** 形成无 owner 的死代码，与本阶段“删除旧/无调用链代码”的目标不一致。
- **修复门：** 删除该类；无需新增抽象或兼容分支。

## 已检查且未发现问题的范围

- 三 bucket 映射本身：`oa_confirmation_pending` 单独映射 staged，submitted 状态集合与前后端一致。
- not-submitted 主状态变更：当前 service 会清除 submission/draft/current owner，同时保留 business batch 的 invoice/import/history 成员。
- list/detail 热读：页面不再调用 full reconciliation task list；PostgreSQL list 为 count+page 两条 SQL，detail 为 batch+invoice+task 三条窄读；summary response 不输出 invoice IDs/import attempts/audit events；list/detail mapper 不探测对象存储。
- 权限主门：mutation route 先要求 mutation permission，recover application service 再要求 admin；detail/list 使用 actor owner/org scope。
- 外部 OA I/O 确实已移出进程内 business lock；问题在其后的 durable 写入粒度/CAS，而不是锁外方向。
- 正式 reconciliation/import/source-file API 仍有页面或导入 owner，未发现被错误删除；新 ETC 页面 production source 未重新引入 full task list helper、旧双 selection 或 legacy `/api/etc/batches*`。

## 测试证明缺口

现有测试覆盖单批次 happy path、service 内同 key、单进程锁释放、固定 SQL/object-store 次数和基础 Audit fixture，但没有证明以下关键合同：

1. 两个 staged batches 时显式行操作不会被 transient draft target 覆盖。
2. 慢 detail/task 切换期间不会对上一 task 发 mutation。
3. business finalize 成功、task metadata 持久化失败后的同-key收敛。
4. 独立 API/worker service 实例并发写时不会 lost update。
5. unrelated snapshot save 不会刷新 creating 的业务超时钟。
6. not-submitted retained membership 被新 batch 合法重用时 Audit 仍通过。
7. manual status 写后只有一次 list reload，task 与 business detail 并行且各一次。

## 审查文件

- Backend routes/DI/service/store/repository/Audit：10 files。
- Backend tests/architecture guards：3 files。
- Frontend page/API/types/styles：4 files。
- Frontend unit mocks/tests：3 files。
- Playwright spec/mock：2 files。

总计 22 个源文件；另读取 Phase 12 PLAN/SUMMARY 与 ETC boundary-io/state-machine/tests 合同用于验收对照。
