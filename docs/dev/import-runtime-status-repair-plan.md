# 导入运行状态与恢复闭环修复计划

日期：2026-09-22
状态：代码已实施；本地验证与正式发布证据见第 9 节。

## 1. 目标与事实

生产只读检查在 2026-09-22 11:25—11:27 显示：运行摘要 pending=0、processing=0、failed=1、backlog=1；四个必需 worker 空闲且心跳有效。银行与发票导入审计均为 pass/drained。发票审计存在两条确认前复核拒绝的历史警告，聚合摘要未提供未确认失败记录的 ID，尚不能把其中一条直接等同于摘要中的 failed=1。

当前缺陷：

1. `AppStatusOverviewService` 把 failed 和任务存在统一解释为 busy/refreshing。
2. `file_import.confirm` 同时登记在银行、发票两个域；监控按 import_type 聚合，丢失业务归属。
3. 监控先合并不同状态计数、再取最严重状态，混合任务可能被全部统计为失败。
4. App Health 使用旧 BackgroundJob 任务读取，新任务接口使用 `job.import_jobs`；Dashboard 通用 outbox 统计又遗漏直接导入任务，入口口径不一致。
5. 前端 App Status task 状态白名单不接纳 awaiting_confirmation；接入新任务前必须同步 DTO。
6. 导入 worker 没有显式处理继承 BaseException 的 RuntimeWorkerTaskTimeout。
7. failed 的操作指引笼统允许原意图重试；确认前需复核的业务拒绝应回到预览，而非循环提交。

目标：真实状态、精确归属、可诊断可处理、处理后收敛、有限自动恢复、无重复业务写入。

不承诺任何故障永不发生；承诺经测试覆盖的故障按明确规则收敛，无法恢复时准确呈现原因。

## 2. 范围与模块 I/O

| Owner | 输入 | 输出及约束 |
| --- | --- | --- |
| ImportJobRepository / ImportWorkflowService | durable job、已登记 session/file 归属、当前用户、显式操作 | canonical task 状态、任务 DTO、现有确认/重新预览/重试/取消/确认提示命令；SQL 只在 repository |
| RuntimeMonitoringRepository | import jobs、通用 outbox、当前 worker registry/heartbeat | 分来源、分业务域、分状态的有界统计；不产生修复写入 |
| AppStatusOverviewService | 聚合统计、授权任务摘要、依赖健康 | 域状态、整体原因、运行计数；不执行 SQL 或导入命令 |
| App Health / background routes | 已认证身份和显式请求 | DTO、权限与 HTTP 映射；不在 server.py 增加状态业务规则 |
| Shell / App Health / import progress | 明确状态 DTO | 文案、链接、任务操作反馈；不从当前页面 loading 推导全局状态 |
| Import worker | 同一 durable job 与领取凭证 | 事务结果、续租、有限重试、终态；不依赖 HTTP 或 Application |

直接影响模块：app-health-operations、imports-bank-transactions、imports-invoices、runtime-workers、app-shell-navigation。
共享导入合同回归范围：imports-etc-invoices、税务已认证导入、设置 OA 手动导入。修改它们的共享合同前读取对应 boundary-io；现金不得进入全局状态业务数据。
不增加 worker、队列表、read model、缓存平台、依赖库或周期性全量审计。

## 3. 状态和统计合同

| durable 状态 | 展示 | 是否执行中 | 操作原则 |
| --- | --- | --- | --- |
| pending | 排队中；有延迟重试时说明等待重试 | 否，属于待执行任务 | 保留原任务和意图 |
| processing | 解析中 / 导入中 | 是 | 正常等待；按现有权限取消 |
| awaiting_confirmation | 等待确认 | 否 | 查看预览并显式确认 |
| needs_review | 待复核 | 否 | 重新预览、修正、再次确认 |
| failed | 失败待处理 | 否 | 依据明确原因给出重试、重新预览或修正指引 |
| succeeded | 已完成；部分成功保留原 outcome | 否 | 查看结果；仅处理失败部分 |
| canceled | 已取消 | 否 | 不自动重新激活 |

- 保留已有三级 level 及写入权限语义，不因业务失败新增全站门禁。
- 导入域使用精确 status/reason；黄灯整体徽标采用“需关注”，不再把所有 busy 翻译为“同步中”。真正执行中的信息由原因和计数表达。
- 每个域保留混合状态计数；存在失败和运行任务时，两类均可见，不能由单一代表状态掩盖另一类。
- pending、processing、failed、awaiting_confirmation、needs_review 分别计数；兼容保留的 backlog 定义为 pending+processing，UI 分别显示排队、执行、待处理，禁止相加展示成重复总数。
- 失败/已完成记录的 acknowledged_at 只控制提醒；确认提示不改写成功或失败事实，不删除历史。
- 原始状态 needs_review 在任务 DTO 中明确保留，所有客户端白名单、提示和操作同步更新；不能用缺省值伪装正常。
- 未知状态、未知归属明确报告，不猜成发票、银行或成功。未知归属只影响导入诊断，不广播污染所有页面。

