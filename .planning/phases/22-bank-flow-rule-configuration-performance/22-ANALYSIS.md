# 第 2 项：流水规则配置链路全量分析

## 范围

本项只处理 `/bank-flow-rule-batches` 页面中的“标签规则”配置子链路：

- `GET /api/bank-flow-rule-batches/tag-rules`
- `PUT /api/bank-flow-rule-batches/tag-rules`
- 规则抽屉的读取、保存、审计与刷新

同一路由中的批次列表、详情、提交、撤回、重置属于第 3 项“批量处理”，本项禁止修改其业务行为。

## 基线事实

生产只读基线（20 次、另含 2 次 warmup）：

| 链路 | p50 | p95 | 结论 |
| --- | ---: | ---: | --- |
| 页面壳 | 95.777ms | 110.862ms | 已达标 |
| 标签规则 GET | 125.012ms | 183.321ms | 已达标 |
| Page Audit | 246.142ms | 331.181ms | 已达标 |

当前 Page Audit 为 `pass / fresh / drained`。因此读取路径不存在需要新缓存、新 read model 或前端重写的问题；优化对象是规则保存写路径。

## 当前 I/O 链路

### 读取

`BankFlowRuleBatchApiRoutes.tag_rules()` → `BankFlowRuleBatchApplicationService.tag_selection_payload()` → `AppSettingsService.get_bank_flow_rule_batch_tag_rules_payload()` → `app_settings.bank_flow_rule_batch_tag_rules`。

读取是单一事实源、无 relation 扫描，生产数据证明其性能已经足够高。

### 保存

当前 PUT 在写入 settings 后执行以下副作用：

1. `_sync_bank_flow_rule_relation_requirements(...)`：读取全部 active relations；对命中的 bank-flow、turnover 和普通手工 relation 逐条调用 `update_relation_metadata_for_case_id(...)`。
2. `_sync_turnover_rule_relation_requirements(...)`：再次读取全部 active relations；再次逐条处理 turnover relation。
3. 每条 relation 更新独立写 history、持久化 relation，并产生下游 dirty/outbox fan-out。
4. 同步方法内部再次调用 `after_mutation(...)` 与显式 `enqueue_background_refresh(...)`。
5. 顶层 `update_tag_selection(...)` 又调用一次 `after_mutation(...)` 和一次显式 refresh。
6. `after_mutation(...)` 触发 `bank_flow_rule_batch_changed`，该 lifecycle 已经 fan out 到 bank-flow、Workbench、relation 和 search；因此显式 bank-flow enqueue 与 lifecycle 重复。

生产当前有 219 个 active relations。该写路径复杂度不是常数，而是两次全表扫描加最多逐 relation 的数据库/队列写入，属于确定性的 O(R) 写放大。

## 真实根因

### 1. 旧分区规则已经失效，relation 回写仍在运行

当前权威 API 合同与 `WorkbenchRelationGroupingService` 已规定：

- active 正式关系的完整成员一律进入 paired；
- 没有 active relation 的事实进入 unpaired singleton；
- `requires_oa` / `requires_invoice` 只作为规则校验和审计提示，不再决定关联台分区。

但 2026-06-30 的旧实现仍按“requirement 决定 paired/open”假设，在每次规则保存后改写所有既有 relation metadata。该旧假设已被 2026-07-14 的 formal-relations 合同替代。

全仓扫描未发现任何当前生产读取逻辑再以 relation metadata 中的 `requires_oa`、`requires_invoice`、`paired_requirement_*` 或 `flow_rule_version` 决定分区；剩余引用是写入端、历史测试与展示/审计数据。

### 2. turnover relation 可能在同一次保存中被写两次

第一段同步会把非 bank-flow relation 写为 `bank_transaction_paired_policy`；第二段同步又把 turnover relation 写为 `no_oa_bank_batch_tag_selection` / `turnover_manual_closure`。两段使用不同 metadata source，同一 relation 可在一次保存中发生两次串行持久化和下游 fan-out。

### 3. 相同规则也递增版本

当前 settings writer 即使规则语义完全相同也会递增 version、写 settings、写 audit，并使 relation 的旧 `flow_rule_version` / `paired_requirement_version` 全部被判过期。一次无变化保存也会触发完整写放大。

### 4. 刷新 owner 重复

relation command、同步方法内 lifecycle、同步方法内显式 enqueue、顶层 lifecycle、顶层显式 enqueue 都可能写入刷新请求。虽然 durable queue 有 dedupe，但请求前的 relation/history 写入无法被 dedupe，且重复 owner 使边界不清晰。

### 5. bank-flow settings 内部仍复用 no-OA 旧 shape

`bank_flow_rule_batch_tag_rules` 当前通过 `_normalize_no_oa_bank_batch_tag_selection(...)` 规范化，内部 shape 会生成 `selected_tag_codes`；自动标签归档时也复用 no-OA detach helper。public payload 虽隐藏该字段，但内部 I/O 与持久化清理仍受到旧 no-OA 结构污染。

迁移 `0083` 曾从 no-OA settings 一次性复制初值。为了安全删除 runtime 兼容逻辑，必须先用一次性迁移把旧 `selected_tag_codes` 合并为 `requirements_by_tag_code` 后删除该字段，不能直接忽略旧数据。

## 设计结论

规则保存的生产级最简边界应为：

1. 校验 `expected_version`、标签 code、重复项和权限。
2. 规范化 bank-flow 专属 rules；不接收、不产生 `selected_tag_codes`。
3. 规则语义未变化：返回当前 payload，不写 settings、不写 audit、不入队。
4. 规则语义变化：单次写 settings、单次写 audit。
5. 仅通过 `BankFlowRuleBatchReadModelRefreshProducer` 写入一个 durable `bank_flow_rule_batch/all` refresh 请求。
6. 不读取或改写任何 active relation；既有 relation 保持创建时的历史 metadata，新建批次使用新规则生成其审计提示 metadata。
7. GET 路径与前端 UI 保持不变。

## 明确不采用

- 不新增 Redis cache、专用表、专用 worker、消息总线或第二套 read model。
- 不做 relation 批量回写优化；该回写本身已无当前业务合同，正确做法是删除。
- 不修改 Workbench、往来款、银行明细或其他页面的 read model。
- 不在本项修改批次提交、撤回、重置链路。

## 性能门槛

- 页面壳、GET tag-rules、Page Audit：生产 p95 ≤ 1000ms，且不得劣化超过基线的 30%。
- no-op PUT：生产响应 ≤ 500ms，零 settings/audit/relation/queue 写入。
- 实际变更 PUT：真实 PostgreSQL 环境响应 p95 ≤ 500ms；只允许 1 次 settings 写、1 次 audit、1 个 `bank_flow_rule_batch/all` durable refresh。
- 写后 GET 新规则可见 ≤ 1000ms；read model 在 worker 完成前必须诚实显示 refreshing/stale，完成后 fresh。
- Page Audit 必须 `pass / fresh / drained`；其他页面不得新增 dirty/outbox 或 Audit 回归。
