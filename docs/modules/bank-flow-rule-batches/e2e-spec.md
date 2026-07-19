# 流水规则批量处理 E2E 规格

状态：covered-transition。关键 P0 场景已映射到 `web/e2e/bank-flow-rule-batches-flow.spec.ts`；真实 pending-invoice/invoice attach 跨页补票入口和独立 read model 拆分仍是后续风险。

## BRB-E2E-001 标签规则抽屉跟随银行明细标签

前置：

- 银行明细存在多个 active 标签，覆盖收入/支出、主标签、子标签。
- 本模块规则尚未保存部分标签。

步骤：

1. 打开 `/bank-flow-rule-batches`。
2. 打开标签规则抽屉。
3. 查看 grid 左侧 `收支类型 / 流水主标签 / 流水子标签`。
4. 尝试编辑左侧标签列。
5. 勾选/取消右侧 `OA`、`发票`。
6. 保存后刷新页面。

验收：

- 左侧标签与银行明细 active 标签一致，且不可编辑、不可新增、不可删除。
- 右侧只存在 `OA`、`发票` checkbox。
- 未配置标签默认 OA 和发票都勾选。
- 保存后规则持久化，刷新仍保持勾选。
- API 不递增银行标签版本。

## BRB-E2E-002 提交形成 active relation 后进入已配对

前置：

- 某银行标签存在明确 OA/发票审计提示。
- 存在 4 条同月、同账户、同标签且未被 active relation 占用的银行流水。

步骤：

1. 在流水规则批量处理页筛选该标签。
2. 选择 4 条银行流水并提交。
3. 等待 operation barrier 完成。
4. 打开关联台。

验收：

- 提交成功创建 active `relation_mode=bank_flow_rule_batch`。
- 关联台已配对区出现该 relation。
- 因银行流水数 `>3`，默认以折叠摘要展示。
- 展开后可看到 4 条原始银行流水。

## BRB-E2E-003 无 active relation 的事实保持未配对，确认后进入已配对

前置：

- 存在 4 条同月、同账户、同标签银行流水。
- 存在可匹配发票。

步骤：

1. 在关联台查看尚无 active relation 的银行/发票事实。
2. 确认它们分别位于 unpaired singleton。
3. 选择对应事实并通过确认关联预览提交。
4. 等待 operation barrier。

验收：

- 没有 active relation 时事实保持 unpaired。
- 确认形成 active relation 后，同一个 case 的完整成员进入 paired。
- 原始银行 rows 未丢失，折叠摘要和展开详情一致。

## BRB-E2E-004 规则保存不追溯改写 existing relation

前置：

- 已存在 bank-flow、turnover 或 manual active relation。
- 当前规则与 relation 提交时的审计提示不同。

步骤：

1. 保存新的 OA/发票规则。
2. 读取 existing relation 和关联台分区。

验收：

- existing relation metadata、relation mode 和 history 不变。
- active relation 继续 paired，不因当前规则变化回到 unpaired。
- 只产生 bank-flow read model refresh，不产生 Workbench/turnover relation 写入。

## BRB-E2E-008 已提交批次批量重置回未提交候选

前置：

- 流水规则批量处理页存在 `submitted` 批次。
- 对应 active relation 由 `relation_mode=bank_flow_rule_batch` 创建。

步骤：

1. 在页面提交一组银行流水。
2. 点击“重置全部已提交”。
3. 等待 operation barrier。
4. 查看未提交列表。

验收：

- API 调用 `POST /api/bank-flow-rule-batches/reset-submitted`。
- 后端通过 withdraw + relation command 取消 active relation，不手工 SQL 修改 relation 表。
- 页面提示重置成功，并切回未提交。
- 银行 rows 重新按当前规则进入未提交候选；不会自动重新提交。

## BRB-E2E-006 权限、陈旧和失败状态 fail closed

前置：

- 准备只读用户、规则保存权限用户、批次提交/撤回权限用户。
- 准备 stale/missing read model 场景。

步骤：

1. 只读用户打开页面和抽屉。
2. 尝试保存规则、提交批次、撤回批次、reset submitted。
3. 在 read model stale/missing 时查看列表和提交按钮。

验收：

- 无权限时按钮隐藏或禁用，API 返回业务错误。
- 非 fresh 时页面显示刷新/陈旧状态，不把空结果当真实无候选。
- 写操作返回明确错误 message、read model status 和 scope keys。

## BRB-E2E-007 银行标签变更后规则 grid 同步

前置：

- 已保存本模块规则。
- 银行明细新增一个 active 标签、归档一个旧标签。

步骤：

1. 打开流水规则批量处理标签抽屉。
2. 查看 active 标签列表和规则。

验收：

- 新增标签出现在左侧，默认 OA/发票都勾选。
- 归档标签不再作为新规则可编辑项。
- 历史 submitted 批次仍显示提交时标签 snapshot。
