# 待找发票

## 目标

`待找发票` 是支出流水发票获取工作台。页面原地使用现有左侧菜单 `待找发票` 和路由 `/pending-invoices`，以一条支出银行流水为一行，帮助财务人员判断是否已经取得进项发票、是否无需开票、是否流水可替票、是否需要补票或选择已有发票。

本页面不新增平行菜单，不替代关联工作台写模型。它读取和写入既有事实源：银行流水、进项发票、OA 投影、`workbench_pair_relations`、银行明细标签和 `pending_invoice_tag_groups`。

页面应明确展示流水方向边界：全量银行流水可以同时包含收入和支出，但本工作台主表只展示支出流水；收入流水应进入销项发票收款、收入核销或往来台账等收入侧工作流。

## 首版范围

- 主表使用 MUI Table，不使用 DataGrid。
- 主表为四个大区：`支出流水`、`发票获取状态`、`进项发票`、`OA`。
- 一行等于一条支出流水。
- 多发票、多 OA、多次支付只展示 primary 摘要和 `+N`，完整关系进入右侧抽屉。
- `Sheet1` 的入口在 `发票获取状态` 列，用于查看历史支付、已付合计、待付金额，并选择已有发票建立关系。
- `待找发票规则设置` 抽屉只允许用户编辑两组无需发票规则：`流水代替发票`、`无需开票`；`需要开票` 由后端按 active 银行明细标签补集派生并只读展示。
- 导出当前筛选、排序命中的全量结果，不只导出当前页。

## 列合并

主表在常见桌面宽度下不得出现横向滚动。列合并口径：

| 大区 | 小列 |
| --- | --- |
| 支出流水 | 对方 / 时间、金额 / 银行账户、摘要 / 凭证 |
| 发票获取状态 | 状态 / 依据 / 主操作 |
| 进项发票 | 发票号码 / 开票日期、销方 / 识别号、金额 / 支付差额 |
| OA | 申请人 / 类型、项目 / 详情 |

流水凭证号、账户明细编号、企业流水号、完整发票明细和完整 OA 字段进入详情抽屉，不塞进主表。

OA 详情点击后展示 OA 系统中的原始支付申请信息，支付申请按 OA 打印预览的表格样式呈现，包括申请人、申请日期、申请类型、支付方式、发票种类、项目、金额、收款方、开户行、账号、申请事由和审批意见。数据来源必须是 OA projection 或 OA 只读适配层；如果 OA 投影未同步，则显示不可用原因，不用关联关系备注临时拼表单。

## 状态口径

状态只由后端根据规则、active pair relation、发票/流水/OA 事实和金额关系计算。前端只展示后端返回的状态，不手算、不直接修改状态。

首版固定 7 类：

| code | 标签 |
| --- | --- |
| `paid_invoiced` | 已支付已开票 |
| `paid_pending_invoice` | 已支付待开票 |
| `paid_pending_future_invoice` | 已支付待后期集中开票 |
| `invoice_not_fully_paid` | 未支付完已开票 |
| `no_invoice_required` | 无需开票 |
| `bank_statement_as_invoice` | 流水代替发票 |
| `pending` | 待处理 |

状态优先级：

1. active bank+input invoice relation 存在且发票价税合计大于已付合计：`invoice_not_fully_paid`。
2. active bank+input invoice relation 存在且金额闭合或关系事实完整：`paid_invoiced`。
3. 命中 `no_invoice_required` 且没有正式发票关系：`no_invoice_required`。
4. 命中 `bank_statement_as_invoice` 且没有正式发票关系：`bank_statement_as_invoice`。
5. 有稳定后端事实证明进入后期开票累计但尚未闭合正式发票：`paid_pending_future_invoice`。
6. 未命中免票/流水替票规则且未发现进项发票关系：`paid_pending_invoice`。
7. 事实不足以可靠判断：`pending`。

`paid_pending_future_invoice` 不能仅因为前端猜测、多条相似流水或普通 `bank_statement_as_invoice` 标签自动成立。

## 规则

规则事实源仍是设置中的 `pending_invoice_tag_groups` 和银行明细 `自动标签规则`，不新增第二套规则表。`pending_invoice_tag_groups` 只持久化 `流水代替发票`、`无需开票` 两组用户选择；`需要开票` 不是用户可编辑事实，而是当前自动标签规则接口中的 `system_rule + active_rules` 减去这两组后的补集。兼容字段 `bank_transaction_tags` 可能包含历史流水分类字典或非规则 taxonomy，不能作为规则抽屉可选标签全集。

