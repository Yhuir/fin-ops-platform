# 关联台二态配对口径实施计划

## 目标

关联台和下游业务只暴露两种关系口径：

- `paired`：存在正式 active 配对关系。
- `unpaired`：不存在正式 active 配对关系。

系统自动配对命中确定性闭合结果时，必须走正式关系写入口落库。候选/建议只作为内部计算过程，不进入业务筛选口径。

## 模块边界

### workbench-relations

输入：
- `confirm_relation(...)`
- `withdraw_relation(...)`

输出：
- active relation
- withdrawn history
- read model refresh scope

约束：
- 人工确认和系统自动配对共用同一写入口。
- 行占用、幂等、审计、版本冲突继续由关系命令服务负责。

### reconciliation-matching

输入：
- OA、流水、发票行
- active relations
- 已撤回/已抑制决策

输出：
- 满足确定性条件时调用 `confirm_relation(...)`
- 不满足时仅保留内部 decision，不输出业务关系状态

约束：
- 只自动落库 `paired + paired display + 三栏完整 + 金额 matched` 的决策。
- 用户撤回后，同一组 row id 不得再次自动落库。

### reconciliation-workbench / downstream

输入：
- `workbench_relation` read model
- 关系命令 API

输出：
- 已配对：正式 active relation
- 未配对：没有正式 active relation

约束：
- 不暴露 `candidate` 业务筛选。
- 自动建议未落库前不算已配对。

## 实施步骤

1. 自动匹配引擎新增 paired decision 直接正式落库路径。
2. 正式关系撤回时抑制同组 reconciliation decision，防止下一轮自动重配。
3. `workbench_relation` 投影不再把非正式 open/proposed decision 输出为 candidate 业务关系。
4. 前端关系预览和筛选文案移除“候选”用户概念。
5. 更新关系/匹配/下游筛选测试。

## 验收

- 自动三栏确定性配对会生成 active formal relation。
- 已有 active relation 的行不会被重复自动配对。
- 撤回自动配对后，同一组行不会自动重配。
- downstream 只看到 linked/unlinked 或 paired/unpaired 派生口径，不再把 candidate 暴露为业务状态。
- 关联台不再出现“拆分候选”作为用户状态文案。
