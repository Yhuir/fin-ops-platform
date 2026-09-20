# 成本统计测试矩阵

## 外部往来款主标签相邻（2026-09-20）

- Policy 覆盖付款/收款分离、收款原本在前、已经相邻、单项、无目标标签、空集合、重复读取一致及输入/金额/计数不变。
- API 覆盖主标签顺序、搜索后相邻、付款/收款分别下钻及与时间视图汇总一致；Repository 沿用单快照、批量查询回归，不增加查询。
- 页面组件验证保留服务端顺序、两项独立选择与子标签请求；既有 `cost-statistics-flow.spec.ts` 保护五视图及下钻流程。生产只读验证年月/搜索、真实页面位置、两项下钻及五视图性能。
- 七类中业务、服务、API、前端、跨层流程和回归适用；read model/cache/job 不适用。无数据库写入、迁移、备份或新依赖。

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

## 来源菜单挤压修复（2026-09-10）

- `CostSourceAllocationForm.test.tsx`：已用完提示不可见但选项仍禁用、键盘不能选择、当前选中不禁用、释放金额后可选、同项重复提示保留。
- `cost-source-allocation.spec.ts`：1440/390 宽度下四条长名称、多标签选项自然撑高；断言内容处于选项边界、金额不被名称挤压、行不交叠、菜单滚动及末项可达，无额外详情读取或写入。复用2/100来源行性能样本、保存重读、冲突、失联核实及五视图回归。
- 本次新增类别5前端交互及7回归；类别1运行现有业务规则测试，类别6复用现有浏览器业务流；2/3/4无服务、接口、持久化或后台生命周期变更，不新增对应测试。生产只读验证实际菜单与接口，保存验证使用既有隔离浏览器场景。

## 当前分配对照与金额提示（2026-09-10）

- `CostSourceEvidence.test.ts`：只按现有来源 ID 分组，覆盖一对一、一对多、多对一、多对多连通、重复边、无效/空选择、退款、未分配与原始顺序；不修改输入，不重复事实。
- `CostSourceAllocationForm.test.tsx`：完整闭合显示；未分配或总额相等但逐单元/来源错误隐藏；来源切换保持正式关系对照和合并单元格不变；保存中、冲突、未确认结果、刷新失败提示不显示成功暗示。旧全文查询从双 grid 更新为统一 table。
- `cost-source-allocation.spec.ts`：七笔截图金额逐行对齐、原始流水序号不重编、多对多每笔只出现一次、四背景实测文字对比度、150% 内容缩放和390px窄屏、文字变化时按钮不跳动；既有保存重读、409、失联核实、只读、退款/非成本和2/100行20次交互性能继续执行。
- `FinanceTableMigration.test.ts`：仅登记成本对照表这个需要 rowspan/colspan 的原生表格例外；公共组件与其他消费者的旧检查不变。
- 七类：1复用既有金额规则测试；5/7新增展示分组、组件和浏览器回归；6复用已有保存/重读与关系到成本浏览器链。2/3/4没有服务、HTTP 合同、存储或后台生命周期变化，不新增对应测试。生产浏览器验证只读和未提交草稿，实际保存用隔离浏览器场景验证。

## 抽屉文案精简（2026-09-10）

- `CostSourceAllocationForm.test.tsx`：常驻说明及禁用原因文字不存在；同项重复来源仍真实禁用，键盘不能选入。保留当前来源、释放金额、金额一致和保存反馈回归。
- `cost-source-allocation.spec.ts`：更新加载/空态/冲突/核实/重读按钮文案与多对多短标题；保留保存→重读、409修改保留、响应丢失后GET核实、只读、菜单长文本、四色、窄屏及2/100行交互测量。
- 七类：1复用来源/金额规则；5、7更新组件和浏览器回归；6复用保存和关联业务流。2、3、4无服务、HTTP合同或后台生命周期改动，不新增相关测试。生产仅验证只读事实及未提交的会话修改。

## 2026-09-11 项目成本标签范围

