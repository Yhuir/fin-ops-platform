# 成本统计测试矩阵

## 自动化覆盖

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 三个项目成本 view 共用成本人口；两个流水 view 共用银行人口并按`支出-收入`计算净额；标签分面；账户归属；OA 自动/人工边界；人工任务保留 canonical 流水标签且不输出摘要；无 OA 成本；金额与完整性失败 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单个 repeatable-read snapshot、集合式批量读取、scope 下推、无 N+1；流水 view 在 OA/关系/人工分配前返回；人工任务对全部关系流水只批量分类一次并保留完整标签路径 |
| Service/API | `tests/test_cost_statistics_api.py` | 接受五个正式 view；三个成本根视图对账并在同一 snapshot 返回基础流水方向数；时间/标签方向统计与导出；人工流水 `tags`/无旧 `summary`；账户/标签下钻；搜索/cursor；旧 `bank` 与旧 time-tag endpoint 拒绝；权限和错误合同 |
| Settings | `tests/test_app_settings_service.py`、`tests/test_postgres_state_store.py` | 旧 time/tag setting 不再公开、归一化或持久化；历史字段不回退；无 OA 设置保持独立 |
| Runtime/工具 | `tests/test_http_slo_probe.py`、`tests/test_write_operation_e2e_smoke.py` | 性能探针和写后影响探针使用当前正式 view；旧 `bank` 被拒绝 |
| Frontend API/组件 | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx`、`CostExplorerList.test.tsx` | 五个 view 映射、统一基础流水统计、HeroUI ListBox 完整名称、无展开/归集/净额旧 UI、项目/费用/账户/标签下钻、人工分配 Chip、正负方向、错误恢复、导出和权限 |
| 浏览器 E2E | `web/e2e/cost-statistics-flow.spec.ts`、`cost-statistics-relation-fanout.spec.ts` | 真实浏览器五视图、方向展示、标签下钻、详情、导出、无 OA 保存刷新、关系确认后成本可见 |
| 既有页面回归 | 银行导入、发票导入、ETC、流水规则、往来款、设置与权限 E2E | 原始 `按银行`不恢复；银行流水分析不污染项目成本；其它页面原行为保持 |

## 七类测试适用性

1. 业务核心：适用。流水正负净额、标签分面、账户归属、退款、金额闭合和成本资格均有正反例。
2. Service/Repository：适用。保护 snapshot、查询预算、人工分配同事务和旧设置删除。
3. API 合同：适用。保护 view/参数/DTO、400/403/404/409 与导出上限。
4. Read model/cache/job：不适用。成本统计为 direct canonical read；以“零 Cost queue/worker/cache I/O”的负面断言保护。
5. 前端组件与交互：适用。覆盖 loading/error、五视图切换、项目/账户/标签下钻、详情、导出、权限和分页。
6. 端到端业务流：适用。覆盖时间流水、标签→流水、关系确认→项目成本、账户→项目→同一成本明细、无 OA 规则→重新读取。
7. 既有功能回归：适用。银行明细继续拥有账户级浏览和维护，导入/关系/设置/权限链不能受污染。

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

生产发布后使用现有 admin-token wrapper 执行只读链路验证和 SLO probe，记录五个 view 的 p50/p95/max；核对 `time|bank_tag` 的流水人口、支出、收入、净支出完全一致，并分别抽样“标签→流水”和“账户→项目→成本明细”。不为本次验证写业务数据或创建数据库备份。
