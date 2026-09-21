# 时间范围默认“全部”实施计划

状态：2026-09-21 已按计划实施并完成独立复审。依据 main `1c15b72bf` 的全量页面审查；不使用 GSD，不新增依赖或流程门禁。本文保留设计与验收合同；生产发布版本及实测证据以交付记录为准。

## 1. 目标和明确排除

普通查询页面每次重新进入时，时间筛选默认全部；界面、首次请求、列表、汇总和导出的实际日期范围一致。用户本次访问主动选择日期后，正常操作保留该选择。

“全部”只取消时间限制，保留权限、业务资格、父对象、搜索和其他非日期筛选。它不表示一次传输全部记录，不表示把缺日期的数据补成今天，也不表示改变审批、匹配、金额或任务身份。

以下保留具体业务期间，不增加“全部历史总览”：税金抵扣计划月、现金月任务所属月、现金个人年度账四个视图的年度、未结/待回款截至日。开票日、实际收付日、任务生效月、OA 导入起始日等录入/配置字段不改变。无时间选择器的页面不新增选择器。

## 2. 进入和保留规则

| 场景 | 时间行为 |
| --- | --- |
| 从其他主页面进入、离开后重进、浏览器路由前进/后退重进 | 普通查询恢复全部 |
| 浏览器整页刷新、新浏览器标签直接打开页面 | 普通查询恢复全部，不恢复旧日期 session |
| 已在当前页面再次点击同一个菜单链接 | 不额外重置、不额外发请求；没有发生页面离开/进入 |
| 现金侧栏切换 section | 新进入 section 的普通查询恢复全部；仅在 cash owner 内实现 |
| 同一主页面/现金 section 内切换视图或 Tab | 本次访问保留各视图选择；新的页面/section 访问初始化全部 |
| 本次访问修改日期、分页、排序、搜索、页面“刷新”、保存后回读 | 使用本次选择 |
| 抽屉开关、窗口 focus/visibility | 不重置；关闭未保存编辑继续遵循既有确认规则 |
| 页面导出窗口 | 继承本次页面的实际时间范围，不另恢复上次导出日期 |
| 业务候选抽屉 | 普通日期初始不限；仍保留所属事项/任务和资格限制，不扩大业务资格 |

原生 BFCache 恢复仍遵循现有无额外业务激活合同，不新增 pageshow/focus 全局监听。普通 SPA 路由返回和真正 reload 单独测试。当前没有普通日期深链合同，本次不新增 URL 优先级体系。

## 3. 覆盖清单

以 `web/src/app/pageRegistry.tsx` 的 19 个注册主路由为清单，不复制新的运行时页面注册表。

| 页面/入口 | 实施内容 |
| --- | --- |
| 关联台已配对、未配对两区 | 各自恢复全部；清理 OA/流水/发票旧 timeFilterByPane 及日期列条件；保留非日期显示偏好；请求仍走现有 workbench query owner |
| 成本统计五视图 | 四份 scope 全部初始化 all；恢复时清除旧年月限制；银行按时间/标签继续共享既有 bankFlowScope，不创建第二份状态 |
| 银行明细 | 本年初始改为全部；清除恢复的日期范围及日期列条件；保留账户、标签等非日期条件 |
| OA 待付款核对 | 维持已有初始全部，补重进/首请求与业务回读回归；不无故改 API |
| 流水规则批量处理 | 本月初始改全部，继续使用已支持的空 month 查询；全部列表中的候选提交仍传候选真实 scope_month |
| 批量账务 | 银行候选及已提交列表支持全部年份；单银行、多 OA 的提交模式保持；真实 bank_year 由后端提供 |
| 销项发票收款情况 | 一起清理恢复的 month、invoiceDateFrom/To、开票日期列过滤条件；不留下隐藏日期限制 |
| 进项发票使用情况 | 清理 query 中可恢复的旧 month、invoiceDateFrom/To 和日期 filters；不为当前没有选择器的页面新增控件 |
| 待找发票 | 主表不增日期控件；候选发票抽屉初始起止为空，回归资格、分页及关联操作 |
| 操作历史、设置 OA 手工搜索 | 维持起止为空；补页面重进回归，不改变 OA 导入截止配置或搜索权限 |
| 现金流水 | 独立历史列表增加全部；父事项/任务嵌入流水保留既有全历史及父对象范围 |
| 现金账目：周转期间明细、有票支付期间台账 | 增加真正全部查询；截至日账表仍为截至今天等明确业务口径 |
| 现金纠错候选流水 | 普通时间筛选初始全部；保留动作资格、目标关系、CAS 与请求限制 |
| 现金月任务关联已录现金 | 保留任务月资格和父对象；不得因全局时间要求误把其它月份不合格流水变成可关联 |
| 成本导出三组时间控件（覆盖四视图） | 支持显式全部，复用后端 month=all；项目导出继承项目页当前范围；按月/年聚合粒度独立保留 |
| 税金抵扣、现金任务、个人年度账 | 明确作为业务期间例外，回归原读取和写入规则 |
| 外部往来款、ETC 管理、系统状态、三个导入页面 | 没有普通时间范围入口；仅检查导航和日期录入不受影响 |

