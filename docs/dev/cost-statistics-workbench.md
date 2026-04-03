# 成本统计页面开发说明

本文档定义“成本统计”页面的产品边界、数据口径、接口建议、前端结构和测试重点。它建立在 Prompt 08 的项目归集底座之上，但不是项目归属底座本身。

## 1. 页面定位

`成本统计` 是一个新的独立页面入口，位于顶部导航 `税金抵扣` 右侧。

它的目标不是做新的核销动作，而是把**已建立 OA 映射关系的支出银行流水**整理成可统计、可下钻、可导出的成本视图。

页面职责：

- 按月份统计项目成本
- 按项目查看费用明细
- 层层下钻到具体银行流水
- 导出当前视图

页面不负责：

- 重新做核销
- 修改 OA 业务单据
- 做复杂成本分摊
- 做利润或毛利分析

## 2. 数据口径

### 2.1 主数据源

成本统计以 `BankTransaction` 为主数据源。

### 2.2 入统条件

只有同时满足以下条件的流水才进入成本统计：

- 属于**支出类流水**
- 已经与 OA 建立确认关系，或能够稳定拿到 OA 字段映射
- 能取到以下字段：
  - `project_name`
  - `expense_type`
  - `expense_content`

### 2.3 排除项

以下记录默认不进入成本统计主结果：

- 收入流水
- 未确认关联的流水
- 只有发票、没有流水的记录
- 只有 OA、没有流水的记录
- OA 字段缺失的流水
- 已忽略记录

### 2.4 金额口径

- 统一使用银行流水的**实际支出金额**
- 统计页内金额默认展示为正数
- 不在该页面引入负数抵扣、差额核销等复杂口径

## 3. 页面层级

页面内建议分三层：

### 第 1 层：按月份统计

字段：

- 项目名称
- 费用类型
- 金额
- 费用内容

推荐聚合键：

- `month + project_name + expense_type + expense_content`

这一层的目的是让财务先看“本月每个项目花了什么钱、属于什么费用类型”。

### 第 2 层：按项目查看

用户点击某一个项目后进入项目明细层。

字段：

- 时间
- 费用类型
- 金额
- 费用内容

这一层仍限定在当前月份内，只是把同一项目的成本明细展开。

### 第 3 层：具体银行流水

用户继续点击后进入具体流水层。

这一层至少展示：

- 交易时间
- 借方发生额 / 贷方发生额
- 对方户名
- 支付账户
- 摘要 / 备注
- 对应 OA 项目名称
- 对应 OA 费用类型
- 对应 OA 费用内容

## 4. 页面结构建议

推荐页面结构：

1. 顶部工具区
   - 年月选择
   - `按月份统计 / 按项目统计` 视图切换
   - 导出按钮
2. 面包屑区
   - 例如：`2026年3月 / 项目统计 / 云南溯源科技`
3. 汇总区
   - 当前层级的记录数、金额合计
4. 主表区
   - 当前层级表格

不建议：

- 用弹窗承载主下钻流程
- 在同一页塞过多卡片化摘要
- 把“统计页”和“关联台动作”混在一起

## 5. 后端读模型建议

建议新增独立只读服务，例如 `CostStatisticsService`。

### 5.1 月份汇总行

建议读模型：

- `month`
- `project_name`
- `expense_type`
- `expense_content`
- `amount`
- `transaction_count`
- `sample_transaction_ids[]`

### 5.2 项目明细行

建议读模型：

- `month`
- `project_name`
- `trade_time`
- `expense_type`
- `expense_content`
- `amount`
- `transaction_id`
- `oa_row_id`

### 5.3 流水详情读模型

建议读模型：

- `transaction_id`
- `trade_time`
- `debit_amount`
- `credit_amount`
- `counterparty_name`
- `payment_account_label`
- `summary`
- `remark`
- `project_name`
- `expense_type`
- `expense_content`
- `oa_reference`

## 6. 接口建议

### `GET /api/cost-statistics?month=YYYY-MM`

返回当前月份汇总结果。

