# 发票生命周期、待找发票与 OA 待付款

本文维护进项/销项发票、待找发票、发票使用状态、OA 待付款核对和发票关系的当前业务口径。

## 发票生命周期原则

发票状态应由统一 lifecycle policy 判定，页面不各自定义状态：

- 导入/识别状态：是否存在、是否完整、是否可参与候选匹配。
- 认证/抵扣状态：是否认证、是否进入税金抵扣链路。
- 使用/收款状态：是否已和支出流水、OA 付款或销项收款建立关系。
- 异常状态：重复、冲突、缺少来源、金额/税额不一致、关系撤回。

当前架构采用 `InvoiceLifecyclePolicy` + `invoice_lifecycle` read boundary：

- `InvoiceLifecyclePolicy` 是唯一规则入口，负责待找发票获取状态、进项付款状态、OA 付款状态、销项收款状态和税局认证状态。
- `read_model.invoice_lifecycle_rows` 是跨页面分发边界，按月分片预计算 subject lifecycle。HTTP 热路径只批量读取 read model，不同步扫描发票、银行流水、OA 和关联台事实。
- 现有页面 API shape 保持兼容：待找发票继续返回 `invoice_acquisition_status`，进项使用继续返回 `paymentStatus`，OA 待付款继续返回 `paymentStatus`，销项收款继续返回 `collectionStatus`，税金抵扣继续返回认证字段。
- 页面自己的 read model 仍保留筛选、分页、导出和页面 DTO；生命周期 read model 只分发生命周期结果，不替代业务页面 read model。

需要接入生命周期的页面：

| 页面 | subject | lifecycle 字段 |
| --- | --- | --- |
| 待找发票 | `bank_transaction` | `acquisition_status` |
| 进项发票使用情况 | `input_invoice` | `payment_status`、后续 `certification_status` |
| OA 待付款核对 | `oa_application` | `payment_status` |
| 销项发票收款情况 | `output_invoice` | `collection_status` |
| 税金抵扣 | `input_invoice` | `certification_status` |

## 待找发票

待找发票页面关注支出流水的发票获取状态：

- 列表读取支出流水、候选发票、规则建议和人工关系。
- 筛选覆盖月份、项目、付款对象、状态、异常和规则命中。
- 筛选状态必须以最终 `invoice_acquisition_status.code` 闭环。特别是 `bank_statement_as_invoice` 只展示最终仍为“流水代替发票”的流水；如果同一流水已关联发票并变成 `paid_invoiced`，不能继续出现在“流水代替发票”筛选结果里。
- 规则组筛选仍表达规则口径，例如收入 `requires_invoice` 可以包含已开票、待开票和人工标记状态；但具体状态筛选和规则组筛选不得互相污染。
- 右侧工作流支持候选查看、人工确认、撤回和导出。
- 更新后必须影响税金抵扣、OA 待付款、关联台和成本统计。

### 待找发票规则事实源

待找发票规则是独立规则集事实，不是银行标签设置的附属版本：

- `bank_transaction_tags.version` 只代表银行明细自动标签定义、自动匹配规则、归档/新增/重命名等标签事实。
- `pending_invoice_tag_groups.version` 只代表支出待找发票规则版本。
- `pending_output_invoice_tag_groups.version` 只代表收入待找发票规则版本。
- `requires_invoice` 是 active tag complement，由后端根据当前 active 标签和用户可编辑分组实时派生，不作为用户可编辑事实持久化。

将“外部往来款付款”等银行标签纳入 `no_invoice_required` 是合法的待找发票规则配置。它只改变待找发票/发票生命周期口径，不改变外部往来款台账准入，也不触发免 OA 批次重建。

规则保存成功后发布 `pending_invoice_rules_changed`，刷新 `invoice_lifecycle`、待找发票、关联台、进项使用、OA 待付款、销项收款、税金抵扣、成本统计和搜索 read model。该事件不得刷新外部往来款台账、免 OA 批次或银行账户余额。

## OA 待付款核对

OA 待付款核对页用于对齐 OA 单据、付款流水和进项发票：

- rows/read model 必须返回 payment、invoice、status、candidate、refresh 状态。
- filter-options 需要与列表事实一致，不能前端自造枚举。
- 详情 API 返回可解释的来源、匹配关系和异常原因。
- SQL read model 刷新失败时，页面必须展示 stale/refreshing 状态。

## 发票关系影响

| 动作 | 影响 |
| --- | --- |
| 发票导入确认 | 候选关系、待找发票、税金抵扣、成本统计刷新 |
| 人工确认发票关系 | 支出流水发票状态、OA 待付款状态、关联台关系刷新 |
| 撤回发票关系 | 相关页面回到待处理或异常状态 |
| 发票认证/抵扣变化 | 税金抵扣和发票使用 read model 刷新 |

生命周期变化必须先 dirty/enqueue `invoice_lifecycle.read_model.refresh`，再刷新待找发票、进项使用、OA 待付款、销项收款、税金抵扣、成本统计和搜索等下游页面 read model。

## 相关文档

- API 契约：`../dev/api-contracts.md`
- Runtime：`../app-architecture/runtime-and-ownership.md`
- Worker：`../operations/runtime-worker-governance.md`