## 4. 架构与 I/O

依赖保持：页面状态 → 模块 API client → route 参数/权限映射 → service 查询规则 → repository SQL → canonical facts。

| 层 | 输入/输出与责任 | 禁止 |
| --- | --- | --- |
| 公共日期控件 | 受控 selection 与 onChange；现有月历光标可仍为当前月 | 控件替页面决定业务范围、改全局 DEFAULT_MONTH |
| 页面 session | 页面提供 initialValue、已有 restore 回调；输出清理日期后的页面状态 | 清空全站 session、恢复旧日期后再用 effect 二次请求 |
| Cash section 容器 | 接收 CashContent 保存的条件快照，在 section 子组件 lazy initializer 中重置普通日期 | 接入全局 PageSessionState、Shell 保存 cash 条件或业务数据 |
| 模块 API client | 把页面全部映射为该 API 正式支持的参数 | 一个全局 all 字符串覆盖所有接口、浏览器全量筛选 |
| Route/service | 校验显式范围；维持现有权限/错误/写入语义 | SQL 写进 route、GET 生成任务或修改匹配 |
| Repository | 同一只读快照筛选、汇总、稳定排序、分页；只 hydration 当前页 | 逐年循环请求、N+1、全历史 payload 聚合到 Python 后分页 |

复用 `PageSessionStateContext` 已有 `restore`，不新增第二套 normalizer 参数或日期状态框架。restore 仅处理已存储状态，无缓存的路径仍须修改 initialValue。页面已有 restore 时组合其解析与日期转换，保留既有 validate；不猜字段、不做旧 schema 兼容转换。纯转换须幂等、不原地修改缓存，不假设 StrictMode 下只调用一次。

日期变化后清理旧页码/游标、与旧范围绑定的选择、行定位和展开上下文；不改变搜索、非日期列筛选、排序、pageSize、列宽等合法偏好。若原来已为全部，不借此无条件清掉其它状态。查询与表格状态分开保存的页面必须在各自已确认调用点协调恢复：validRowIds 不能替代页码重置。只有确需给 useFinanceTableSession 传入页面规则时才窄扩该封装；基础 session provider 不变，不批量升级 session version 丢弃用户偏好。

现有 restoreState 在 setValue 时也会是 restored，不能使用 `restoreState === 'restored'` 的 effect 反复归零。不能给整个 App 添加 location.key 或 generation 重挂载规则。

## 5. 可执行顺序

### A. 明确测试和文档合同

1. 按上表更新受影响模块的 state-machine、tests/e2e-spec；说明哪些是新行为、哪些是明确保留行为。
2. 按已有测试模式准备跨年、空数据、缺日期、旧 session、分页第二页的样例。使用隔离测试数据，不复制真实业务附件到测试。
3. 记录当前同范围查询的请求数和延迟；原默认本月与新全部的数据量不同，不能只比较这两者后宣称算法变慢/变快。

完成条件：清单每一项都有实施或保留理由及验证责任；没有需要实施人员临时决定的“所有日期一律清空”。

### B. 普通页面默认值与 session

修改入口：`ReconciliationWorkbenchPage.tsx`、`CostStatisticsPage.tsx`、`BankDetailsPage.tsx`、`BankFlowRuleBatchPage.tsx`、`InputInvoiceUsagePage.tsx`、`OutputInvoiceCollectionsPage.tsx` 及其已有日期状态工具。

1. 无缓存初始值全部。
2. 页面 owner 通过现有 restore 清除日期相关条件；旧值即便仍存于 session，也不能进入首次请求；沿用现有存储更新周期写回干净状态。
3. 已有日期变更处理同步清理游标、选择和范围绑定的详情；取消或忽略离开/旧范围的迟到响应。
4. 保留页面内部操作的日期选择，不在每次 render、查询成功或业务保存后重置。
5. 关联台同时验证主列表与异常查看入口继承当前范围，不改分组、金额、OA 状态或配对业务。

