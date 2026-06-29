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

## BRB-E2E-002 无需 OA/发票的银行流水直接进入已配对

前置：

- 某银行标签规则保存为 `requires_oa=false`、`requires_invoice=false`。
- 存在 4 条同月、同账户、同标签且未被 active relation 占用的银行流水。

步骤：

1. 在流水规则批量处理页筛选该标签。
2. 选择 4 条银行流水并提交。
3. 等待 operation barrier 完成。
4. 打开关联台。

验收：

- 提交成功创建 `relation_mode=bank_flow_rule_batch`。
- 关联台已配对区出现该 relation。
- 因银行流水数 `>3`，默认以折叠摘要展示。
- 展开后可看到 4 条原始银行流水。

## BRB-E2E-003 需要发票的银行批次先留在 open，补票后进入已配对

前置：

- 某银行标签规则为 `requires_oa=false`、`requires_invoice=true`。
- 存在 4 条同月、同账户、同标签银行流水。
- 存在可匹配发票。

步骤：

1. 选择 4 条银行流水并提交。
2. 打开关联台。
3. 确认该 group 位于 open 区且折叠。
4. 在关联台选中该银行批次和补票候选发票。
5. 通过确认关联预览提交。
6. 等待 operation barrier。

验收：

- 缺发票时 active relation 不进入已配对。
- 补齐并确认发票后，同一个 case 进入已配对。
- 原始银行 rows 未丢失，折叠摘要和展开详情一致。

## BRB-E2E-004 需要 OA 和发票时缺任一项均不得 paired

前置：

- 标签规则为 `requires_oa=true`、`requires_invoice=true`。
- 已提交银行批次。

步骤：

1. 只补齐 OA，不补发票。
2. 查看关联台。
3. 再补齐发票。

验收：

- 只补齐 OA 时仍在 open。
- OA 和发票都满足后才进入 paired。
- relation metadata 缺失或不完整时 fail closed，不默认 paired。

## BRB-E2E-005 历史 no-OA submitted rebaseline

前置：

- 存在多个 legacy `relation_mode=no_oa_bank_batch` submitted 批次。
- 对应银行 rows 当前未被其它非 no-OA active relation 占用。

步骤：

1. 运行 rebaseline dry-run。
2. 查看 manifest 中的批次数、银行 rows、月份、金额、风险。
3. 执行 apply。
4. 等待 operation barrier。
5. 打开流水规则批量处理页和关联台。

验收：

- dry-run 不改变事实。
- apply 通过 relation command service 撤回旧 relation。
- 旧 no-OA 批次标记 rebaseline withdrawn。
- 银行 rows 回到候选或按新规则进入 open/paired 候选链路。
- 重复 apply 幂等。

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

- 准备只读用户、规则保存权限用户、rebaseline 管理权限用户。
- 准备 stale/missing read model 场景。

步骤：

1. 只读用户打开页面和抽屉。
2. 尝试保存规则、提交批次、运行 rebaseline。
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
