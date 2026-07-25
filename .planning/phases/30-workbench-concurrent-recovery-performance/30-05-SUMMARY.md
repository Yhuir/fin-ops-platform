---
phase: 30-workbench-concurrent-recovery-performance
plan: "05"
status: complete
subsystem: workbench-relation-production-closure
tags: [workbench, confirm, withdraw, oa-pending, cost-statistics, production, zero-fan-out]

requires:
  - phase: 30-02
    provides: bounded relation preview and formal confirm/withdraw transaction boundary
  - phase: 30-03
    provides: synchronous pending feedback, duplicate guard and safe error mapping
  - phase: 30-04
    provides: reversible production runner and sanctioned test-owned fixture control
provides:
  - membership-sensitive OA active-relation source proof
  - active-only OA relation projection through the structured repository boundary
  - production proof of confirm and withdraw across all affected and isolation consumers
  - Cost relation-impact validation for both active and System Audit all scopes
affects: [reconciliation-workbench, oa-pending-payments, cost-statistics, system-audit, deploy-control]

tech-stack:
  added: []
  patterns:
    - canonical active relation set is shared by OA freshness proof and projection
    - ordinary writes perform no read-model fan-out; page access owns exact-scope convergence
    - correctness and deferred 3-second performance status are reported separately

key-files:
  created:
    - .planning/phases/30-workbench-concurrent-recovery-performance/30-05-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_source_snapshot.py
    - backend/src/fin_ops_platform/services/oa_pending_payment_sql_projection.py
    - backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py
    - tests/test_oa_pending_payment_source_snapshot_repository.py
    - tests/test_oa_pending_payment_read_model_refresh.py
    - tests/test_oa_pending_payment_postgres_integration.py
    - tests/test_write_operation_e2e_smoke.py
    - docs/modules/oa-pending-payments/boundary-io.md
    - docs/modules/oa-pending-payments/tests.md
    - docs/modules/oa-pending-payments/implementation-notes.md
    - docs/modules/deploy/boundary-io.md
    - docs/modules/deploy/tests.md
    - docs/modules/deploy/implementation-notes.md

key-decisions:
  - "OA projection no longer infers activity from historical raw relation payload; it consumes the existing structured active-only repository reader."
  - "OA source proof is count plus stable membership digest, so withdrawing any relation invalidates the scope even when a newer active relation remains in the month."
  - "Cost production probes require relation-semantic project/bank/expense-type views; active is mandatory and all is additionally allowed for System Audit."
  - "The relaxed Phase 30 correctness gate accepts bounded convergence above 3 seconds but records it as performance follow-up rather than hiding it."

requirements-completed: [AUDIT-04, RELCL-01, RELCL-02, RELCL-03, RELCL-05, RMF-02, RMF-03, RMF-08]
requirements-deferred: [RMF-09]

completed: 2026-07-26
production-validation-status: passed
active-release: main-77c580f0-20260726052834
---

# Phase 30 Plan 05：关联台确认/撤回生产闭环

**确认关联与撤回关联已在正式链路完成生产级闭环：写入成功、九个消费者按访问收敛、数据与配对关系正确、写后零 fan-out、System Audit 16/16、队列清空、测试 fixture 恢复未关联。旧的 3 秒端到端性能目标没有全部达到，按本次已放宽的验收口径列为独立性能后续。**

## 根因与修复

1. OA 待付款投影曾从历史 raw payload 的 `_active_relations` 推断关系是否 active。撤回后，结构化 SQL 状态已经 inactive，但旧 payload 仍可能携带 active 字段，导致 OA 页面继续显示 bank/invoice relationCount。
2. OA freshness proof 只靠不足以表达 relation membership 的旧版本信号。撤回一条较旧关系时，同月若存在更新时间更晚的 active relation，scope 可能错误地保持 fresh。
3. 第一轮生产验证暴露的 Cost Audit 失败不是 Cost runtime 缺陷，而是 runner 把每个 Cost consumer 都强制为 `project_scope=active`；System Audit 合法使用 `all` scope。

最终修复只落在三个既有边界：

- OA source snapshot 使用一个 set-based SQL 生成 active relation count 与稳定 digest。
- OA projector 复用既有 `load_active_workbench_pair_relations_for_row_ids()`，删除 raw payload `_active_relations` 旧过滤 owner。
- 生产 runner 要求 relation-semantic Cost probe；至少一个 `active`，同时允许 System Audit 所需的 `all`。

没有新增表、migration、cache、queue、worker、协调器、第二套 runner 或兼容 fallback。

## 提交与生产版本

| 提交 | 内容 |
|---|---|
| `13311f867` | OA 根因 RED 证明 |
| `a6c3863fe` | OA active-only projection 与 membership proof 修复 |
| `058e55213` | 真实 PostgreSQL 回归 |
| `68d48ffc7` | Cost relation-impact runner RED 门禁 |
| `983d1595a` | Cost semantic probe fail-closed |
| `c47fd5925` | System Audit fixture 对齐 |
| `77c580f01` | 同时验证 Cost active/all scope |

- Candidate C：`main-c47fd592-20260726050231`
- 最终 Candidate D：`main-77c580f0-20260726052834`
- `77c580f01` 已推送到 `origin/main`，Candidate D 已通过官方 `scripts/deploy-oa.sh` 激活。
- API、RabbitMQ dispatcher、24 个要求的 worker、backend readiness、deploy-control、前端 hash 与公开 session route 均通过部署检查。

## 最终生产验证

使用同一条明确 test-owned、可逆的 `bank_oa_invoice` fixture，依次执行：

`inactive preimage → confirm → 9 consumers → withdraw → 9 consumers → inverse proof → System Audit`