完成条件：旧 session 进入时 UI 和第一批业务请求均为全部，没有先旧月份后全部的附加查询。

### C. 成本导出闭环

修改入口：`CostStatisticsPage.tsx`、`components/cost-statistics/ExportCenterModal.tsx`、`features/cost-statistics/api.ts`，后端以既有 query service/policy 为验证对象。

1. ExportRangeMode 增加明确 all；打开窗口从当前 scope 构造范围，preview 与 download 复用同一参数构造。
2. all 发送已有 `month=all`，省略起止日期/月；具体年月和自定义区间继续按现有合法合同发送。
3. 删除 all 被转换为 availableYears 首尾区间的路径，删除无年份时回到 DEFAULT_MONTH 的分支。仅用于真实年/月转换的代码可以保留，所有调用方迁移后再删除无消费者 helper。
4. 回归所有五视图的预览、下载、金额、无日期记录及权限；全部空结果必须真实为空，不能回到本月。
5. 保持既有导出行数上限和明确超限反馈，不截断、不临时新建导出 worker。

完成条件：同时间和同其他条件下，表格与导出的业务范围一致；预览和下载一致。

### D. 批量账务全部年份

修改入口：`BatchAccountingPage.tsx`、`features/batchAccounting/api.ts/types.ts`、`routes_batch_accounting.py`、`batch_accounting_service.py`、`postgres_repositories/batch_accounting.py`。

1. GET 显式支持 `bank_year=all`，具体年份仍合法；query 内转换为可空 year，null 表示不附加年份条件。缺失/非法年份不悄悄变成全部。summary.bank_year 在 all 时返回 null，DTO 明确 nullable。
2. 单条 bank DTO 必有 `bank_year: string | null` 字段，来自查询同一个 `_BANK_DATE_SQL` 日期口径。不能从显示 trade_time 截取年份；当前日期优先级存在差异，必须以查询事实为准并覆盖跨年不一致样例。三种 canonical 日期均缺失时返回 null，不能从当前年、OA年份或关系metadata补造；all模式保留满足其它条件的缺日期行，具体年模式自然不包含它。未知日期统一 NULLS LAST，再按稳定ID排序，count与实际显示行一致。
3. POST 仍传一个 bank_row_id、多 OA 与具体 bank_year；后端用同一日期事实核验，all 不能进入写参数、幂等身份或关系 metadata。允许的跨年 OA 不收紧。
4. 标签规则分类、资格、count 与分页在 SQL 中集合执行，复用分类 owner。公共分类 CTE 当前以 ID 数组调用，本次窄扩为接收 repository 构造的受控候选 CTE，先限定精确业务对方、支出、正数、未删除、可选年份；不得接收来自 HTTP 的 SQL 文本。移除“全年候选 JSON 聚合到 Python → 分类后切页”链路，不先取全量 ID；先得到本页 keys，再加载详情。`bank_details_canonical_query.py` 的公共分类 owner 边界和原银行分类调用必须纳入回归。
5. 未提交、已提交、标签规则读取、撤回后回读都核对相同 scope；不只改一个列表入口。保持单快照、原查询次数上限、原权限/CAS/幂等和关系写 owner。
6. 读取资格与提交资格分开：缺日期的未提交行显示“日期未知”，不能勾选提交并提示“缺少银行业务日期，无法提交”；后端仍拒绝伪造具体年份。已提交关系只要仍有有效 canonical 银行成员，在all模式中可见，bank_year可为null；撤回仍凭relation ID、原因、版本和幂等键执行，不新增年份要求。既有撤回影响scope的历史来源不用于填充新bank_year DTO，不借此次日期需求重写该历史处理。
7. 公共分类扩展只改变候选来源接入，不改变规则优先级、标签、账户或往来语义；原ID集合调用继续原意。增加银行明细、关联台分类投影、往来流水选择、流水规则批次的等价回归，并覆盖批量账务新候选CTE输入，避免新增路径改变其它消费者结果。

完成条件：任意年份合格流水可在全部页找到并按真实年份提交；未知日期不隐藏、不补年、不误提交，已提交关系不因日期缺失失去撤回入口；仅当前页 payload 返回服务进程，金额/计数无变化。

### E. 现金普通历史范围

修改入口：`CashPage.tsx`、`components/cash/CashFlows.tsx`、`CashFlowTable.tsx`、`CashBooks.tsx`、`CashFlowCorrections.tsx`、`features/cash/api.ts` 及其类型；后端 cash route/query service 与 `postgres_repositories/cash_queries.py`。

