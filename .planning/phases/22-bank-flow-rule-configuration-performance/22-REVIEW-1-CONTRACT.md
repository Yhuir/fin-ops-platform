# 第一轮审阅：事实源与合同

## 审阅问题

规则变化是否仍必须改写关联台已有 relation，才能保证页面正确？

## 证据

- 当前 `docs/dev/api-contracts.md` 明确说明 requirement 只用于校验/审计提示，不再决定关联台分区。
- 当前 `WorkbenchRelationGroupingService` 只按 active formal relation 集合构造 paired；未读取 requirement metadata。
- 当前测试 `test_single_pane_active_relation_is_still_paired` 证明即使只有 bank rows，active relation 仍为 paired。
- 全仓生产代码扫描未发现 relation metadata requirement 的分区消费者。
- 旧模块文档和旧 API 集成测试仍要求保存规则后改写 relation，它们来自 formal-relations 迁移之前，已经与当前权威合同冲突。

## 审阅结论

删除 relation 回写不会让当前关联台数据变旧：relation 是否 paired 的事实源是 active formal relation，不是当前规则版本。相反，继续回写会篡改既有关系的历史审计快照，并让规则页面跨边界修改 Workbench 与 turnover。

需要同步修正的不是当前 formal relation 合同，而是 bank-flow 模块内过期的 boundary/state/test/implementation 说明与测试断言。

## 第一轮补充项

- 明确区分“当前规则事实”和“既有关系历史 metadata”：规则变化只影响未来候选/新批次，既有 relation 不追溯改写。
- 新增架构 guard，禁止 tag-rules 保存调用 relation list/update 或 broad lifecycle。
- 保留 no-OA legacy 服务的独立合法行为；只删除 bank-flow 新链路能够触达的旧同步代码，不跨范围删除 no-OA 页面。
