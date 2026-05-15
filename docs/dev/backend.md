# 后端开发

## 结构

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化和投影
```

## 入口

- `app/server.py`：当前主 HTTP server 和路由分发。
- `app/auth.py`：OA token 提取、会话识别和权限判断。
- `services/state_store.py`：当前 app 持久化入口。
- `services/mongo_oa_adapter.py`：OA Mongo 只读适配。

## 服务分层

- 导入：`imports.py`、`import_file_service.py`、`import_preview_audit.py`
- 工作台：`workbench_query_service.py`、`workbench_action_service.py`、`workbench_read_model_service.py`
- 配对：`workbench_pair_relation_service.py`、`workbench_candidate_match_service.py`、`workbench_matching_orchestrator.py`
- 异常：`workbench_exception_case_service.py`、`workbench_exception_application_service.py`
- 银行明细：`bank_details_service.py`、`bank_transaction_category_service.py`
- 税金/ETC：`tax_offset_service.py`、`etc_service.py`、`etc_reconciliation_service.py`
- 成本统计：`cost_statistics_service.py`、`cost_statistics_read_model_service.py`
- 运维：`background_job_service.py`、`app_health_service.py`、`app_health_alert_service.py`

## 开发原则

- 不在路由层写复杂规则。
- 不直接读写 OA 原始集合，必须走 adapter。
- 影响工作台展示的写操作必须考虑 read model 和 search cache 失效。
- 导入确认必须重新校验幂等性。
- 新服务需要 snapshot/persistence 时，优先明确状态边界，不继续扩大整包状态。
