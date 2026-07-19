# 银行明细生产验证

**日期：** 2026-07-20  
**页面状态：** `PRODUCTION_VERIFIED`  
**最终九页系统门：** 待全部页面完成后统一执行

## 精确发布

- Git SHA：`123e2362d296efb6d23a0a2ca2f6fb8e7cfeebe0`
- Release：`main-123e2362-20260720004738`
- 分支：`main`
- release metadata：clean，API、dispatcher 与 22 个 registered workers 均指向该 release；migration `0001`–`0110` 均已存在，无新增 migration。
- 本轮运行时代码变化只有删除无 production caller 的 disconnected UoW 文件；没有 API、业务规则、read model、worker、queue、cache、migration、前端或其他页面行为变化。

## 页面读性能

部署后使用真实 Admin-Token、2 次 warmup、20 次/探针，共 100 个生产样本：

| 探针 | p95 | 结果 |
| --- | ---: | --- |
| `/fin-ops/bank-details` 页面壳 | 110.606ms | pass |
| accounts | 148.195ms | 20/20 fresh |
| transactions | 295.326ms | 20/20 fresh、20/20 cache hit |
| auto-tag rules | 222.558ms | pass |
| bank-details Page Audit | 405.607ms | pass |

- 所有页面/API p95 均小于 1000ms；100 个样本没有失败。
- 同一生产 UI 在变更前的 warm data-visible 浏览器基线为 792–964ms、平均 903.8ms；本轮没有前端或页面读路径实现 diff。部署后页面壳和全部首屏数据 API 的独立 p95 继续显著低于 1 秒。

## 页面操作后的可见性与 Audit

使用幂等的 `POST /api/bank-details/auto-tag-rules/reapply` 做直接页面链路验证，不修改规则内容或业务分类：

- POST：202，实际 HTTP 430.115ms；
- response 完成到 transactions 首次 fresh：941.687ms；
- 用户操作开始到 transactions fresh：约 1.431s；
- 用户操作开始到 Page Audit 完整返回：1.786s；
- 41 个目标 scope 全部收敛；最终 dirty scope 0、outbox backlog 0。

该直接写后样本证明 enqueue/response 后到 fresh 小于 1 秒；单次样本不冒充统计学 p95/p99。页面读 p95 已由上表 20 次独立样本证明。

操作后 bank-details Page Audit：

- `overall_status=pass`
- integrity `pass`、freshness `fresh`、queue `drained`
- canonical 989 = read model 989
- 42 scopes、219 active relations、271 linked groups
- dirty 0、outbox 0、issues/errors/warnings/blocking 0

## 隔离验证

操作后定向 Page Audit：

- reconciliation-workbench：pass / fresh / drained
- bank-flow-rule-batches：pass / fresh / drained
- turnover-ledger：pass / fresh / drained
- settings（不相关页面）：pass / fresh / drained

没有发现银行明细变更导致其他页面 API、read model、worker 或 UI 合同变化。

## 两项共享系统证据的精确归类

### System Audit

App Health system audit 当前有 3 个 `system_page_integrity_failed`：

- `tax-offset`
- `input-invoice-usage`
- `output-invoice-collections`

它们均为本主控后续尚未处理的页面。银行明细自身和直接下游均通过；本轮代码 diff 也不包含这三个模块。

标准 test-owned fan-out scenario 的 dry-run 通过，但 apply 在任何 mutation 前被 System Audit preflight 拒绝：`system_audit_page_count_or_contract_failed`、`recovery_required=false`。因此没有创建关系、没有撤回关系、没有半写状态，也没有绕过安全门。该跨页 fan-out 在上述三个页面完成后，放到九页最终统一验证执行；否则第一个页面会被后续页面的已知问题永久阻塞，和“逐页串行修复”相冲突。

### 共享 `/health/ready`

三次探针均返回 HTTP 200、`health_status=ready`、runtime blocker 0、release consistent，但共享 endpoint 为 2.295–4.566s（第三次 2.817s），未达到 1 秒全局门槛。该 endpoint 不是 bank-details 页面壳或首屏 API 热路径，本轮也未修改 App Health；不在银行明细轮次扩张为共享模块优化。它保留为最终九页系统门风险。

## 闭环判定

银行明细达到 `PRODUCTION_VERIFIED`：本页代码、直接页面性能、直接操作后 freshness、Page Audit、queue drain 和定向隔离全部通过。全系统 fan-out 与共享 readiness 不是本页缺陷，不能在本页越界修改；它们作为九页全部完成后的统一系统验收门保留，届时必须通过才能结束主控 Goal。