- `tests/test_cost_statistics_project_cost_scope.py`：混合来源、退款、显式未标记、空范围、来源未知、日期为空、身份不变、配置错误及原始流水隔离。
- `tests/test_cost_statistics_source_postgres.py`：真实 PostgreSQL 保存/恢复、同事务审计和回滚、版本冲突/并发、API 400/403/409、窄设置写入、重复迁移、单层内部往来标签输出。
- `CostStatisticsProjectCostScopeDrawer.test.tsx`：标签清单、禁用收入、全取消、搜索、加载/错误、只读和结果待核实。
- `e2e/cost-statistics-project-cost-scope.spec.ts`：按需 GET、草稿无写入、保存后正常读取、宽/窄浏览器截图；原有来源分配、配对对齐及颜色对比回归继续执行。
- 七类适用：1/2/3/5/6/7；4 无新增 read model/cache/job，沿用直接读取不写队列的既有测试。

## 2026-09-11 项目成本紧凑布局

- `web/e2e/cost-statistics-layout.spec.ts`：三个视角，在 1920、1440、1024 和 390px 宽度下验证页面不溢出、完整时间单行、内部滚动与表头、分页可见；银行账户长列表独立滚动，切回银行流水保留原时间 chip。
- 复跑 `CostStatisticsPage.test.tsx` 与 `cost-statistics-flow.spec.ts`，覆盖现有视角、下钻、详情、分页、导出及范围设置读取交互。
- 测试类别 5、7 直接适用；6 通过已有页面→接口模拟→明细/导出交互回归。1、2、3、4 没有新增业务规则、服务、HTTP 合同、缓存或后台任务，因此不新增这些层的测试。
- 发布后用真实浏览器检查三个视角，并核对同口径金额与生产只读 HTTP SLO；不通过保存分配制造生产测试数据。


## 待分配范围闭环回归（2026-09-11）

- 业务核心：`test_cost_statistics_project_cost_scope.py` 覆盖 2100 借出款排除、住宿费保留且不自动确认、范围身份稳定、混合退款不猜测、显式退款份额及输入不变。
- 服务/API/真实 PostgreSQL：`test_cost_statistics_source_postgres.py` 覆盖按来源保留历史、重新勾选恢复、增加来源后已有成本保留、旧范围草稿拒绝、伪造范围外来源拒绝、审计失败事务回滚；原有权限、来源失效、金额和导出测试继续执行。PUT 增加必填 scope_version，旧版本请求不能静默写入。
- 前端：来源草稿核实同时比较范围版本；浏览器 `cost-source-allocation.spec.ts` 验证单笔住宿费的表格/菜单/计数、绿色提示、保存、宽窄屏截图及既有多来源/退款/失效交互。
- E2E：真实 PG 保存后从项目/标签/账户视角核对同一金额；浏览器验证抽屉保存/任务切换。生产验证仅只读，不对用户真实分配做试验性保存。
- 读模型/cache/worker 不适用：本次只修改 canonical 成本读取和事务内分配保存，不新增或修改异步链。其余六类测试覆盖当前受影响业务；银行流水原始收支、关联关系与导出保持回归。


## 正式关系对照与刷新（2026-09-13）

- `test_cost_relation_display.py`：电信重复金额7 OA/14流水、油卡5/5、利息2/16三类历史分组与 Workbench 同源，范围裁剪不重新分组，报销父子共有证据不生成分配，输入不变。
- `test_cost_statistics_source_postgres.py`：真实 PostgreSQL 历史→详情分组→保存→重读→撤回失效完整流；旧任务不可保存。复用权限、409、范围与事务回滚用例。
- `CostSourceEvidence.test.ts`：按正式 ID 分组、稳定排序、共享块、范围排除、未知成员明确失败；删除旧草稿边分组断言。
- `CostSourceAllocationForm.test.tsx`：编辑来源/金额不改上方关系；`CostManualAllocationRefresh.test.tsx`：脏草稿冲突保留、连续刷新不能解锁、显式重读恢复、旧请求不能覆盖新事实、窗口聚焦重读且无 PUT。
- `cost-source-allocation.spec.ts`、`cost-statistics-relation-fanout.spec.ts`：浏览器保存/重读、错误/权限/结果核实、关系刷新、三个成本及原银行视角回归、宽窄屏与交互耗时。
- 七类中的1/2/3/5/6/7适用；4中的前端会话缓存失效和旧响应竞态已覆盖，服务端 read model/queue/worker 不适用（仍直接读取 canonical，不新增后台刷新）。生产只读核对全部待分配正式成员、目标关系分组、浏览器视觉与请求耗时；写入闭环在隔离 PostgreSQL 验证。


