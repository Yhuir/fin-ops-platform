# Prompt 08 Project Costing Foundation Design

## Goal

在不破坏现有核销闭环的前提下，为项目维度建立最小可用底座，让发票、流水、核销单、台账可以按项目归集，并支持人工指定项目归属和项目视角查询。

## Scope

本次只覆盖以下内容：

- 复用现有 `ProjectMaster` 作为项目主数据模型
- 新增项目归属服务，支持人工指定对象项目
- 新增项目归属记录与审计轨迹
- 提供项目汇总查询和单项目详情查询
- 在原型页中增加最小 `项目归集` 视图

本次不做：

- 成本分摊算法
- 项目毛利计算
- 多项目拆分归属
- 独立 BI 看板

## Design

### 1. Boundary

新增 `ProjectCostingService`，只负责：

- 项目主数据补齐
- 项目归属优先级计算
- 手动归属动作
- 项目汇总查询

它不改写导入、匹配、核销、台账的业务规则，只消费这些服务产生的业务对象。

### 2. Project Assignment Priority

项目归属优先级固定为：

1. `手动指定`
2. `OA 单据带出的项目`
3. `对象已有 project_id`
4. `无归属`

为了让“手动指定”与“对象原始 project_id”可区分，新增独立 `ProjectAssignmentRecord`。项目查询时优先读取该记录，而不是简单依赖对象当前字段。

### 3. Effective Project Resolution

不同对象的项目解析规则：

- `Invoice`
  - 手动指定
  - `oa_form_id` 对应 OA 单据的项目
  - `invoice.project_id`
- `BankTransaction`
  - 手动指定
  - `transaction.project_id`
- `ReconciliationCase`
  - 手动指定
  - `approval_form_id / related_oa_ids` 对应 OA 单据的项目
  - `case.project_id`
  - 若关联对象项目唯一，则回落到该项目
- `FollowUpLedger`
  - 手动指定
  - `ledger.project_id`
  - 来源核销单的项目

### 4. Query Model

新增项目汇总读模型 `ProjectSummary`，先只输出底座所需指标：

- `income_amount`
- `expense_amount`
- `reconciled_amount`
- `open_ledger_amount`
- `invoice_count`
- `transaction_count`
- `case_count`
- `ledger_count`

收入和支出当前基于发票类型聚合：

- 销项票 -> 收入
- 进项票 -> 支出

### 5. API

新增接口：

- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects`
- `POST /projects/assign`

其中：

- `POST /projects` 用于手工创建项目主数据
- `POST /projects/assign` 用于手工把对象归属到项目

### 6. Prototype

继续沿用现有原型页，只增加平行 `项目归集` 视图：

- 顶部入口 `项目归集`
- 汇总卡片显示项目数量、收入、支出、未闭环金额
- 左侧项目汇总表
- 右侧显示当前项目详情
- 下方显示待归属对象表，按行选择项目并执行归属

它不是正式成本看板，只是项目维度底座的验证界面。

## Impact

### Backend

- `domain/models.py`
  - 增加 `ProjectAssignmentRecord`
  - 增加 `ProjectSummary`
- `services/integrations.py`
  - 补项目与 OA 单据查询辅助方法
- `services/project_costing.py`
  - 新增项目归属与汇总服务
- `app/server.py`
  - 新增项目接口

### Frontend Prototype

- `web/prototypes/reconciliation-workbench-v2.html`
  - 新增 `项目归集` 页面
  - 新增项目归属操作入口

## Testing

至少覆盖：

- 手动项目归属优先于 OA 与对象已有字段
- 按项目汇总收入、支出、已核销、未闭环金额
- 项目接口 round-trip
- 原型页脚本保持可解析
