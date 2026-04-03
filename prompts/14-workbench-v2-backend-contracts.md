# Prompt 14：实现 Workbench V2 后端接口与契约

目标：为前端工作台和税金抵扣页提供真实 JSON 接口，替换静态 mock 数据。

前提：

- 阅读：
  - `docs/dev/reconciliation-workbench-v2-backend.md`
  - `docs/dev/reconciliation-workbench-v2-data-contracts.md`

要求：

- 实现 `GET /api/workbench?month=YYYY-MM`
- 实现 `GET /api/workbench/rows/{row_id}`
- 实现主工作台动作接口：
  - 确认关联
  - 标记异常
  - 取消关联
  - 更新银行异常
- 实现 `GET /api/tax-offset?month=YYYY-MM`
- 实现 `POST /api/tax-offset/calculate`
- 增加 `oa_adapter.py` 和 `mongo_oa_adapter.py` 边界
- 增加 `bank_account_resolver.py`

建议文件：

- `backend/src/fin_ops_platform/services/workbench_query_service.py`
- `backend/src/fin_ops_platform/services/workbench_action_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/oa_adapter.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- `backend/src/fin_ops_platform/services/bank_account_resolver.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/app/routes_tax.py`

交付要求：

- 两个月份种子数据可查询
- 三种行详情结构可查询
- 动作接口返回统一结果结构

验证：

- 增加 unittest
- 跑通接口级测试
