# 第二轮审阅：简洁性与性能

## 候选方案比较

### A. 把逐 relation 写改成 bulk update

拒绝。它只是降低错误旧链路的常数，仍会污染 Workbench/turnover I/O、重写历史 metadata，并继续产生无意义下游刷新。

### B. 增加缓存、专用 projection 或新 worker

拒绝。生产 GET p95 仅 183.321ms，读取不是问题；新增基础设施会增加一致性和运维成本。

### C. settings 单写 + bank-flow 单刷新

采用。它与当前事实源一致，写路径为 O(1)，复用既有 durable queue、既有 producer 和既有 worker，不增加新架构组件。

## 是否过度设计

否。最终运行时只有三个动作：校验/保存、审计、单次入队。额外的一次性迁移不是新运行时层，而是删除 legacy `selected_tag_codes` 前避免数据丢失的必要收口。

## 第二轮补充项

- 必须实现 semantic no-op；否则相同保存仍会制造版本和刷新噪声。
- 不让 AppSettingsService 直接入队；settings writer 只拥有 settings/audit，application service 拥有 refresh output。
- 不再调用 `bank_flow_rule_batch_changed` broad lifecycle；规则配置只影响 bank-flow read model。
- 不修改前端，因为现有 UI 已使用独立 `rules` 合同且 GET 性能达标。
