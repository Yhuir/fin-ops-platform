# 成本统计测试矩阵

## 自动化覆盖

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 三视图共用成本人口；银行账户唯一/缺失/多账户/退款账户忽略；OA 自动与人工边界；无 OA 成本；金额与完整性失败 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单个 repeatable-read snapshot、集合式批量读取、scope 下推、无 N+1、账户与关系证据完整 |
| Service/API | `tests/test_cost_statistics_api.py` | 仅接受 `project|expense_type|bank_account`；三个根视图对账；账户→项目→明细；搜索/cursor；详情/导出；旧 view 与旧 time-tag endpoint 拒绝；权限和错误合同 |
| Settings | `tests/test_app_settings_service.py`、`tests/test_postgres_state_store.py` | 旧 time/tag setting 不再公开、归一化或持久化；历史字段不回退；无 OA 设置保持独立 |
| Runtime/工具 | `tests/test_http_slo_probe.py`、`tests/test_write_operation_e2e_smoke.py` | 性能探针和写后影响探针只使用当前 view；旧 view 被拒绝 |
| Frontend API/组件 | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` | 三个 view 映射、项目/费用/账户下钻、错误恢复、导出、权限、旧 UI 不存在 |
| 浏览器 E2E | `web/e2e/cost-statistics-flow.spec.ts`、`cost-statistics-relation-fanout.spec.ts` | 真实浏览器三视图、详情、导出、无 OA 保存刷新、关系确认后成本可见 |
| 既有页面回归 | 银行导入、发票导入、ETC、流水规则、往来款、设置与权限 E2E | 写后进入成本页不恢复原始银行统计；非成本银行事实不污染项目成本；其它页面原行为保持 |

## 七类测试适用性

1. 业务核心：适用。账户归属、退款、金额闭合和成本资格均有正反例。
2. Service/Repository：适用。保护 snapshot、查询预算、人工分配同事务和旧设置删除。
3. API 合同：适用。保护 view/参数/DTO、400/403/404/409 与导出上限。
4. Read model/cache/job：不适用。成本统计为 direct canonical read；以“零 Cost queue/worker/cache I/O”的负面断言保护。
5. 前端组件与交互：适用。覆盖 loading/error、三种下钻、详情、导出、权限和分页。
6. 端到端业务流：适用。覆盖关系确认→项目成本、账户→项目→同一成本明细、无 OA 规则→重新读取。
7. 既有功能回归：适用。银行明细继续拥有原始流水，导入/关系/设置/权限链不能受污染。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_cost_statistics_policy \
  tests.test_cost_statistics_canonical_repository \
  tests.test_cost_statistics_api \
  tests.test_app_settings_service \
  tests.test_postgres_state_store \
  tests.test_auth_guard \
  tests.test_http_slo_probe \
  tests.test_write_operation_e2e_smoke

bash scripts/verify.sh lint
cd web && npx tsc --noEmit
cd web && npx vitest run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx
cd web && npx playwright test e2e/cost-statistics-flow.spec.ts e2e/cost-statistics-relation-fanout.spec.ts --project=chromium
```

生产发布后使用现有 admin-token wrapper 执行只读链路验证和 SLO probe，记录 `project`、`expense_type`、`bank_account` 的 p50/p95/max，并抽样完成“账户→项目→明细”。不为本次验证写业务数据或创建数据库备份。
