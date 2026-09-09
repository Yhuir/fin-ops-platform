# 成本统计测试矩阵

## 自动化覆盖

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 三个项目成本 view 共用成本人口；两个流水 view 共用银行人口并按`支出-收入`计算净额；标签分面；账户归属；OA 自动/人工边界；人工任务保留 canonical 流水标签且不输出摘要；无 OA 成本；金额与完整性失败 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单个 repeatable-read snapshot、集合式批量读取、scope 下推、无 N+1；流水 view 在 OA/关系/人工分配前返回；人工任务对全部关系流水只批量分类一次并保留完整标签路径 |
| Service/API | `tests/test_cost_statistics_api.py` | 接受五个正式 view；三个成本根视图对账并在同一 snapshot 返回基础流水方向数；时间/标签方向统计与导出；人工流水 `tags`/无旧 `summary`；账户/标签下钻；搜索/cursor；旧 `bank` 与旧 time-tag endpoint 拒绝；权限和错误合同 |
| Settings | `tests/test_app_settings_service.py`、`tests/test_postgres_state_store.py` | 旧 time/tag setting 不再公开、归一化或持久化；历史字段不回退；无 OA 设置保持独立 |
| Runtime/工具 | `tests/test_http_slo_probe.py`、`tests/test_write_operation_e2e_smoke.py` | 性能探针和写后影响探针使用当前正式 view；旧 `bank` 被拒绝 |
| Frontend API/组件 | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx`、`CostExplorerList.test.tsx` | 五个 view 映射、统一基础流水统计、HeroUI ListBox 完整名称、无展开/归集/净额旧 UI、项目/银行主子标签/账户下钻、来源选择与只读账户/标签、正负方向、错误恢复、导出和权限 |
| 浏览器 E2E | `web/e2e/cost-statistics-flow.spec.ts`、`cost-statistics-relation-fanout.spec.ts` | 真实浏览器五视图、方向展示、标签下钻、详情、导出、无 OA 保存刷新、关系确认后成本可见 |
| 既有页面回归 | 银行导入、发票导入、ETC、流水规则、往来款、设置与权限 E2E | 原始 `按银行`不恢复；银行流水分析不污染项目成本；其它页面原行为保持 |

## 七类测试适用性

1. 业务核心：适用。流水正负净额、标签分面、账户归属、退款、金额闭合和成本资格均有正反例。
2. Service/Repository：适用。保护 snapshot、查询预算、人工分配同事务和旧设置删除。
3. API 合同：适用。保护 view/参数/DTO、400/403/404/409 与导出上限。
4. Read model/cache/job：不适用。成本统计为 direct canonical read；以“零 Cost queue/worker/cache I/O”的负面断言保护。
5. 前端组件与交互：适用。覆盖 loading/error、五视图切换、项目/账户/标签下钻、详情、导出、权限和分页。
6. 端到端业务流：适用。覆盖时间流水、标签→流水、关系确认→项目成本、账户→项目→主标签→子标签→同一成本明细、无 OA 规则→重新读取。
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

## 2026-09-09 来源分配专项

- 业务核心：`test_cost_statistics_source_allocation.py`、`CostSourceAllocation.test.ts`：Decimal/整数分、空与零、双边闭合、固定目标、重复来源、退款/非成本、唯一解与多对多人工边界。
- PostgreSQL：`test_cost_statistics_source_postgres.py`：持久化重读、同事务审计、审计失败回滚、两并发一个成功、来源金额更新/关联撤回并发冲突、无效目标不写入、跨月视角对账。
- API：轻量摘要和定向详情、新 source JSONB、缺标签保存仍 pending、旧费用类型参数拒绝、源金额详情、聚合导出与明细 sheet parity。
- 前端：`cost-source-allocation.spec.ts`：真实浏览器增行/选来源/金额350+250、焦点、完成任务迁移、缺资料重开回填、409草稿保留、只读、390/1440宽度；`cost-statistics-flow.spec.ts` 保护三条新下钻与旧银行视角。
- 迁移：0169可重放，旧记录source为NULL不重建多对多决定。
- Read model/cache/job仍不新增；既有银行/关联的写后读取与部署worker健康由原回归保护。

验证结果和生产测量记录于[实施决策](implementation-notes.md)。不将本地mock耗时当生产性能。

## 紧凑抽屉重构专项（2026-09-09）

- `CostSourceAllocation.test.ts`：固定目标、来源派生合计、显式零、非法精度、旧来源缺失；不确定保存结果必须同时核对版本、既有 fingerprint 和完整分配内容，不能仅凭版本递增判成功。
- `CostSourceAllocationForm.test.tsx`：一张 OA 多成本项分组计数、内部 ID/冗余数字不进入可见文本、表头、零成本/新增/删除/焦点、非固定金额保存。
- `CostStatisticsPage.test.tsx`：既有页签、下钻、权限、抽屉读取和保存回填，更新旧可见 ID 与独立金额输入断言。
- `apiClient.test.ts`：Cost PUT 显式关闭 HTML 路径重试后只发一次请求；其他调用方的既有默认行为仍由原测试保护。HTTP DTO 未改变，保留 Cost API 合同测试。
- `cost-source-allocation.spec.ts`：350/250保存与已完成重读、缺标签pending、409保留、只读窄屏、详情失败重试、提交成功但响应丢失后GET核实、统计刷新失败不重复PUT、删除/新增焦点；2/100合法来源行的输入、选择、增删和数据到达后渲染测量，无新增性能gate。
- `test_cost_statistics_source_postgres.py` 增加真实 PG16 可编辑目标600/400案例：原OA700/400不变；来源三行通过现有 HTTP 路由保存重读后，三个视角8月/9月各500。既有并发、审计、回滚测试继续运行。
- `FinanceTableMigration.test.ts` 仅登记成本来源分组编辑表为原生表格的明确例外，避免把专用输入规则扩进公共 FinanceTable。既有检查仍覆盖其余页面。
- 不新增 read model/cache/worker 生命周期测试：本次没有相应运行时变更。生产验证只读；合法写入及回滚使用任务独占数据库。