1. 只为 `/flows`、周转 `view=events`、有票支付 `view=period` 增加显式 `time_scope=all`，纠错候选复用 `/flows`。all 不携带 date_from/date_to；与日期混传明确报错。没有 all 时保留现有合法日期区间查询与校验，独立列表漏传全部时间参数仍报错，父对象无日期历史保持原合同。
2. 不全局放开日期验证 helper。余额截至日、年度账、任务月、任务关联资格和写命令仍按原合同。
3. cash all 明确为全部已登记历史至当前上海业务日。现有实际业务日期禁止晚于今天，保留该写入合同；SQL 无日期下界、统一截至今日，响应 period 标明真实截至日。保留现有金额/账户账序/余额公式，不把期初设成 0 或把缺日期设为今天；汇总和 rows 同一快照。显式 all 不能沿用父对象无日期查询按 filtered rows 的 min/max 推导余额期间：搜索旧项目不应把账户余额截止日改旧。账户摘要使用完整账序、账户真实开账覆盖范围和固定截至日，filtered_totals 使用行筛选，两者不混算；未起算/未知覆盖仍明确显示。
4. 利用现有 section 子组件卸载/挂载边界：CashBooks lazy initializer 一次清理所有纳入范围的内部视图日期，CashFlows wrapper 初始化本次入口条件，再传给表格。不能在 CashContent 的 section effect 里重置，也不能在公共 CashFlowTable 每次挂载时重置，否则会先发旧请求或破坏内部 Tab/父对象范围；不给整个 CashContent 加 section key。section 内 Tab 保留本次选择，隐藏视图也不能带入上次 section 访问的旧日期。
5. 明确全历史模式和自定义起止输入的互斥展示，复用既有控件；不增加第二个手写年月组件。
6. 保留 cash 独立 API/DTO、小连接池、no-store、日志脱敏、无普通财务 I/O 边界。
7. 同步处理项目筛选候选 `/project-options`：它不接受新 time_scope，全部模式继续按既有合同传 `date_to=当前上海业务日`，父对象场景继续传明确父对象；不得把清空的主查询日期直接复用给候选接口导致400。前后端使用既有上海业务日口径，接口与页面测试覆盖全历史首屏的主列表和候选请求，不为候选另开新接口或放松验证。

完成条件：跨年普通历史可查，分页/汇总/纠错资格正确；任务身份、年度账、截至日不变；cash 数据不进入全局状态或普通日志。

### F. 清理旧链、回归、性能与文档

1. whole-repo 文本/符号扫描入口、调用方、API、service、repository、测试和文档，确认被替换的分支没有剩余调用。
2. 旧默认和旧恢复断言替换为新行为测试；合法具体年月、业务期间校验和安全边界测试保留。
3. 运行相关测试，再执行发布所需的统一检查；通过后不无理由反复全套重跑。
4. 同步相应模块 boundary-io/state-machine/tests、cash 技术/UI 规格、app-shell 进入规则及成本导出合同。当前已退役 read model 不恢复，不新增 worker/cache/refresh 链。

## 6. 旧代码删除清单

| 要删除/替换的旧逻辑 | 完成证据 |
| --- | --- |
| 普通列表默认本月/本年及恢复旧日期的路径 | 所有入口首请求测试；全量旧 session 样例 |
| 日期已重置但 filters/cursor/selection 仍绑定旧范围 | 列筛选与第二页/选择回归 |
| 成本 all→年份首尾→空年份回本月 | 全部/空/无日期记录预览下载测试；旧调用无残留 |
| 批量账务 GET 只支持具体年份 | all 和具体年 API contract；POST依旧拒绝all |
| 批量候选全量 Python 分页 | SQL分页正确性、结果等价、返回载荷/规模测试 |
| 现金目标普通历史接口强制日期、独立列表本年默认 | 显式all和日期模式各自测试，非目标业务校验保留 |

不得删除：合法年月查询、公共日期格式/日历光标、权限/CAS/幂等、任务月份身份、账表截止日、非日期 session 恢复、历史迁移文件和不受影响业务模块。

## 7. 验证矩阵

