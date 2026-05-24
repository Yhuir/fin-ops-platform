# 免 OA 流水批量处理三栏树状与关联台折叠设计

## 背景

免 OA 流水批量处理当前页面把批次列表和流水明细放在同一个右侧区域，批次卡片信息偏杂，流水明细“收/支”和金额分列导致扫描效率低。关联台已经存在免 OA 批次 `collapsed_summary` 折叠代码，但部分已提交批次在 SQL read model 路径没有折叠显示。

## 目标

- 页面改为三栏树状结构：左栏分类、中栏批次、右栏流水。
- 左栏保持现有分类 rail 和计数口径。
- 中栏宽度与左栏一致，只显示时间、银行+后四位、流水条数、分类、提交批次和撤回批次操作。
- 右栏流水移除“收/支”列，在金额前显示收/支 tag，在金额下方显示银行+后四位 tag。
- 批次生成口径保持并明确为 `batch_type + scope_month + account_key`，`account_key` 由银行名称和账号后四位构成；内部往来款保留现有跨账户匹配逻辑。
- 关联台复用现有 `collapsed_summary` 契约。已提交免 OA 批次只有 `row_count >= 2` 时折叠，单条保持普通银行流水行，并且仍必须保留免 OA tag、`special_metadata.source_batch_id`、批次版本和撤回批次动作。

## 非目标

- 不新建第二套免 OA 批次模型。
- 不重写关联台折叠组件。
- 不改变提交/撤回的权限、审计、版本冲突和 read model 失效链路。

## 设计

后端继续以 `NoOaBankBatchService` 为批次事实源。API 列表返回批次摘要，详情返回批次内流水，并补齐每条流水的 `bank_name`、`account_last4`、`account_key`，供右栏显示银行 tag。`account_key` 使用现有规范：`bank_name:account_last4`。

关联台仍由 `WorkbenchCandidateGroupingService` 生成折叠摘要。折叠条件收紧为同一 `source_batch_id` 且银行流水数量至少 2。SQL projection 在应用 `no_oa_bank_batch` relation 时必须把 relation `special_metadata`、`display_tags` 和撤回动作写入银行行，否则现有折叠判断无法识别批次来源，单条普通行也会丢失撤回入口。

前端 `NoOaBankBatchPage` 保持顶部状态、月份和账号筛选。主体 grid 改为三列：左栏分类、同宽中栏批次、右栏流水明细。中栏批次节点的“时间”显示 `scope_month`，只保留用户要求的最小信息和操作按钮。右栏表格保留交易时间、对方户名、金额、摘要/用途/备注、分类来源；金额单元格内显示收/支 tag、金额和银行+后四位 tag。

## 验证

- 后端测试覆盖批次按银行后四位拆分、单条不折叠但可撤回、两条及以上折叠、SQL projection 元数据传播。
- 前端测试覆盖 no-OA API 字段映射、三栏区域、批次节点文案、流水金额 tag 和银行 tag。
- 构建验证使用现有 `npm run build`。
