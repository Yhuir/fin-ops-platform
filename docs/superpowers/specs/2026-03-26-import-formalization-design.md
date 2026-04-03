# 导入正式化设计记录

日期：2026-03-26

## 目标

把当前只支持结构化 JSON 的导入能力升级成“真实文件上传 -> 自动识别模板 -> 多文件批量预览 -> 选中文件确认导入”的正式链路，并在 React 工作台中提供可交互的导入中心。

## 范围

本轮覆盖：

- 发票导出文件自动识别与解析
- 银行流水自动识别与解析：
  - 工商
  - 光大
  - 建行
  - 民生
  - 平安
- 多文件拖拽上传与批量预览
- 文件级错误隔离
- 导入会话和确认入库结果的本地持久化
- 发票进项 / 销项自动判断与手动改判
- 模板库展示、按文件重试改判、批次撤销与下载
- 确认导入后自动触发匹配并回灌工作台实时查询
- 导入中心 React 页面
- 与现有 `ImportNormalizationService` 的 preview / confirm 语义对接

本轮不做：

- 异步解析任务队列
- 对象存储
- 超大文件分片上传
- 浏览器端本地 Excel 解析
- 可视化模板配置编辑器
- 销项 / 进项发票自动业务归类之外的复杂票据分类引擎

## 总体方案

### 1. 后端统一解析，前端只负责上传与展示

文件识别、模板解析、字段映射、行级错误定位都放在后端。前端只上传原文件、展示识别结果与预览明细、触发确认导入。

这样做的理由：

- `.xlsx` 和 `.xls` 处理逻辑不应该散落到浏览器端
- 模板识别规则与导入标准化规则需要和后端导入模型保持一致
- 后续增加银行模板时，只需要扩 parser，不需要重复改前端

### 2. 新增文件导入适配层

在现有 `ImportNormalizationService` 之前增加一层“文件导入适配层”：

- `WorkbookReader`：读取 `.xlsx` / `.xls`
- `TemplateDetector`：识别文件模板
- `TemplateParser`：把模板行映射成统一中间字段
- `FileImportService`：组织多文件 preview / confirm / session 状态

`TemplateParser` 不直接落库，也不做幂等判断。parser 只负责把原始文件变成统一的结构化行，再交给现有的 `ImportNormalizationService.preview_import()` 与 `confirm_import()`。

### 3. 新增文件级导入会话

为多文件批量预览增加文件导入 session：

- 一个 session 对应一次拖拽上传
- session 下挂多个 file preview result
- 每个文件都有自己的识别结果、预览统计和逐行结果

文件级失败不会中断整个 session。未识别模板、解析失败、字段异常都只影响当前文件。

### 4. 正式化收口

在第一版文件导入链路之上，继续补以下配套：

- `StateStore`：把导入会话、批次、发票、流水和匹配运行落到本地持久化目录
- 发票方向自动判断：
  - 购方命中本公司主体 -> `input_invoice`
  - 销方命中本公司主体 -> `output_invoice`
  - 前端允许手动覆盖并通过 `retry` 重跑预览
- 原始文件留存：
  - 每个 session 单独目录
  - 便于重试、追溯和撤销
- 导入后闭环：
  - `confirm` 完成后自动运行匹配引擎
  - `/api/workbench` 优先读取实时导入数据，而不是只读 seed 样例
- 批次配套动作：
  - 批次 JSON 下载
  - 批次撤销

## 模板识别设计

输入：

- 文件名
- 扩展名
- 前若干行单元格文本

输出：

- `template_code`
- `batch_type`
- `confidence`

首版模板规则：

- `invoice_export`
  - 命中：`发票代码 / 发票号码 / 数电发票号码 / 销方识别号 / 购方识别号`
  - 业务类型：默认映射为 `input_invoice`

- `icbc_historydetail`
  - 命中：`[HISTORYDETAIL]`
  - 且表头含 `凭证号 / 交易时间 / 对方单位 / 转入金额 / 转出金额 / 摘要`

