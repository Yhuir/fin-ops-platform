# 第三轮审阅：生产闭环、隔离与遗漏

## 一致性

- settings 写入仍由现有 state store/PostgreSQL 边界完成。
- actual change 后 read model source version 变化，并通过既有 durable queue 刷新；页面在完成前必须报告 stale/refreshing，不伪装 fresh。
- no-op 不改变 version，因此 read model source version不变，无需刷新。
- optimistic version conflict、未知/停用/重复 tag、legacy input 拒绝保持原合同。

## 隔离

- 删除 active relation 全量读取与逐条更新。
- 删除 Workbench、workbench_relation、turnover 和 search 的规则保存 fan-out。
- 保留 bank-details 标签字典作为输入；标签字典真实变化仍可按其 owner 的现有合同影响共享 canonical 数据。
- 不改变 no-OA legacy API/service、turnover settings 或其他页面 read model。

## 旧代码闭环

必须完成以下删除/替换：

1. `BankBatchApplicationService` 中无生产入口的 generic tag selection writer。
2. 两个 bank-flow/turnover relation sync 方法。
3. 仅供这些 sync 使用的 requirement 推导、比较与 relation row helper。
4. bank-flow runtime 对 `_normalize_no_oa_bank_batch_tag_selection` 和 no-OA detach helper 的复用。
5. formal-relations 之后仍断言 requirement 决定 paired/open 或保存后回写关系的旧测试与文档。
6. PostgreSQL `bank_flow_rule_batch_tag_rules.selected_tag_codes` 残留，由一次性迁移转入 requirements 后删除。

no-OA 独立页面的 legacy `selected_tag_codes` 合同属于另一个模块，保留且用回归测试保护。

## 回滚

- 代码回滚不会丢业务数据；新写入的 canonical rules shape 仍包含旧代码可读取的 `requirements_by_tag_code`。
- 迁移只删除 bank-flow settings 内的冗余 legacy key，并在删除前合并其语义；不改 no-OA settings。
- 若 refresh worker 异常，durable dirty/outbox 状态保留，页面显示 refreshing/stale；修复 worker 后可重放，无需 relation 回滚。

## 第三轮遗漏检查

已补齐：权限、审计、乐观锁、无变化保存、持久化迁移、worker 异常、回滚、Page Audit、其他页面隔离、旧消费者扫描、文档合同和七类测试责任。

不需要新增：缓存、表、worker、fallback、兼容 API、UI 状态或跨页面补偿任务。

## 最终审阅结论

计划合理、范围最小且闭环。它通过删除错误副作用获得高性能，而不是增加复杂基础设施；满足模块化边界、清晰 I/O、隔离、生产一致性和旧代码清理要求，可以进入实施。
