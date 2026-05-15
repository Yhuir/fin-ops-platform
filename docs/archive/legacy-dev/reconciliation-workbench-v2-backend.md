# 关联工作台 V2 后端实现

## 1. 当前已落地模块

本轮后端分成两层：

- 旧工作台与核销服务：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/reconciliation.py`
  - `backend/src/fin_ops_platform/services/imports.py`
  - `backend/src/fin_ops_platform/services/matching.py`
- 新的 V2 契约层：
  - `backend/src/fin_ops_platform/app/routes_workbench.py`
  - `backend/src/fin_ops_platform/app/routes_tax.py`
  - `backend/src/fin_ops_platform/services/workbench_query_service.py`
  - `backend/src/fin_ops_platform/services/workbench_action_service.py`
  - `backend/src/fin_ops_platform/services/tax_offset_service.py`
  - `backend/src/fin_ops_platform/services/oa_adapter.py`
  - `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
  - `backend/src/fin_ops_platform/services/bank_account_resolver.py`

## 2. 已实现接口

### 2.1 Workbench V2 查询

- `GET /api/workbench?month=2026-03`
- `GET /api/workbench/rows/{row_id}`

返回：

- `summary`
- `paired.oa / paired.bank / paired.invoice`
- `open.oa / open.bank / open.invoice`
- 单行详情 `summary_fields / detail_fields`

说明：

- V2 契约层已提供两个月份种子数据：`2026-03`、`2026-04`
- OA / 银行 / 发票三类行都能查询
- 行级详情已拆成独立接口，不再依赖主列表一次性塞完所有字段

### 2.2 Workbench V2 动作

- `POST /api/workbench/actions/confirm-link`
- `POST /api/workbench/actions/mark-exception`
- `POST /api/workbench/actions/cancel-link`
- `POST /api/workbench/actions/update-bank-exception`

四类动作统一返回：

- `success`
- `action`
- `month`
- `affected_row_ids`
- `updated_rows`
- `message`

当前动作是契约层内存态更新，目的是先给 React 工作台稳定 JSON 协议。

### 2.3 税金抵扣 API

- `GET /api/tax-offset?month=2026-03`
- `POST /api/tax-offset/calculate`

返回：

- `output_items`
- `input_items`
- `default_selected_output_ids`
- `default_selected_input_ids`
- `summary`

其中 `calculate` 负责按勾选 ID 试算：

- `output_tax`
- `input_tax`
- `deductible_tax`
- `result_label`
- `result_amount`

## 3. 适配层与边界

### 3.1 OA 适配层

- `oa_adapter.py` 定义了 `OAAdapter` 边界和 `InMemoryOAAdapter`
- `mongo_oa_adapter.py` 已预留真实 Mongo OA 替换点

当前状态：

- Workbench V2 用内存种子驱动 OA 行
- Mongo adapter 只保留接口边界，尚未接真实库

### 3.2 银行账户识别

`bank_account_resolver.py` 负责把账号识别成前端可直接展示的：

- 银行名
- 账户类型
- 末四位

例如：

- `招商银行 基本户 9123`
- `建设银行 一般户 1138`

## 4. 与旧工作台的关系

旧接口仍保留：

- `GET /workbench`
- `POST /workbench/actions/confirm`
- `POST /workbench/actions/exception`
- `POST /workbench/actions/offline`
- `POST /workbench/actions/difference`
- `POST /workbench/actions/offset`

这样可以保证：

- 01-08 的测试和服务不回退
- Prompt 14 的 `/api/*` 契约层可独立演进
- Prompt 15 再把 React 页面从 mock 切到真实 API

## 5. 已实现但故意保留的边界

- React 前端还没有切到 `/api/*`，当前仍使用本地 mock 数据
- OA 适配层还没接 MongoDB / 真实 OA 系统
- V2 动作当前只改契约层种子状态，不落核心核销单
- 税金抵扣当前仍是月度样例数据，不接真实发票仓

这些边界不阻塞 Prompt 14，但会影响 Prompt 15 的联调深度。

## 6. 验证方式

后端全量测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

本轮新增重点测试：

- `tests/test_workbench_v2_api.py`
- `tests/test_tax_offset_api.py`

接口级验收点：

- 两个月份都能返回 V2 工作台数据
- OA / 银行 / 发票三类详情接口可查
- 四类动作接口返回统一结果结构
- 税金抵扣计算结果与选中 ID 一致