- `pingan_transaction_detail`
  - 命中：`交易时间 / 账号 / 收入 / 支出 / 对方户名 / 交易流水号 / 核心唯一流水号`

- `cmbc_transaction_detail`
  - 前若干行为元信息：`账户名称 / 账号 / 开户机构 / 币种 / 起始日期`
  - 向下扫描后命中真实表头：`交易日期 / 借方发生额 / 贷方发生额 / 对方户名 / 摘要`

- `ccb_transaction_detail`
  - 命中：`借方发生额（支取） / 贷方发生额（收入） / 对方户名 / 对方开户机构 / 账户明细编号-交易流水号`

- `ceb_transaction_detail`
  - 命中：`交易时间 / 借方发生额 / 贷方发生额 / 对方名称 / 摘要 / 凭证号`

模板识别失败时：

- 标记为 `unrecognized_template`
- 文件级 preview 失败
- 不影响同 session 内其他文件

## 统一中间字段

### 发票

- `counterparty_name`
- `invoice_date`
- `amount`
- `tax_amount`
- `total_with_tax`
- `invoice_code`
- `invoice_no`
- `digital_invoice_no`
- `seller_tax_no`
- `seller_name`
- `buyer_tax_no`
- `buyer_name`
- `invoice_status_from_source`
- `tax_rate`
- 其余详情字段原样保留

### 银行流水

- `account_no`
- `account_name`
- `trade_time`
- `pay_receive_time`
- `counterparty_name`
- `counterparty_account_no`
- `counterparty_bank_name`
- `debit_amount`
- `credit_amount`
- `balance`
- `summary`
- `remark`
- `bank_serial_no`
- `voucher_no`
- `enterprise_serial_no`
- `account_detail_no`
- `voucher_kind`
- `currency`

## API 设计

### `POST /imports/files/preview`

请求：

- `multipart/form-data`
- 支持一次上传多个文件

返回：

- `session_id`
- 每个文件的：
  - `file_id`
  - `file_name`
  - `template_code`
  - `recognized`
  - `batch_type`
  - `total_rows`
  - `created_count`
  - `updated_count`
  - `duplicate_count`
  - `suspected_duplicate_count`
  - `error_count`
  - `row_results`

### `GET /imports/files/sessions/{session_id}`

用途：

- 回看某次上传预览
- 页面刷新后恢复当前 session 内容

### `POST /imports/files/confirm`

请求：

- `session_id`
- `selected_file_ids`

行为：

- 只确认选中的文件
- 每个文件内部复用现有 `confirm_import()`

返回：

- 每个文件对应的 `batch_id`
- 最终导入状态和统计结果

## React 导入中心设计

新增页面：

- 路由：`/imports`
- 顶部导航新增 `导入中心`

页面结构：

1. 拖拽上传区
2. 文件识别与预览列表
3. 确认导入结果区

交互流程：

1. 用户拖入多份文件
2. 前端上传原文件到 `POST /imports/files/preview`
3. 页面展示每个文件的识别结果与预览统计
4. 用户展开文件查看逐行明细
5. 用户勾选需要确认的文件
6. 点击 `确认导入`
7. 页面回显各文件的 `batch_id` 和最终结果

## 依赖

后端新增依赖：

- `openpyxl`
- `xlrd`

原因：

- `.xlsx` 需要稳定读取表格内容与表头
- `.xls` 需要支持老式银行导出格式

## 测试策略

### 后端

- 用真实样例文件覆盖模板识别
- 验证各模板解析出合理的结构化行
- 验证无法识别模板时返回文件级失败
- 验证多文件上传时局部失败隔离
- 验证 `confirm` 只导入选中文件

### 前端

- 导入中心路由和导航
- 多文件上传后的 preview 展示
- 单文件展开逐行明细
- 勾选确认导入请求
- loading / empty / error 状态

## 风险与约束

- `.xls` 解析依赖运行环境安装 `xlrd`
- 民生模板存在元信息区，必须先扫描表头再读数据区
- 发票样例首版默认导入为进项票，如后续需要销项判断，应增加可配置规则而不是在 parser 内硬编码业务猜测