## 4. 顺序实施

### A. 先补最小复现测试和归属事实

1. whole-repo 扫描 file_import、file_import.confirm、旧 BackgroundJob 导入消费者、DTO 白名单和统计字段；核对入口、调用方、测试和文档。
2. 验证任务 payload.route、session/file 类型和显式 affected_domains 的现有来源，覆盖银行上传、发票上传、人工录入、历史任务和混合会话。
3. 确立一个导入模块拥有的归属解析规则：使用已登记文件类型区分银行/发票，校验新建任务的路由一致性；真实混合任务只列实际涉及域。查询批量读取必要关联，不逐任务查询。
4. 已有 route 只能作为经合同校验的元数据，不能成为缺失事实时的猜测分支。缺失或冲突明确返回待诊断。
5. 先补“一条发票失败不影响银行”“failed 不等于 refreshing”“混合计数精确”的失败用例，再修改实现。

交付：可复现的问题测试、受影响调用清单、单一归属输出。

### B. 收口查询和状态计算

1. RuntimeMonitoringRepository 按来源、真实业务域、状态分组；总数先按唯一 job/event 计算，再派生域计数，混合任务不得重复计入全局总数。
2. 导入概览、任务进度和 Dashboard 统一读取 job.import_jobs；旧 BackgroundJobService 继续服务仍有效的非导入任务。
3. App Health 组装复用导入 service 的任务 DTO/权限规则；避免查询同一批导入任务两次，也不能把受限的任务详情样本当作全量计数。
4. 普通用户只获得现有权限允许的任务详情；全局摘要不泄露文件名、上传人或错误原始业务内容。
5. 管理员 Dashboard 增加 bounded import queue 诊断区，复用既有 GET 和 admin 权限；返回精确总数与有限样本、任务 ID、业务域、状态、阶段、尝试次数、时间、可公开的原因。样本有上限，明确总数与截断，不加载原文件内容。
6. 移除旧“所有任务都 busy”“failed->refreshing”“共享类型广播双页面”“最严重状态承接所有数量”的路径。
7. readiness 仍区分基础设施故障与业务输入失败；不得让用户文件失败阻断全站，也不得隐藏基础设施不可用。

交付：一致的状态/计数与可定位记录；监控 GET 不触发任务重试或业务修复。

### C. 修复任务处理与恢复

1. 确认前需复核的业务拒绝改为明确领域错误，由导入 worker 转入现有 needs_review；保留 error/疑似重复明细，不自动确认。
2. 对该错误同步检查确认入口与后台执行二次检查，防止前端遗漏或确认后的事实变化穿透。
3. retry/confirm 不再把需复核任务直接放回 commit；重新预览后仍由用户确认，维护 preview version 和已选文件范围。
4. 保留瞬时故障的有限重试、指数延迟与现有 max_attempts；未知程序错误不自动无限重跑。
5. 显式捕获 RuntimeWorkerTaskTimeout，通过同一 owner/claim_version 失败写入边界登记原因并执行有限重试；只捕获这一明确控制异常，不泛化捕获所有 BaseException。
6. 保留 lease、取消与完成竞争控制、权限复核、事实与任务成功同事务；不增加第二次成功补写。
7. 重试、重新预览、确认、取消、确认提示分别更新当前任务和摘要；操作响应优先更新局部任务，随后复用既有状态刷新，不新建并行轮询。

交付：业务问题可处理、瞬时问题可恢复、任务恢复不重复入账。

### D. 前端闭环

1. 同步 features/appStatus 的类型与合法状态集合，接纳 awaiting_confirmation、needs_review；未知状态明确报错。
2. AppStatusIndicator 文案按精确状态生成；先判断失败/待确认等状态，再决定是否显示百分比，避免失败仅显示 0%。
3. 导入进度入口复用已有打开预览、重试、取消、确认提示能力；显示真实操作结果与已知失败原因。
4. 管理员诊断样本能定位任务；跨用户详情只通过 admin 只读边界，不扩展普通用户修改别人任务的权限。
5. 现有 owner 操作接口保持授权；跨用户问题展示诊断，不伪造一个实际上无权限操作的按钮。
6. 请求失败或断网保留明确的旧数据/未知提示，恢复后回读；不得将空值视为正常。保持现有五秒有界轮询和去重，不缩短间隔掩盖服务端问题。

交付：从异常提示到任务处理、结果反馈、全局收敛可完整走通。

### E. 历史记录与旧代码清理