### `GET /api/cost-statistics/projects/{project_name}?month=YYYY-MM`

返回指定项目在当前月份的成本明细。

### `GET /api/cost-statistics/transactions/{transaction_id}`

返回某一条具体流水详情，以及对应 OA 成本字段。

### `GET /api/cost-statistics/export?...`

导出当前层级结果。

当前实现支持导出参数：

- `month`
- `view=month|project|transaction`
- `project_name`（如适用）
- `transaction_id`（如适用）

当前导出格式：

- `xlsx`

当前文件名规则：

- 月份汇总：`成本统计_{month}_月份汇总.xlsx`
- 项目明细：`成本统计_{month}_项目明细_{project}.xlsx`
- 流水详情：`成本统计_{month}_流水详情_{project}_{transactionId}.xlsx`

## 7. 前端实现建议

### 7.1 新页面与导航

- 新增 `成本统计` 页面路由，例如 `/cost-statistics`
- 顶部导航按钮放在 `税金抵扣` 右侧
- 页面内自带筛选作用域：
  - `按时间` 和 `按费用类型` 支持单月或区间
  - `按项目` 默认全部期间

### 7.2 下钻方式

使用三视图分析台：

- `按时间`：主表 + 流水详情弹窗
- `按项目`：从左到右 `项目 -> 费用类型 -> 流水`
- `按费用类型`：费用类型列表 + 流水 + 详情弹窗

### 7.3 导出

- 导出按钮跟随当前层级
- 当前层级切换后，导出内容同步变化
- 导出中显示明确 loading 文案
- 导出成功显示结果反馈
- 导出失败显示错误反馈

## 8. 与 Prompt 08 的关系

Prompt 08 解决的是：

- 项目主数据
- 项目归属
- 项目汇总底座

本页解决的是：

- 基于已归属 / 已确认 OA 成本字段的流水统计展示
- 面向财务使用者的月度成本分析与下钻

所以它应视为 Prompt 08 之后的正式页面能力，而不是 Prompt 08 的同义改名。

## 9. 测试重点

后端：

- 只统计支出类流水
- 未关联 OA 或缺少 OA 成本字段的流水不入统
- 月份汇总与项目明细金额一致
- 钻到底层流水时，字段完整
- 导出结果与当前视图一致

前端：

- 顶部按钮能进入新页面
- `按时间` 默认进入
- `按项目` 采用从左到右三列联动
- `按费用类型` 支持费用类型筛选与流水查看
- 统一使用 `导出中心` 弹窗做导出配置、预览和下载
- loading / empty / error 清晰可见

## 10. 项目明细强导出当前口径

当前成本统计导出已经升级为“统一导出中心 + 强项目导出底座”的口径：

- 后端：
  - 一个项目导出一份完整多 sheet 工作簿
  - 包含：
    - 项目汇总
    - 按费用类型汇总
    - 按费用内容汇总
    - 流水明细
    - OA 关联明细
    - 发票关联明细
    - 异常与未闭环
- 前端：
  - 页面只保留一个 `导出中心`
  - `导出中心` 内支持：
    - 按时间
    - 按项目
    - 按费用类型
  - `按时间`：
    - 自定义月份
    - 自定义时间区间（精确到日）
  - `按项目`：
    - 项目下拉选择
    - 费用类型多选或全选
    - 默认全部期间
  - `按费用类型`：
    - 费用类型多选或全选
    - 当前月份
    - 自定义时间区间（精确到日）
  - 所有模式都支持：
    - 仅预览
    - 导出
  - 预览会显示：
    - 文件名
    - 统计范围
    - sheet 数量
    - 命中条数
    - 金额合计
    - 样例前几行

仍待下一阶段补齐的能力：

- 导出历史持久化与任务化
- 导出记录查询
- 更强的导出 QA 和可追溯性

对应文档：

- 强导出设计文档：[2026-04-01-cost-statistics-project-export-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-project-export-design.md)
- 后续 prompt：
  - [21-project-detail-export-history-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/21-project-detail-export-history-and-qa.md)