| 七类测试 | 本次适用范围 |
| --- | --- |
| 业务核心单测 | 范围归一化、all与日期互斥、非法年月、bank真实年份、cash边界；零/空/缺日期/跨年/重复条件 |
| Service/repository | all/年/月等价、同快照summary与rows、SQL分页、无N+1、批量submit/withdraw既有幂等CAS、cash读零写 |
| API合同 | 新增all输入、nullable summary、真实bank_year、字段错误/权限拒绝/旧具体范围、预览与下载 |
| Read model/cache/background | 不新增或修改后台机制；适用部分为session初始化、请求失效及既有无projection/无GET入队回归；read-model刷新队列测试不适用 |
| 前端交互 | 全部选中、脏session、进/退/整页刷新、现金section、内部Tab保留、空/加载/错误、抽屉与保存后回读、权限 |
| 端到端 | 跨页选择月份→离开→返回→全部→导出；批量全部列表→旧年份单银行提交/撤回；cash全部→跨年页/汇总/纠错资格 |
| 既有功能回归 | 具体月份仍可查、搜索/排序/非日期筛选、页面内刷新、税计划月、现金任务/年度账/截至日、关系和发票链路不改 |

关键已有测试：`PageSessionStateContext.test.tsx`、`useFinanceTableSession.test.tsx`、`BankDetailsPage.test.tsx`、`CostStatisticsPage.test.tsx`、`BatchAccountingPage.test.tsx`、`CashFlows.test.tsx`、`CashBooks.test.tsx`、各受影响页面测试；后端 `test_batch_accounting_api.py`、`test_batch_accounting_postgres_integration.py`、`test_cost_statistics_api.py`、`test_cash_queries.py`、`test_cash_api.py`、`test_cash_http_integration.py`、`test_cash_query_performance.py`。补 restore 回调本身、storage 不可用时既有 memory 路径、无缓存/过期/非法缓存、普通 setValue 不归零的测试；这是既有 session 合同，不新增存储 fallback。

增加一个按明确清单驱动的浏览器“日期进入规则”用例，避免给每页复制完整测试框架；具体业务交互留在各模块既有测试。反向用例必须证明同页刷新/关闭抽屉没有丢掉用户刚选的日期，旧请求迟到不能覆盖新结果。非日期条件仍生效不能被误判为“全部失效”。

批量账务缺日期边界必须覆盖：三日期均空时全部可见、具体年不可见；null年份行不可勾选且伪造年份提交失败；已提交缺日期关系仍可查看和撤回，即使旧metadata带年份也不能填充DTO。此为schema允许边界，尚未查询生产是否实际存在，不把测试样例描述为已确认生产问题。

