# 第 2 项实施结果：流水规则配置链路

## 已落地的运行时收敛

- `AppSettingsService` 将 bank-flow 规则持久化规范为 `version + requirements_by_tag_code`；legacy `selected_tag_codes` 只继续服务 no-OA 模块。
- 语义相同的规则保存成为真正 no-op：不增加 version、不写 settings、不写 audit、不入队。
- 实际规则变化只写一次 settings/audit，并只入队一次 `bank_flow_rule_batch/all` durable refresh。
- 规则保存不再读取或改写既有 Workbench relation，不再触发 turnover I/O，也不再调用 broad lifecycle。
- 新 relation 仍在批次创建时记录当时规则元数据，作为审计快照；既有 formal relation 的 paired/unpaired 事实不被规则保存追溯修改。

## 旧链删除

- 删除 `_sync_bank_flow_rule_relation_requirements`。
- 删除 `_sync_turnover_rule_relation_requirements`。
- 删除仅由上述同步路径使用的 relation 扫描、推导、比较与逐条写回 helper。
- 删除共享 base 中无生产调用方的旧 tag-selection 入口与相关依赖。
- migration `0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql` 清理 bank-flow 持久化 selected 字段；不修改 no-OA 数据。
- 更新旧测试和文档，移除“规则保存会追溯改写 relation”的过期合同。

## 变更边界

- 输入：`GET/PUT /api/bank-flow-rule-batches/tag-rules` 既有 DTO、权限与 optimistic version。
- 输出：既有 response shape；actual change 额外产生且只产生 `bank_flow_rule_batch/all` refresh。
- 不变：批次列表、详情、提交、撤回、重置；no-OA；银行明细；关联台 formal relation；流水台账。
- 未新增 cache、表、worker、兼容 API、fallback 或通用抽象。

## 数据迁移

- 迁移只触及 `app.app_settings.settings_key='app_settings'` 中的 `bank_flow_rule_batch_tag_rules`。
- legacy selected code 若尚无 requirement，则按历史语义补为 `requires_oa=false`、`requires_invoice=false`，随后删除 selected 字段。
- 迁移幂等，并把执行证据写入 raw payload；no-OA key 保持原样。
