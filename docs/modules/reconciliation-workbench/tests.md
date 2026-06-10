# 关联台 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py`、`tests/test_etc_backend.py` 及其他 Workbench 相关测试 | 覆盖自动候选金额、方向、证据、唯一性、优先级和 ETC 汇总行业务规则。 |
| 2. Service-layer tests | 适用 | `tests/test_workbench_matching_orchestrator.py`、`tests/test_workbench_reconciliation_engine.py`、`tests/test_etc_backend.py` | 覆盖 matching orchestrator、decision store、pair relation 排除、ETC 人工提交触发 Workbench 投影可见性的服务编排。 |
| 3. API contract tests | 适用 | `tests/test_workbench_v2_api.py`、`tests/test_etc_backend.py` | 覆盖 Workbench payload/grouped rows、candidate application、`source_kind=etc_invoice_summary`、pending relation 和 grouped OA 汇总行。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_workbench_matching_orchestrator.py`、`tests/test_workbench_v2_api.py`、`tests/test_etc_backend.py` | 覆盖 candidate/decision 变更后的 read model invalidation、projection 隐藏散票、生成 open 汇总行、匹配 OA 时追加汇总行。 |
| 5. Frontend component and interaction tests | 按变更判断 | 关联台页面测试、ETC 页面测试 | 本次 ETC 页面测试覆盖入口侧行为；关联台 UI 若改展示需补 Reconciliation 测试。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖 ETC 批次人工提交后进入关联台 open 区等待三项配对。 |
| 7. Existing feature regression tests | 适用 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py`、`tests/test_workbench_v2_api.py`、`tests/test_etc_backend.py` | 覆盖既有 OA-bank 单笔精确、OA-invoice、多发票、多流水分组和 open/paired 边界不回退。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_rules -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_oa_bank_exact_sum_candidate_in_one_open_group -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
cd web && npm run build
```

## 未测风险

- `oa_bank_exact_sum` 当前覆盖后端 service、decision store、API payload/grouping 和 read model invalidation；未新增前端组件测试，因为页面展示继续消费既有 open candidate group shape，没有新增前端交互或字段。
- 本矩阵不替代 SQL active generation 全量生产回放；涉及真实库历史数据时仍需按运维流程做只读验证或 worker dry-run。