执行阶段主要命令：

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh frontend
bash scripts/verify.sh backend
bash scripts/verify.sh docs
git diff --check
```

先用 `cd web && npm test -- --run <受影响测试文件>` 和 `PYTHONPATH=backend/src:tests python3 -m unittest <受影响模块> -v` 快速定位，再跑以上发布检查；Playwright 按受影响 spec 和新增导航 spec 执行。数据库集成、写操作、规模 fixture 只在隔离测试库；没有执行的类别必须如实列出，不能用mock代替真实数据库证据。

## 8. 性能与发布闭环

- 复用现有[性能合同](../operations/performance-contract.md)，核心读 API p95≤1000ms、p99≤2000ms、错误0；这是验收目标，不是本轮已测结果。不增加新hash、baseline gate或审批阶段。
- 对比同一数据、同一范围、相同分页与筛选的前后结果。首屏不产生“先旧月份再全部”请求；请求数、返回行数/bytes和SQL次数有界。筛选/聚合仍需数据库读取符合范围的数据，不承诺全历史查询与数据量无关。
- 批量账务优先修正集合筛选和SQL分页；cash保留小池与超时；其它已支持all的接口沿用既有路径。只有查询计划/实际慢查询证明需要时才设计索引，不能预先加缓存、worker或新表。
- 隔离数据覆盖多年度及大于一页；现金复用已有1万/10万行、100次样本、并发1/4性能用例，把目前304天种子扩为多年，覆盖单/多账户、深页、周转和票据。需要EXPLAIN ANALYZE或合成规模数据只在测试库执行。生产仅认证、有界、只读采样，记录样本数、分位耗时和实际数据规模。小样本p99/当前生产规模不能冒充百万级能力。
- 执行发布时，使用已有commit→remote main→`./scripts/deploy-oa.sh`流程；不夹带其它任务未审阅文件、不强推、不绕过现有发布安全检查。
- 发布验证实际release、普通页第一请求、残留session重进、分页/汇总/导出，以及业务期间例外；T0/T+30沿用已有运维检查。普通页面探针不得收集cash业务载荷，cash只用模块已有只读验证路径。
- 新all前后端必须同一release匹配；回退按上一兼容release整体处理，不以失败后查本月隐藏错误。

## 9. 数据与备份

本设计无业务数据修复、无表结构迁移、无新数据库备份，因此不触碰主数据库数据，也不存在计划内备份清理动作。测试使用隔离库。

若正式执行的既有发布流程确实创建本任务临时备份，记录准确位置和用途，在发布验证完成后清理本次临时备份，并核对主数据库仍正常；不通配删除、不清理他人/其他任务的备份、不删除主库。原release代码回退包不是数据库备份，按既有发布策略保留。

## 10. 二次审阅结论

复审已收敛以下缺口：

1. 已有restore能力足够，删除新增全局normalizer/hook方案；无缓存initialValue同样修改。
2. 页面进入与同页操作分开，cash section单独处理，不全局重挂载。
3. 隐藏日期列/旧query字段、分页选择、迟到响应纳入闭环。
4. 导出all必须真实表达，删除回到本月的旧分支。
5. 批量账务必须SQL分页，不能只取消year；单条bank_year由canonical日期返回，不能截显示日期。
6. cash只扩普通历史，不把余额、任务身份、年度账当作可清空日期；修正筛选结果日期不能决定账户余额截止日，显式全部为全部已登记历史至今日。项目候选继续使用现有截至日/父对象合同，不跟随主列表清空参数。
7. 已退役read model不恢复；生产验证为只读，性能证据区分规模和样本限制。
8. 最后一轮复审补齐缺日期bank_year nullable、读取/提交/撤回资格分离及稳定空日期排序；公共分类的其它直接消费者纳入等价回归。没有新增业务数据修复、后台机制或额外审批门禁。

| 用户要求 | 审阅结论 |
| --- | --- |
| 模块化与清晰I/O | 通过：日期默认在页面owner，SQL在repository，写身份不受查询all污染 |
| 简单与完整 | 通过：复用控件/session/查询，补齐读取、汇总、导出、进入/返回和回归，不新增框架 |
| 高性能 | 方案通过：首请求正确、SQL分页、集合聚合；实际耗时须执行测量，不能提前承诺 |
| 清除旧代码 | 通过：列出精确替换链及删除证据，合法业务期间代码不误删 |
| 其他页面正常 | 已定义隔离和回归；无法保证未执行测试时绝对零bug，执行后报告实测和未覆盖项 |
| 指出不合理理念 | 已指出：业务月份不能清空，全部不等于无权限/无分页/零成本，不应每次刷新清选择 |
| 备份与主库安全 | 无计划内备份/数据迁移；若发布创建临时备份则定点清理，主库禁止删除 |
| 禁止兜底 | 通过：非法输入明确错误，不返回本月、空结果或第二条旧路径伪装成功 |

结论：实现沿用以上边界。验收分别记录功能回归、隔离数据库规模测量和生产只读测量，不能把计划审阅或本地测试当作生产性能结果。

## 11. 实施收口

- 初始值与会话恢复分别处理，复用原有 restore；基础 provider、路由生命周期和全局日期常量未改。
- 成本导出删除依赖 availableYears 构造伪全量日期、无年份回到本月的旧路径；预览/下载共用范围参数。
- 批量账务删除 Python 全量 hydration 后分页，候选、计数、排序与分页在同一 SQL snapshot 中完成；银行年份由真实 canonical 日期返回，无日期不猜年。共享分类 owner 只增加内部候选 CTE 入口，保留其余消费者原合同。
- 现金只扩普通历史查询。日期 draft 只持日期，防止覆盖后续项目/状态筛选；已为全部时保留合法页码，真正日期改变才重置。
- 无业务数据迁移、备份或新依赖；测试数据只在本次专用可删除库。
- 全量前端106文件1409项与构建通过。后端4341项运行中的5个测试库名称约束错误已在符合命名要求的专库重跑通过；新增生产只读spec登记后CI清单测试通过。53项需要单独环境的跳过按原测试合同保留，现金性能与真实HTTP另行执行。
- 浏览器smoke共251项：249项首轮通过，旧默认月选择器断言更新后通过；现金浮层稳定性超时独立重跑通过，未放宽断言。后续小范围审阅修正均定向复跑。
- 七类测试：1业务范围/年月资格、2查询服务与真实PG、3API参数/响应、5组件交互、6真实HTTP与浏览器、7旧功能回归适用；4无read model/cache/job生命周期修改，复用现有隔离测试，不新增后台机制。
