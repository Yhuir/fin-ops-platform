# 免 OA 银行批次 E2E Coverage

| Spec ID | 状态 | 自动化入口 | 说明 |
| --- | --- | --- | --- |
| `NO-OA-E2E-001` | covered | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_workbench_integration.py` | 覆盖 submit/withdraw、canonical relation、空 targets、零普通写 fan-out。 |
| `NO-OA-E2E-002` | covered | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_architecture_guards.py` | 覆盖 exact scope、访问时 refresh、dedupe 和无 `all` fallback。 |
| `NO-OA-E2E-003` | covered | `tests/test_no_oa_bank_batch_routes.py`、`tests/test_bank_flow_rule_batch_backend_boundary.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 no-OA 与 bank-flow route/service/read model 隔离。 |
| `NO-OA-E2E-004` | covered | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_reversible_relation_closure_postgres.py` | 覆盖幂等、冲突、失败回滚和无半写。 |

本模块无独立 Browser 页面，因此 frontend interaction/Browser E2E 由 bank-flow 页面和 Workbench relation consumer 覆盖；生产 legacy fixture 验证仍由 Phase 27 矩阵执行。
