# OA 待付款核对

## 定位

`OA待付款核对` 是 Invoices 模块下的只读核对页，用 OA 申请作为主视角，核对同一 OA 的支付状态、支出银行流水和进项发票情况。页面菜单标题为 `OA待付款核对`，页面标题为 `OA 待付款核对`，路由为 `/oa-pending-payments`。

## 数据口径

- 一行对应一个 OA application，主键来自 OA projection，不直接读取 OA Mongo 原始库。
- 支出流水和发票只从 active Workbench pair relations 读取，按 row type 去重。
- 发票仅展示进项发票；多张发票或多条流水时，表格展示最匹配的首条摘要，摘要/备注列合并全部关联流水的摘要和备注，同时通过详情 icon 查看全部关联明细。
- `支出流水无需开票规则设置` 复用待找发票规则能力：`/api/pending-invoices/rules?direction=expense`。

## 支付状态

金额比较按分处理：

- 无支出流水：`unpaid` / `未支付`。
- 支出流水合计等于 OA 金额：`paid` / `已支付`。
- 多个 OA 共享同一流水且 OA 合计等于流水金额：`merged_paid` / `已支付（多条OA合并支付）`。
- 支出流水合计小于 OA 金额：`partially_paid` / `支付少了`。
- 支出流水合计大于 OA 金额：`overpaid` / `支付多了`。
- OA 金额缺失、无法解析或证据不完整：`pending_review` / `待核对`。

## 页面能力

- 主体为紧凑 MUI Table，双层 sticky header 分组为：OA情况、支付状态、支出流水、发票情况，总计 10 列。
- `OA情况` 包含 `OA申请人`、`项目名称`、`金额`。`OA申请人` 第一行展示申请人和 OA 详情 icon，第二行用 tag 展示 OA 类型。
- `支出流水` 包含 `对方户名/交易时间`、`金额/账户`、`摘要/备注`。交易时间、收支方向、银行+后四位均以 tag 展示；流水详情入口为金额行内 icon。
- `发票情况` 包含 `发票号码/发票方`、`日期`、`价税合计`。发票方显示文案为 `进项发票方名称`，数据源仍为进项发票 `sellerName/seller_name`。
- 支持全页面检索、月份、交易日期范围、支付状态筛选、申请人筛选、交易时间排序和分页。
- 支持 OA、单条流水、单张发票详情抽屉，入口均为行内详情 icon。
- 多条流水或多张发票时，关联明细 icon 打开关联明细抽屉，展示全部关联摘要。
- PostgreSQL read model 刷新、缺失或 source version 不一致时，页面显示紧凑刷新提示，不把刷新中状态静默呈现为空数据。

## 生产边界

- 页面所有读取接口必须通过财务运营平台 OA 读权限校验。
- 生产路径读取 `read_model.oa_pending_payment_rows` 和 `read_model.oa_pending_payment_scopes`；列表、筛选项、详情和关联明细都不能在 API 请求中 live scan 全量 OA、银行流水、发票或 Workbench relations。
- read model 的 source versions 覆盖 OA projection、Workbench active pair relations、银行流水导入事实、进项发票导入事实和 OA 待付款自身版本；缺失或不匹配时触发 durable queue refresh。
