# 流水规则批量处理 E2E 规格

状态：covered-partial。页面直读、单次写后 GET、失败恢复、规则、提交、撤回和 reset 已映射并通过；共享 Workbench confirm-preview fixture 的旧 DTO 仍需主控修复后重跑 BRB-E2E-003。真实生产 canonical SQL/HTTP 大数据性能仍由发布 smoke 验证。

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
7. 返回未提交 bucket，比较双 false 标签与需要 OA/发票标签。

验收：

- 左侧标签与银行明细 active 标签一致，且不可编辑、不可新增、不可删除。
- 右侧只存在 `OA`、`发票` checkbox。
- 未配置标签默认 OA 和发票都勾选。
- 保存后规则持久化，刷新仍保持勾选。
- API 不递增银行标签版本。
- 未提交主/子标签只显示 OA、发票都未勾选的 active 标签；需要任一单据的标签在抽屉中仍可见，但完全退出未提交区。
- 保存 API 成功反馈和抽屉关闭不等待投影；当前页随后只执行一次正常列表 GET，响应无 read-model/operation-barrier 字段。

## BRB-E2E-002 提交形成 active relation 后进入已配对

前置：

- 某银行标签明确不需要 OA 和发票。
- 存在 4 条同月、同账户、同标签且未被 active relation 占用的银行流水。

步骤：

1. 在流水规则批量处理页筛选该标签。
2. 选择 4 条银行流水并提交。
3. command 成功后确认页面立即清空选择，并通过当前页正常 GET 收敛；不得等待 operation barrier。
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
4. 通过关联台自己的正常 GET 等待其 freshness gate 收敛。

验收：

- 没有 active relation 时事实保持 unpaired。
- 确认形成 active relation 后，冻结要求满足时同一个 case 的完整成员进入 paired；未满足时保持同 case unpaired 并显示缺失类型。
- 原始银行 rows 未丢失，折叠摘要和展开详情一致。

## BRB-E2E-004 规则保存增量重算 existing active relation

前置：

- 已存在 bank-flow、turnover 或 manual active relation。
- 当前规则与 relation 持久化 requirement 不同。

步骤：

1. 保存新的 OA/发票规则。
2. 获取返回的 recalculation job，等待 durable worker 完成。
3. 读取 existing relation/history 和关联台分区。

验收：

- 只命中持久化 tag proof 包含变化标签的 active relation；case id、成员、relation mode 和金额事实不变。
- 用关系完整 tag set 的当前规则 OR 重算 requirements，并追加 `bank_relation_requirement_recalculated` history；结果未变的关系零写。
- 设置、job、outbox 原子提交；worker 只刷新实际变化关系的精确 Workbench 月份。重复执行同一 job 零新增写，语义 no-op 不创建 job。

## BRB-E2E-006 权限、空集和失败状态 fail closed

前置：

- 准备只读用户、规则保存权限用户、批次提交/撤回权限用户。
- 准备真实空集、非法查询参数和 canonical API 失败场景。

步骤：

1. 只读用户打开页面和抽屉。
2. 尝试保存规则、提交批次、撤回批次、reset submitted。
3. 分别打开真实空集、非法参数和后端失败场景。

验收：

- 无权限时按钮隐藏或禁用，API 返回业务错误。
- canonical 查询成功且 rows 为空时显示真实空态。
- 非法参数或查询失败时显示明确错误和重试入口，不伪装空态。
- API 和页面不出现 read-model status、refresh enqueue 或后台 polling。

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