## 正式子关系预填回归（2026-09-13）

- `test_cost_relation_display.py`：电信 7 OA/14 流水、重复等额 5 对、利息 2 OA/16 流水完整预填；金额展示不等于来源、旧历史成员不匹配、范围裁剪/引用冲突、多费用项歧义。
- `test_cost_statistics_source_postgres.py`：真实隔离 PostgreSQL + HTTP 的重复金额历史关系→预填零写入→保存/审计→重新读取→三成本视角→撤回后读取和旧提交拒绝；原并发、退款、范围和回滚测试继续运行。
- `cost-source-allocation.spec.ts`：7 组14行预填、无重复、可编辑、金额提示、保存后完成页重读。原刷新保护、权限、错误、保存结果核实、100行交互测量继续覆盖。
- 无新 read model/cache/worker；更新验证由现有 canonical GET、抽屉刷新测试承担。

## 人工补充专项（2026-09-13）

- 核心：`test_cost_statistics_manual_items.py` 覆盖有效/空/重复/非法字段、停用目录只保留原选择。`test_cost_statistics_source_allocation.py` 保护逐来源/退款/OA单元校验。
- 真实 PostgreSQL + HTTP：`test_cost_statistics_source_postgres.py` 的 `manual_cost` 用例覆盖192残差预填、人工保存/重读/修改/删除、三个视图、详情/导出、审计原子失败、CAS重放、403、范围排除/恢复、局部保存保留其它来源人工项、撤回关系，断言OA/银行/关系事实零变化。
- 前端：`CostSourceAllocationForm.test.tsx` 验证选项目/标签/来源、金额绿字、超额撤销绿字、删除释放192余额以及证据区不受编辑影响；API与既有刷新/错误恢复测试更新新字段。
- 浏览器：`cost-source-allocation.spec.ts` 的 manual supplemental 场景验证真实页面新增、保存、已完成重开、1440与1280窗口截图；既有来源分配、成本五视图及关联变动回归继续运行。
- 七类：1、2、3、5、6、7适用；4不适用，成本保持canonical直接读取，无read model/cache/job改变。性能分开报告公网GET与浏览器交互耗时；生产不编造192用途来执行财务保存。

## 人工成本标签二级选择（2026-09-13）

- `test_cost_statistics_manual_items.py`：与银行当前规则同源、排除 legacy/archived、单层标签、斜杠名称、输入不变、目录 API 权限和窄输出。
- `test_cost_statistics_source_postgres.py`：读取后标签停用，新明细保存失败且版本不变；历史保存明细继续回显。既有保存/审计回滚/三视角/导出/权限用例继续保护原链路。
- `CostManualTagPicker.test.tsx`：主子切换、定位、同名子标签按代码选择、单层选择、失败不展示旧选项、重试、禁用。
- `cost-source-allocation.spec.ts`：二级选择后保存重开；目录首次失败→重试取得新标签→选择→再次打开刷新，草稿保持，1280窗口弹层完整可见。
- 七类测试中业务核心、服务、API、前端、端到端和既有回归适用；read model/cache/worker 不适用，没有新增或修改这些链路。

## 混合审批状态回归（2026-09-13）

- Policy/source：单支出共享的已完成部分、等待审批预算、超分/错误来源/进行中成本拒绝，旧 fingerprint 不受展示资格字段影响。
- PostgreSQL + HTTP：admission 事实读取、部分 PUT → 三视图 600 → 审批完成保持 600 → 补分配到 1000 → 审批状态退回到 600 → 撤回关系到 0；CAS 重复保存 409、原审计回滚/并发/范围/导出测试继续执行。
- 组件：未完成行不可编辑、剩余金额不伪报绿色一致、部分请求中等待单元为 0、非成本不能核销等待预算。
- 浏览器：`cost-source-allocation.spec.ts` 的 mixed approval 场景保存 8000、重开抽屉保留、其余 8000 等待；1440×1000 截图肉眼检查。