### 正确性和隔离

- confirm 与 withdraw checkpoint 均 `pass`，无 ambiguous commit。
- Workbench、银行明细、待找发票、进项发票使用、OA 待付款、成本统计 active、成本统计 all 均 fresh，且配对/撤回后的业务语义正确。
- 销项收款与税金抵扣 isolation consumer 保持不受影响。
- confirm 后 OA relationCount 正确变为 active；withdraw 后 OA bank/invoice relationCount 回到 0。
- 每个 checkpoint 的 write-after refresh event sample 都为 0；十个禁止 fan-out 合同全部通过，无 unexpected event contract。
- System Audit 三个 checkpoint 均通过；最终状态为 integrity pass、freshness fresh、queue drained、16/16 页面通过、0 issue、数据库合同通过。
- 最终 fixture 为 inactive：withdraw preview 返回 relation not found，Workbench 三个成员均回到 unpaired，各下游页面不再含该 relation。
- Candidate C/D 的两个远端临时 scenario 已精确删除，并验证不存在。

System Audit 的 `external=unknown` / `end_to_end_source_truth=unproven` 是历史外部银行/OA/发票/ETC 来源证明状态，不表示本次正式 API、关系事实或 read model 链路失败。本次链路本身已完成生产证明。

### 性能实测

| 阶段 | confirm | withdraw |
|---|---:|---:|
| read version | 256 ms | 580 ms |
| preview（最后一次） | 282 ms | 2,588 ms |
| 正式 mutation | 3,859 ms | 2,714 ms |
| preview 10 次 p50 | 301 ms | 3,150 ms |
| preview 10 次 p95/max | 840 ms | 3,689 ms |

页面从访问到 fresh/正确可见：

| 消费者 | confirm | withdraw |
|---|---:|---:|
| Workbench | 12.72 s | 9.23 s |
| 银行明细 | 11.72 s | 8.37 s |
| 待找发票 | 11.50 s | 8.82 s |
| 进项发票使用 | 13.67 s | 11.22 s |
| OA 待付款 | 6.25 s | 4.58 s |
| 成本统计 active | 13.78 s | 10.52 s |
| 成本统计 all | 14.02 s | 10.60 s |
| 销项收款 isolation | 0.94 s | 1.29 s |
| 税金抵扣 isolation | 0.91 s | 1.20 s |

结论：

- 本次放宽后的 correctness gate 通过：所有访问页面都在 30 秒有界窗口内 fresh、完整、正确地收敛。
- 正式写 API 的 confirm 3.86 秒、withdraw 2.71 秒，按钮 pending 状态会立即给出交互反馈并阻止重复提交。
- “非常高性能/全部 3 秒内”不能宣称通过。withdraw preview p95 为 3.69 秒，受影响页面 access-to-fresh 为 4.58–14.02 秒；这是独立性能优化项，不再和本次正确性修复混在一起。

## 验证

- 受影响 backend unit/service/API/read-model/runner/Audit 矩阵：566 通过，9 个真实 PostgreSQL 环境门禁在本地显式跳过；其中 PostgreSQL 关键链路另有真实数据库测试和生产 fixture 覆盖。
- Candidate D runner 定向回归：69 通过。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- Workbench 前端定向 Vitest：123 通过。
- Workbench confirm/withdraw Chromium 关键流：3 通过。
- 前端 production build：通过；只有已记录的既有 generated CSS selector 与 bundle-size warning。
- 最终生产 read-only health、System Audit、fixture inverse、九个消费者、队列/worker 与临时文件清理：全部通过。

按用户要求，没有运行无关的 183 项 Browser 套件、full CI 或 pytest。

## 七类测试覆盖

1. **业务核心单元测试：适用并覆盖。** confirm/withdraw identity、active-only membership、重复/冲突/无效状态和 inverse 语义均有保护。
2. **Service 层测试：适用并覆盖。** OA source proof、projection、持久化状态、幂等和正式 relation UoW 均纳入定向矩阵。
3. **API 合同测试：适用并覆盖。** preview、confirm、withdraw、stale/version/error/requestId 和 mutation result 合同均验证。
4. **Read model/cache/background job：适用并覆盖。** exact-scope stale/fresh、访问触发、去重、队列 drain、worker、System Audit 与 active/all Cost scope 均验证。
5. **前端组件与交互：适用并覆盖。** pending/disabled/spinner、重复点击、stale response、错误恢复、确认和撤回关键浏览器流均通过。
6. **端到端业务流：适用并覆盖。** 生产 confirm→所有消费者→withdraw→所有消费者→inverse/Audit 完整通过。
7. **既有功能回归：适用并覆盖。** 九个消费者、两个 isolation 页面、旧 API shape、正常页面 mapping 与正式 drawer 提交链路均受保护。

## 文档与剩余风险

- OA source/projection 边界、测试责任和实施记录已更新。
- deploy runner 的 Cost active/all 验证合同已更新。
- 无 API response shape、schema、worker 或模块职责变化需要额外迁移文档。
- 没有已知 correctness、数据安全、fan-out、队列或恢复 blocker。
- 剩余风险仅是已量化的尾延迟，以及历史外部控制来源证据仍为 unknown；两者均没有被伪装为本次通过。

## Self-Check：PASSED

- 所有列出的实现、测试和文档提交均存在于 git 历史。
- 最终生产 release 与 exact SHA 一致并处于 ready 状态。
- fixture 已恢复、队列已清空、System Audit 16/16、远端临时文件已删除。

---
*Phase: 30-workbench-concurrent-recovery-performance*  
*Completed: 2026-07-26*