1. 通过新增的有界只读诊断精确定位当前未确认失败 ID、实际业务域与 session/file 状态，不从汇总数反推任务 ID。
2. 默认保留历史 failed 事实，发布新状态逻辑后即应从“同步中”变为“失败待处理”。不为变绿批量 acknowledge、删除或修改成功状态。
3. 历史待复核记录通过显式重新预览入口恢复。已终结、已提交或无原件的任务必须明确说明限制；不能无证据自动重新导入。
4. 旧格式若有真实在用调用点，迁移调用点后再删除；保留当前共享的有效非导入消费者，不删除整套 BackgroundJobService。
5. 全仓复扫旧导入执行/统计依赖，删除失效注册项、重复 DTO 映射、测试假数据和过期文档。历史审计读取不等同于旧执行路径。

交付：历史异常有解释、有可用下一步，旧逻辑不继续影响当前任务。

## 5. 测试与验证

| 测试类别 | 本次内容 |
| --- | --- |
| 1 业务核心 | 状态分支、混合计数、精确归属、重试分类、未知值 |
| 2 Service | 统一读取、权限过滤、审核/确认/重试、取消与完成竞争、事务回滚 |
| 3 API | 三个状态入口合同、合法/非法状态、权限、版本冲突、错误响应、幂等重复 |
| 4 后台任务/读侧 | 真实 PostgreSQL claim、租约过期、超时、恢复、耗尽、只读统计；无新增 read model 或缓存失效策略 |
| 5 前端 | 待确认/待复核、失败原因、混合状态、打开预览、操作反馈、断网恢复、禁用/权限行为 |
| 6 E2E | 上传→预览→确认→worker提交→页面结果→状态收敛；需复核→重新预览→确认；瞬时失败→恢复→只写一次 |
| 7 回归 | ETC、已认证发票、OA手动导入、匹配/维护队列、现有 shell/权限及现金不进入全局状态 |

主要现有测试入口：

- tests/test_app_status_overview_service.py
- tests/test_runtime_monitoring.py
- tests/test_app_health_api.py、tests/test_app_health_service.py
- tests/test_import_direct_queue_postgres_integration.py
- tests/test_runtime_worker.py、tests/test_audit_invoice_import_page.py
- web/src/test/AppStatusApi.test.ts、AppStatusIndicator.test.tsx
- web/src/test/AppHealthStatusContext.test.tsx、AppHealthOperationsPage.test.tsx
- web/src/test/BackgroundJobProgress.test.tsx、ImportCenterPage.test.tsx
- web/e2e/imports-bank-transactions-flow.spec.ts、imports-invoices-flow.spec.ts、imports-etc-invoices-flow.spec.ts

验证顺序：相关单测/真实 PostgreSQL 集成 → 前端交互/类型构建 → 关键浏览器链路 → 一次相关共享回归。采用既有 scripts/verify.sh lint、backend、frontend、docs；数据库测试只使用已验证可丢弃的专用测试库，不连接生产测试写入。浏览器 mock 验证不替代真实 HTTP+数据库闭环。
不为七类各造一套框架；适用场景加入已有测试文件。缓存/read model 专项不适用，无新增这类设施。

## 6. 性能验收

- 改前改后同账号、相近数据规模和负载，测 App Health、任务摘要、Dashboard 的 p50/p95、SQL 次数、响应体大小。
- 常规状态接口预热后各测 30 次，Dashboard 10 次；异常指标才扩大样本，禁止生产压测或杀 worker 注入故障。
- 设计目标：常规状态接口服务端 p95 不超过 100ms、相近网络下端到端 p95 不超过 300ms；Dashboard 暂定服务端 p95 不超过 500ms。它们是待实测验收目标，不是现有性能声明或永久 SLA。
- 样本超标时分清网络、查询与序列化原因；不得静默放宽目标或缓存假状态。
- 查询数量不随展示任务数线性增长，统计不扫描/反序列化全部历史 payload，不逐任务拉 session/file。
- 任务结束后，健康网络和前台正常轮询条件下，概览按既有一秒状态缓存与五秒轮询收敛，保守观测上界约六秒加请求耗时；明确这是观测延迟，不等于导入耗时。
- 数据库断连恢复上界受 max_attempts、退避、lease 和部署实例配置影响，实施时记录实际参数；不能只报“自动恢复”而不说明耗时。

## 7. 发布、清理与文档