## 五视角表格样式统一（2026-09-14）

- `CostExplorerList.test.tsx`：计数与双收支完整展示，loading 不冒充 empty，保留键盘选择；重复点击已选项继续进入下一级，分页加载禁用、失败重试和末页边界有明确断言。
- `CostStatisticsPage.test.tsx`：时间视角单表与标签下钻；原有搜索、权限、错误恢复、详情和分页回归。
- `cost-statistics-layout.spec.ts`：三个成本视角和两个流水视角在 1920/1440/1024/390 宽度下的剩余高度、完整日期、表头、分页、独立滚动、长内容、窄屏路径返回，以及离页后银行明细不继承成本高度约束。
- `cost-statistics-flow.spec.ts`：复用五视角下钻、每页20条、分页回顶、详情、导出入口的浏览器流程。
- 七类：5前端交互、7回归有新增/调整，6复用模拟API浏览器流程；1业务核心、2服务、3接口、4后台生命周期无行为变更，不新增对应测试，仍运行现有客户端/金额格式/公共表格测试。
- 性能按相同环境采样交互与请求次数；生产只读核对真实五视角、下钻、分页及接口耗时，不将模拟API耗时当作生产性能。无新性能门禁、数据库备份或数据库修改。


本次本地验证：前端全量103文件/1337测试通过；最终受影响组件18测试、五视角布局/OA嵌入/跨页文本复制8个浏览器测试通过，构建、lint、docs检查通过。后端全量已尝试：3973测试中7个错误因缺少FIN_OPS_TEST_DATABASE_URL，1个既有断言仍固定到0170而实际迁移已有0171，104个按原测试条件跳过；本次没有改后端、迁移或这些测试，没有放宽断言。生产结果在本次发布交付报告中记录。

## 确定来源自动分配回归（2026-09-14）

- `AutomaticFormalSourceTests`：145/204 正式对应、仅金额歧义、重复金额明确引用、冲突、部分来源与固定目标、父 OA 明细歧义、混合审批及输入不变。
- 真实 PostgreSQL：明确引用/正式历史自动读取、GET 零分配与审计写入、三视图无需保存直接计入、首次人工保存/重读与撤回；现有保存/退款/并发/范围/审计回滚继续回归。
- 前端来源草稿：自动行与剩余建议合并，已保存决定不混入建议；浏览器自动任务在已完成展示、打开零 PUT、显式人工保存和重开。
- 七类：1/2/3/5/6/7适用；4中前端旧响应与详情失效沿用既有覆盖，服务端 read model/cache/job 不适用，维持 canonical 直接读取。性能与执行结果见 implementation-notes。


## 项目块展开与收起动画（2026-09-15）

- `CostManualAllocationRefresh.test.tsx`：切换只打开一个任务，晚到响应不重新展开，收起后草稿金额保留，单次展开仅发起一次详情读取且无 PUT；原有刷新/冲突/保存反馈继续回归。金额失焦后按现有两位小数规则核对。
- `cost-source-allocation.spec.ts`：2/100 行的开合中间帧、收起后表单释放、快速反向切换、系统减少动态效果、键盘焦点与首次延迟详情的连续高度变化；复用原有保存、只读、失败、菜单与窄屏用例。
- 七类：新增5前端交互和7既有功能回归；1业务规则、2服务、3API、4后台/cache均无变更，6不新增跨模块流程，复用原有浏览器保存闭环。生产仅打开/收起/切换/查询，不试验性保存真实分配。
- 性能同时记录点击后的第一帧、帧间隔、完成时间与请求数；开发构建和生产构建结果分开，不将并行测试负载下的帧率当作生产结论。

## 2026-09-20 逐笔展示隔离

`test_cost_relation_display.py` 从 Cost 自身 OA projection 构造付款证据，断言两笔等额付款对应正确且不改变原始事实/source_relation_groups；既有成本来源分配、资格与金额测试保护业务口径。
