---
status: clean
phase: "12"
depth: standard
files_reviewed: 24
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
---

# Phase 12 ETC Tickets Code Review — Auto Iteration 3

## 最终结论

Phase 12 最终只读复审为 `clean`。原 11 项 finding 以及 iteration 2 的 CR-02R、WR-05R、CR-03R-L 均已在当前 HEAD 闭合；本轮没有发现新的可复现 correctness、权限、隔离、Audit、性能热链或旧代码污染问题。

当前实现保持既有 ETC 模块边界，没有新增 schema、migration、read model、cache、queue、worker、兼容 API、跨页面 fallback 或并行旧链。报告结论仅代表代码、合同和本地测试证明已达到 review clean；真实 PostgreSQL 竞争、真实 OA/对象存储和生产延迟仍属于统一部署后的外部门。

本轮使用 CodeGraph 复核 `record_oa_draft_created` 与 scoped attempt persistence 的影响面，并重新审查 Phase 12 全部 24 个 source/test diff。未修改业务代码、未运行部署或生产操作、未提交。

## Iteration 2 三项闭合证据

### CR-02R：异步 list 自动换选不再泄漏旧 task mutation

- `web/src/pages/EtcTicketManagementPage.tsx:820-824` 保存最新 selection owner，并从当前 business batch summary 唯一解析 `selectedBusinessBatchTaskId`。
- list response 自动选择新批次时，在提交 selection 前同步清除旧 `selectedTask`、旧 error 并进入 loading（`:841-855`）；行点击也同步更新 selection ref 并清除旧 task（`:2190-2198`）。
- 所有 task mutation 的唯一 target 额外要求 `selectedTask.taskId === selectedBusinessBatchTaskId` 且非 loading（`:1267-1270`）；上传、匹配刷新、patch、确认、reopen、删除来源文件均复用该 target，没有旁路 handler。
- `web/src/test/EtcTicketManagementPage.test.tsx` 的 deferred filtered-list fixture 证明 A 已可写、异步 list 自动选择 B 时 A 的上传 mutation 请求仍为 0；原行点击切换测试继续覆盖直接 selection 路径。

结论：CR-02 与 CR-02R 均 closed；mutation owner 不再依赖 passive effect 的执行时机。

### WR-05R：not-submitted 历史 membership 与新 current owner 正确分离

- `backend/src/fin_ops_platform/services/postgres_repositories/etc_tickets_page_audit.py:799-816` 只在 retained invoice 没有 current business owner 时要求其保持 `unsubmitted`；若仍由旧 subject 占用，继续报告 `batch_occupancy`。
- 新 owner 若为 submitted batch，现有 submitted lifecycle 会独立校验 submission=`submitted_confirmed`、invoice status=`submitted`、formal business owner 和 submission current owner（`:830-853`）。未知/不可见 owner 仍由 invoice-owner referential rule 报错，没有放宽为静默通过。
- `tests/test_audit_etc_tickets_read_model_tool.py` 把合法复用 fixture 推进到完整最终态：新 batch=`manually_marked_submitted`、submission=`submitted_confirmed`、invoice formal/payload status=`submitted`、owner 指向新 batch/submission，并断言整页 Audit `pass`。

结论：WR-05 与 WR-05R closed；旧批次保留历史成员不会误报，新 owner 的生命周期仍负责当前占用完整性。

### CR-03R-L：本地持久化失败不再留下 dirty task memory

- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py:1066-1085` 在写 OA metadata 前复制完整 task 并记录 audit counter；`_persist()` 任意异常都会恢复 task、version、metadata、audit event 与 counter，再原样抛错。
- `_copy_task` 通过 snapshot mapper 重建 task（`:1703-1704`），回滚副本不会与已变更对象共享可变列表。
- `tests/test_etc_reconciliation_service.py::test_record_oa_draft_created_rolls_back_local_memory_when_persist_fails` 使用真实 `EtcReconciliationTaskService + ApplicationStateStore` 的 fail-once store，证明首次失败后同进程状态完全回滚；第二次重试后新 store 实例能读到 metadata，且只有一个 durable `oa_draft_created` event。
- PostgreSQL 路径原有 `get_task()` durable reload 与 same-key/recovery replay 保持不变；本轮回滚没有新增 fallback 或改变 API shape。

结论：CR-03、PostgreSQL replay 与 CR-03R-L 均 closed。

## 原 11 项最终复核

| Finding | Verdict | 最终证据 |
| --- | --- | --- |
| CR-01 | closed | 显式 staged row batch 优先于 transient `draftResult`；双 staged row 测试锁定正确 ID/version。 |
| CR-02 | closed | 行点击和异步 list 自动换选均同步失效旧 task；所有 mutation owner-bind 当前 summary task ID。 |
| CR-03 | closed | pending same-key 与 recovery adoption 可幂等补齐 task metadata；PostgreSQL reload 和本地失败回滚均可收敛，Audit 校验三项 metadata。 |
| CR-04 | closed | OA prepare/finalize/fail/unknown/recover 只走 target-scoped attempt save；PostgreSQL 同事务 row lock/version CAS 阻止旧 snapshot 覆盖。 |
| CR-05 | closed | creating stale clock 只取 durable attempt event/payload time，不使用会被无关 upsert 刷新的 formal row `updated_at`。 |
| WR-01 | closed | missing linked task 在 list/detail action 与 command 均 fail closed 为 `reconciliation_task_missing`。 |
| WR-02 | closed | recover decision 只接受唯一 JSON boolean；采纳与确认未创建证据严格互斥、完整。 |
| WR-03 | closed | summary task ID 驱动 task/detail 共用 AbortController 并行发起，各一次，无 waterfall。 |
| WR-04 | closed | manual status 只由 active bucket effect 承担一次 list reload，没有显式第二 owner。 |
| WR-05 | closed | not-submitted 只保留历史 membership；新 owner submitted 最终态通过完整 Audit。 |
| IN-01 | closed | `EtcOADraftRecoveryPermissionError` 已删除，全仓无运行时残留或兼容分支。 |

## PostgreSQL scoped CAS 与重放复核

- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py:1084-1101` 在同一 transaction 中执行 `SELECT ... FOR UPDATE`、比较 target version、写 scoped snapshot；传入的 `PostgresTransaction` 没有另开连接，row lock 持续覆盖写入。
- prepare 比较写前 version；complete/fail/unknown 比较 `prepared_version`；recover 比较请求 expected version。CAS false 后 service reload durable snapshot 并返回明确 version conflict。
- scoped snapshot 只包含当前 business/submission batch，并按阶段包含该 attempt 的 import batches 或 invoices；不会迭代、覆盖其它 ETC business batch。
- business batch durable 成功但 linked task metadata 失败时，相同 idempotency key 或完全一致的 recovery evidence 只补 task metadata，不再调用 OA，不创建第二个 submission/draft。
- pending replay 仍经过 HTTP mutation permission；recover 仍额外要求 admin scope。task metadata 已绑定其它 draft 时 fail closed。
- 本地 state store 的 RLock/read-check-merge-write 满足仓库明确声明的单进程 tooling/test 合同；生产运行时仍只允许 PostgreSQL state store。

## Audit、前端性能与隔离复核

- Audit：三 bucket、creating attempt 完整/超时、pending draft/submission/task metadata、submitted/current owner、not-submitted 历史 membership 均有明确 owner；无关 formal timestamp 不会刷新业务超时钟。
- 前端：list 仍为单 summary 请求；selection 后 business detail 与精确 task 并行，各一次；AbortController 在 selection/reload 变化时终止旧请求；manual status 写后只 reload 新 bucket 一次。
- 隔离：页面未调用 full reconciliation task list；list/detail 不 hydrate full ETC state、不探测对象存储；OA HTTP 仍在 business lock 外，持久化只通过 ETC state-store owner I/O。
- 旧链：legacy `/api/etc/batches*`、invoice-id revoke fallback、OA auto refresh、前端双 selection owner、重复 detail effect 和无调用 recovery exception 均未回归。
- 跨页面：本轮没有修改共享 read model、worker registry、queue scope、canonical relation API 或其它页面 DTO；ETC 只通过既有明确 downstream refresh/link 端口产生合法影响。

## 测试证明与本轮验证

已读取并逐项核对 `12-REVIEW-FIX.md` 记录的证明：

- ETC 页面组件测试：71 passed。
- ETC Page Audit：14 passed。
- reconciliation service：95 passed，1 skipped。
- OA backend 定向回归：11 passed，123 deselected。
- iteration 1 backend/Audit/scoped repository：145 passed，4 skipped。
- lint、Ruff、docs、commit-range `git diff --check`：通过。

本轮最终只读复审没有重复运行上述测试；重新执行了 Phase diff 的 `git diff --check`，无 whitespace 错误。完整 PostgreSQL repository suite 中记录的既有 Workbench assertion 不在 ETC 变更调用链内，本阶段未修改或隐藏该失败。

## Residual external gates

以下事项无法由本地 code review 伪造，但不改变当前 `clean` 判定：

1. 真实 PostgreSQL 两连接/多进程 row-lock 等待、CAS loser 与事务回滚验证。
2. 真实 OA 草稿创建、结果未知恢复、附件上传和对象存储读取。
3. 统一部署后的生产 Page Audit，以及创建草稿、人工 submitted/not-submitted 后再次 Audit。
4. 生产冷/热 list、并行 detail/task、OA command 和写后可见延迟；三页面混合负载隔离验证。

## 审查范围

从基线 `04db660a57ee6dcb09bbd69200c4ce57ee3d9f2f` 到当前 HEAD 的 Phase 12 source/test diff 共 24 files：

- Backend route/DI/service/store/repository/Audit：10。
- Backend tests/architecture guard：5。
- Frontend page/API/types/styles：4。
- Frontend unit mocks/tests：3。
- Playwright spec/mock：2。

ETC `boundary-io.md`、`state-machine.md`、`tests.md`、`implementation-notes.md` 与 `12-REVIEW-FIX.md` 作为合同/验证上下文读取，不计入 `files_reviewed`。