- 本计划不预设新表或数据迁移。既有状态、payload、字段足够时只改代码；若发现必须变更结构，先说明具体证据和影响，不顺手扩展。
- 未来执行获授权后，发布复用 ./scripts/deploy-oa.sh 及其既有检查，不另加 GSD、审批层或全站门禁。
- 生产验收默认只读：核对当前失败归属、零执行不显示同步、三入口计数口径、两页 audit、required worker、API性能和相邻页面 smoke。
- 故障注入、重复确认、租约争抢、超时及恢复写入在隔离环境完成，不能在生产制造假发票或错误银行流水。生产只读验证不宣称等价于生产故障演练。
- 代码发布失败沿用既有版本回退流程；不把恢复旧代码等同于撤销已提交业务事实。
- 本方案默认不创建数据库备份。若最终操作确需备份，登记本任务精确备份路径和清理条件，验证完成后移除本任务备份；绝不删除主数据库或其他备份。
- 更新直接影响模块 boundary-io/tests/implementation-notes，及 platform-settings-health、API合同、runtime-worker-governance 的实际变化；修正文档仍声称只读 outbox 的旧口径。
- 最终交付列出改动、删除旧路径、测试分类/命令、生产证据、性能样本、未验证风险及临时文件/备份清理结果。

## 8. 计划复审

- 模块边界：SQL、业务状态、HTTP、UI、worker 各自归属清晰；无反向依赖。
- 简化：复用同一任务表、现有状态和原 worker，不加通用恢复平台。
- 闭环：计数→归属→详情→操作→任务结果→概览收敛均有责任 owner。
- 性能：有测量方法和目标；五秒 polling 不增频，诊断只给有界样本。
- 清旧：删除旧导入读链与错误分组逻辑，保留非导入服务和审计历史。
- 隔离：导入输入失败不阻断全站，跨用户详情仍受权限控制，现金不进入全局监控业务 DTO。
- 自动恢复：只恢复明确可重试技术故障，不自动确认疑似重复/坏文件，不无限重试。
- 无兜底：未知归属和状态明确报错；重试是已有失败模型的确定行为，不是吞错或伪造成功。
- 数据安全：默认无迁移无备份；任何本任务备份验收后精确清理，主数据库永不删除。
- 局限：不能证明永不出错；当前未确认失败 ID、历史任务可恢复性和性能目标仍须实施时通过精确诊断和实测完成验证。


## 9. 实施记录

- 单一归属 SQL 位于 `services/postgres_repositories/import_job_status.py`，由导入 repository 与监控 repository 复用；监控聚合只选择必要列，任务详情有界读取，未添加 N+1 查询、新表、索引或依赖。
- 旧 BackgroundJob 导入状态消费、共享 `file_import` 广播和 RabbitMQ 前端队列字段已从当前链路移除；有效非导入任务及 ETC 同时关联票据管理的合同保留。
- 确认前复核拒绝改为明确领域错误，worker 进入 `needs_review`。历史失败事实不批改，通过已有重新预览入口恢复；不自动确认业务问题。
- 2026-09-22 只读确认生产 import worker：poll=0.05 秒、lease=300 秒、task timeout=900 秒、SQL timeout=120 秒、max attempts=5。瞬时失败退避为 1/2/4/8 秒（单次延迟上限 60 秒），进程退出按既有 lease 接管；实际完成时间还受任务执行时间及队列负载影响，不能承诺所有故障固定秒数恢复。
- App Status 既有状态缓存默认 1 秒、前台轮询 5 秒；Dashboard 既有缓存默认 30 秒，带 generated_at，不能把三个接口不同时刻的快照误报为同一事务。
- 七类测试均适用，复用现有测试；无新增 read model/cache，因此没有新增缓存失效专项。生产保持只读业务验证，超时、争抢和恢复写入在隔离 PostgreSQL 测试库执行。
- 本次不做数据库结构或业务数据迁移，不创建数据库备份，不删除主数据库。

本地验证结果（2026-09-22）：

- `FIN_OPS_TEST_DATABASE_URL=<隔离库> bash scripts/verify.sh backend`：4,481 项，0 失败；55 项要求现金专用 DSN 的用例由下一条补齐。
- `FIN_OPS_CASH_TEST_DATABASE_URL=<另一隔离库> PYTHONPATH=backend/src python3 -m unittest tests.test_cash_core tests.test_cash_http_integration tests.test_cash_runtime -v`：62 项全部通过，未跳过。
- 最终状态合同、复核和恢复边界复验：app_status_overview/app_health_api/app_health_service/import_direct_queue_postgres_integration/import_file_api/etc_backend/runtime_monitoring/operations_dashboard 八组共 259 项通过。
- `bash scripts/verify.sh frontend`：108 文件、1,465 项通过，production build 通过；最后补充不可用状态后四组组件 31 项和 build 复验通过。
- Playwright 三类导入流程 22 项通过；app-shell 权限与管理员面板 6 项通过。队列列头“失败”被全页错误正则误识别，已精确排除列头并保留真实错误检测。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 通过。
- 正式发布使用 `scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh`；线上证据由其 root-owned release checkpoint 保存，最终交付另报告实际 release、commit、两页 audit 与性能。生产故障注入不在本次验证范围。
