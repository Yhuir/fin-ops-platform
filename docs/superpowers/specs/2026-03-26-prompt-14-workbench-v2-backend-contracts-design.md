# Prompt 14 Workbench V2 Backend Contracts Design

## Goal

为 React 工作台和税金抵扣页补稳定的真实 JSON 契约层，替换前端长期依赖静态 mock 的状态。

## Scope

本次覆盖：

- `GET /api/workbench`
- `GET /api/workbench/rows/{row_id}`
- `POST /api/workbench/actions/confirm-link`
- `POST /api/workbench/actions/mark-exception`
- `POST /api/workbench/actions/cancel-link`
- `POST /api/workbench/actions/update-bank-exception`
- `GET /api/tax-offset`
- `POST /api/tax-offset/calculate`
- OA adapter / Mongo OA adapter 边界
- 银行账户识别服务

本次不做：

- React 页面真实联调
- Mongo OA 真实接入
- V2 动作直接落核心核销单
- 税金抵扣真实发票仓接入

## Design

### 1. Compatibility Strategy

保留旧接口：

- `/workbench`
- `/workbench/actions/*`

新增 V2 契约层：

- `/api/workbench*`
- `/api/tax-offset*`

这样 Prompt 14 不会打断 01-08 已通过的能力。

### 2. Service Split

- `WorkbenchQueryService`：月度种子、主表行、详情响应
- `WorkbenchActionService`：确认关联、标记异常、取消关联、更新银行异常
- `TaxOffsetService`：月度税金清单与勾选试算
- `BankAccountResolver`：账号 -> 银行展示名
- `OAAdapter / MongoOAAdapter`：OA 数据源边界

### 3. Data Strategy

V2 先使用内存种子数据：

- `2026-03`
- `2026-04`

每个月都提供：

- OA / 银行 / 发票 paired/open 行
- 三类详情字段
- 税金抵扣 output/input 清单

### 4. Action Result Contract

所有 V2 动作统一返回：

- `success`
- `action`
- `month`
- `affected_row_ids`
- `updated_rows`
- `message`

这样前端不需要为四种动作分别写完全不同的解析逻辑。

## Testing

至少覆盖：

- 两个月份工作台可查询
- OA / 银行 / 发票详情可查询
- 四类动作返回统一结构并修改行状态
- 税金接口和计算接口都可用
- 全量后端 unittest 继续通过