- 用户只能在 `流水代替发票`、`无需开票` 中选择已有 active 银行明细自动标签规则。
- 同一标签不能同时归入 `流水代替发票`、`无需开票`、`需要开票`；由于 `需要开票` 后端派生，前端和后端都不得把同一 code 重复展示或匹配到多个分类。
- 规则抽屉按 `输出主标签 / 输出子标签` 展示层级：主标签只作为不可选择标题；子标签才可选择。没有子标签的标签在该主标签下显示一条同名子标签。
- 规则保存后写设置审计，并标记待找发票 read model dirty。
- 只读导出用户不能保存规则。
- 银行明细标签由 app 自动分配，设置页不提供新增、改名或停用银行标签入口；标签管理入口在银行明细页 `自动标签规则` 抽屉。
- 规则只保存银行明细标签 `code`，展示时实时从规则接口返回的 `available_tags` 解析当前名称。银行标签改名后，待找发票规则设置、列表依据和关联台等当前页面都显示新名称。
- 规则选择器和列表依据需要展示银行明细标签的 `输出主标签 / 输出子标签`，但保存事实仍只能是 `tag_codes`。不得把主/子标签中文名写入 `pending_invoice_tag_groups` 作为匹配依据。
- 通过银行明细 `自动标签规则` 抽屉停用标签时，后端必须在同一保存事务中自动从两个持久化待找发票规则组移除该标签、同步版本并写审计，避免跨页面手工解引用。
- 设置页或接口直接提交“两个持久化待找发票规则继续引用已停用标签”的配置仍必须失败，防止产生悬挂规则。规则专用接口若收到旧客户端提交的 `requires_invoice`，后端接受但忽略，并按 active 补集重新返回。

待找发票行中的银行标签字段需要结构化暴露：

- `bank_transaction.effective_tag_code`：稳定标签 code，用于规则匹配。
- `bank_transaction.effective_tag_label`：兼容展示名。
- `bank_transaction.effective_tag_primary_label`、`bank_transaction.effective_tag_sub_label`、`bank_transaction.effective_tag_label_path`：主/子标签展示、搜索和筛选维度。
- `invoice_acquisition_status.matched_rule` 同步返回 `tag_code`、`tag_label`、`tag_primary_label`、`tag_sub_label` 和 `tag_label_path`。

## 选择已有发票

`Sheet1` 工作流通过候选进项发票搜索、预览、确认三步完成：

- 搜索只返回已有进项发票候选，不写业务事实。
- 预览校验流水、发票方向、active relation 冲突、金额影响和权限。
- 确认通过 `WorkbenchPairRelationService` 创建 active bank+invoice pair relation。
- 确认必须使用 `request_id` 作为幂等键，重复提交不创建重复关系。
- 成功后审计、命令记录和 read model dirty scope 必须一致。

## 权限与审计

- 可查看用户可筛选、查看详情。
- 只读导出用户可查看、筛选、详情和导出。
- 只读导出用户不可保存规则、补票、选择已有发票或建立关系。
- 写动作全部由后端校验权限；前端隐藏按钮不是安全边界。
- 规则保存、关系创建、补票确认、导出下载都要写审计或结构化操作记录。

## Read Model

列表热路径使用 `read_model.pending_invoice_rows`。首版不引入 Redis 作为正确性依赖。

- fresh scope 的空结果返回 `200 OK`、`rows=[]`、`read_model_status=fresh`。
- stale/dirty scope 已有可用行时返回最近一次稳定结果，`read_model_status=refreshing` 或 `stale`，页面展示刷新提示但不阻塞用户读取。
- missing scope 或 schema 不兼容时返回 `202 Accepted`、`read_model_status=refreshing`，并 enqueue `pending_invoice.read_model.refresh`。
- 读请求不得因为已有 active dirty scope 而重复写 `job.read_model_dirty_scopes` 或 `job.outbox_events`。
- API 热路径不得因为 read model miss/stale 同步扫描全量流水、发票、OA 和关系事实。

详细 API 契约见 [`../dev/pending-invoices-api.md`](../dev/pending-invoices-api.md)。执行设计记录见 [`../superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md`](../superpowers/specs/2026-05-25-pending-invoice-page-upgrade-design.md)。
