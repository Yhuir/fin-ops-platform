# 成本统计测试矩阵

## 审批完成时间可空专项（2026-09-10）

- Policy：支付申请和日常报销在审批已完成、时间为NULL/空字符串/空白/字段缺失时，仍生成真实来源成本；同组旧OA缺时间不阻断整组；进行中、暂存或未知状态即使有时间也不计成本。
- PostgreSQL：空approved_at且2025年申请的OA可按现有规则人工分配，2026年8/9月付款分别归月；详情保留空审批时间，原OA数据未补填。
- API：三个成本视角、详情、预览和真实XLSX导出一致；空时间不改变响应合同。既有金额、来源、关系、权限与银行流水视角回归继续执行。
- 七类覆盖：1业务核心、2服务/Repository、3API、6数据库到查询业务流、7回归有新增/调整；5前端复用现有组件及浏览器用例，无交互变更；4无read model/cache/job改动。
- 既有模块边界测试将完成状态常量的责任检查定位到Policy，删除Repository无调用的重复判断后，不要求保留死代码。

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

## 双表格与字段浮层专项（2026-09-09）

- 业务核心：来源/金额/owner 错误可以同时存在，原精度、闭合、固定金额、零及重复来源断言保留。
- 组件：实际展示行计数、无内部 ID、原费用类型与银行主/子 Chip 分离；金额保持、来源切换、首/中/末行删除、唯一同行新增、键盘查看全文、错误格独立且无段落。
- 浏览器：真实鼠标与键盘选择；错误出现前后来源框 y/height 不变；错误浮层可见且 Escape 不关闭抽屉；原保存、冲突、失联后核实、只读、刷新失败链继续保护。
- 性能：2/100条初始合法来源行，各20次输入、增删、打开菜单与实际切换来源；选择测量先编辑另一行释放真实来源，再交替两条来源，避免同值事件冒充选择性能。数据到表 DOM 为单次观测，不标作 p95。
- 服务/API/数据库本轮无改动，复用已有90项真实PG成本专项及现有前端API合同；read model/cache/worker类别不适用。

## 明确来源预填、四色与合并单元格专项（2026-09-10）

- `test_cost_statistics_source_allocation.py`：金额相等无来源证据不填、明确一对一/一对多、同 OA 多单元一来源、部分组确定、冲突引用、多对多歧义、非固定金额/保存/过期/退款/非成本不猜测；计算不修改输入。
- `test_cost_statistics_source_postgres.py`：真实 PG 原始引用投影→详情建议→无写入且列表不变→用户提交→保存重读；没有引用仅金额相等不填。沿用并发冲突、审计回滚和跨月三视角回归。
- `CostSourceAllocation.test.ts` / `CostSourceAllocationForm.test.tsx`：建议初始化、保存优先、stale 不回填、rowSpan 增删、删除首条保留后续来源、删除全部保留身份。
- `cost-source-allocation.spec.ts`：浏览器端建议映射、人工保存前零 PUT、四种实色、两格 rowSpan、清空后折叠重开不重填；现有只读、失败反馈、冲突、窄屏与100行性能样本继续验证。`cost-statistics-flow` / `relation-fanout` 保护五视图及关系链路。
- 七类测试适用性不变：1/2/3/5/6/7 适用，第4类无新的 read model/cache/job 生命周期；保护 canonical 直读与无额外请求即可。

## 2026-09-10 预填实际场景修复

- 单元测试替换“无显式引用一律为空”的旧预期；新增三OA四流水、重复金额、全局替代组合、独立确定部分、共享单来源、零目标、失效/已保存、缺资料、输入上限与搜索耗尽。
- PostgreSQL + HTTP：无原始引用的唯一金额组合GET预填，保持pending/零写入；确认PUT后审计、重读及三个视角跨月闭环，保留冲突/并发/回滚测试。
- COST-E2E-014：实际金额结构四行呈现、两格rowSpan、无自动PUT、保存并在已完成重读；原草稿保护/错误/只读/窄屏测试保留。
- 类别1/2/3/5/6/7适用；第4类无read model/cache/job变更，仍验证列表不带建议和GET无写入。

本轮实际执行入口（PG环境变量指向本次独占测试库，现已清理）：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_source_allocation tests.test_cost_statistics_source_postgres tests.test_cost_statistics_policy tests.test_cost_statistics_canonical_repository tests.test_cost_statistics_api -q
bash scripts/verify.sh lint
bash scripts/verify.sh docs
# web/ 下
npm test -- --run
npm run build
FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:5189 npx playwright test e2e/cost-source-allocation.spec.ts e2e/cost-statistics-flow.spec.ts e2e/cost-statistics-relation-fanout.spec.ts --project=chromium
```

结果：104后端（含11真实PG）、1293前端、23发布构建浏览器测试通过；类别1/2/3/5/6/7覆盖，第4类无对应生命周期改动。生产性能、网络中断样本及未覆盖风险见实施记录修复版发布段。
