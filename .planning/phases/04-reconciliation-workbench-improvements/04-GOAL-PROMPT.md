---
phase: 04-reconciliation-workbench-improvements
status: master_goal_prompt
created: 2026-07-16
source_plan: .planning/phases/04-reconciliation-workbench-improvements/04-PLAN.md
---

# 关联台高性能链路主控 `/goal` Prompt

把下面整个代码块作为**唯一一份主控 prompt** 喂给 Codex `/goal`。主控必须自己维护状态，一次只生成并立即执行一个 bounded execution prompt；不得预先生成 prompt backlog，也不得为每轮创建新的 prompt 文件。

```text
/goal

在 /Users/yu/Desktop/fin-ops-platform 完全闭环“关联台高性能查询链路与旧链清理”的实施工作。

本 goal 的完成边界是 implementation-verified、deployment_status: deferred_by_user：代码、测试、文档、旧链删除证明、受控环境 correctness/EXPLAIN/性能回归和统一发布交接全部完成；禁止部署、生产 canary 和生产性能验证。所有其他 thread 完成并汇总后，用户会另行统一部署和做最终生产性能验收。

一、权威上下文与固定决策

严格遵守当前磁盘上的：
- /Users/yu/Desktop/fin-ops-platform/AGENTS.md 及所有受影响目录的嵌套 AGENTS.md。
- /Users/yu/Desktop/fin-ops-platform/.planning/phases/04-reconciliation-workbench-improvements/04-PLAN.md。
- README.md、ARCHITECTURE.md、docs/index.md、docs/app-architecture/README.md、docs/modules/README.md。
- docs/architecture/module-boundaries/README.md、inventory.md、read-model-contracts.md。
- 每个直接或上下游受影响模块的 docs/modules/<module>/README.md 与 boundary-io.md。
- 涉及 read model/worker 时，必须读取 docs/modules/read-models/boundary-io.md、docs/modules/runtime-workers/boundary-io.md 和 docs/operations/runtime-worker-governance.md。

04-PLAN.md 是本 goal 的实施合同。若代码事实与计划描述冲突，先以 CodeGraph/源代码/测试/当前长期文档核实，更新计划中的错误事实后再继续；不得默默猜字段、调用方、API shape、队列状态或数据库结构。

以下设计决策已经完成三轮 Grill Me 复审，未经用户重新确认不得扩张：
- 复用现有 active month generation；不新增 Query Projection、projection table、generation 类型、dirty scope、worker、事件或第二事实源。
- month=all 只组合 active month generations，并在分页前使用唯一 canonical-owner 语义；不物化 all generation。
- 初始页只保留一条链：Workbench route -> WorkbenchQueryFacade -> PostgresReadModelRepository -> active month generations。
- 一个 GET /api/workbench 在一个 REPEATABLE READ READ ONLY 快照中返回轻量 freshness/version、summary、OA status、invoice inventory 和 paired/unpaired 各首 200 groups；后续分页与 detail 保持窄接口。
- Redis 只缓存 fresh/stable gate 后的默认首屏 payload；Redis 失败回到同一 cold path，不触发 refresh，不引入 warmer、任意查询缓存或 single-flight。
- refreshing 可以展示上一版 stable generation，但必须显式标记、前后端同时禁写，并在新 generation 激活后自动原子替换。
- 所有 Workbench action 携带 expected_read_model_version，由 Workbench action API 服务端 fail closed；不得污染共享 relation command 的其他页面入口。
- 删除旧 full-payload、旧 row-detail fallback、伪 workbench-aggregate lane、cache warmer 及它们在运行代码、依赖组装、部署、测试和当前事实文档中的残留。
- 为删除旧 full-payload 所做的跨模块修改只允许把 Search、Batch Accounting、settings/reset、imports、write path、ops probes 等迁移到已有或最窄的明确 I/O；禁止改变其他页面 read model、DTO、scope、事实源或业务行为。
- 不新增依赖、通用 factory/adapter/port 层、专属连接池、read replica、keyset、虚拟列表、永久 feature flag 或 schema migration，除非当前计划的量化升级门被证据触发并先取得用户明确同意。

二、不可违反的工作区与生产安全线

当前 worktree 同时有其他 thread 工作。你是本 goal 的唯一写入主控：
- 每一轮分析、编辑和验证前先运行 git status --short，记录本 goal 开始时已有的 dirty/untracked 文件。
- 只修改当前 bounded prompt 明确列出的任务文件；保留用户和其他 thread 的修改，不覆盖、不删除、不格式化无关文件。
- 如果目标文件已有别人的改动，做最小兼容编辑并逐块复核 diff；无法安全区分所有权时，停止该文件并报告精确冲突，不得 checkout/reset/stash。
- 禁止 git add、git commit、git push、merge、rebase、创建/切换 release branch 或把其他 thread 变更打包。
- 禁止 ./scripts/deploy-oa.sh、生产部署、生产写操作、生产 performance smoke、生产 admin token、queue drain、worker stop/disable 和 release 创建。
- 不得因为部署被用户延后而把本 goal 标为 BLOCKED；满足实施完成定义后标记 DONE，并报告 deployment_status: deferred_by_user。
- 不得把本地/隔离环境测量表述为 production-passed。

三、架构与实现约束

- 先用 CodeGraph 回答符号定义、caller/callee、trace、impact 等结构问题；用 rg 做字面量、配置、env、route、测试和文档的 whole-repo scan。
- server.py 只保留 route 注册、依赖组装和 HTTP 映射；业务编排进入 service/facade，SQL 和表结构只在 repository。
- service 构造函数接收明确依赖，不接收整个 Application；service 不读 cookie/header、不 import app.auth、不构造 HTTP response。
- worker 不依赖 Application、route、auth 或 HTTP 对象。Workbench 保持 active generation 原子发布模型，不机械套普通 projection/read-model gateway。
- Workbench transaction-local statement_timeout 只能作用于该只读 transaction；不得修改全局连接或其他页面 timeout。
- canonical-owner 规则只能有一个 SQL/semantic owner；summary、paired、unpaired、分页和 detail 必须由相同规则验证，不能复制一份近似逻辑。
- 旧模块必须在实际调用方迁移并有测试保护后删除；不保留 hidden fallback、fail-open、兼容分支、双 payload owner 或重复实现。
- 任何行为变化都按 AGENTS.md 评估七类测试。失败路径、权限、fresh/stale/refreshing、版本冲突、Redis failure、timeout、并发切换和其他页面回归不能只靠 happy path。
- 只更新事实发生变化的长期文档；原始 prompt 只保留在 .planning，不写入 docs。历史 implementation notes/state logs 不改写，但零引用 guard 应排除明确历史归档。
- 不以提高 timeout、减少正确数据、跳过 freshness、缓存任意搜索结果或预热环境来制造性能达标。

四、主控状态

持续维护以下状态；上下文压缩后从当前磁盘和最近验证结果恢复，不从头重复已经证明完成的工作：
- objective 与当前实施阶段。
- 已确认事实、假设和权威来源。
- 直接/上下游受影响模块及其输入 I/O、输出 I/O、依赖方向。
- 旧入口、调用方、route、API client、service、repository、worker、read model、cache、deploy/env、tests、docs 的迁移/删除矩阵。
- 本 goal 已修改文件；goal 开始前已有的其他 dirty 文件。
- 已新增/修改测试及七类测试覆盖判断。
- 已运行验证、结果、性能样本和仍未验证风险。
- 下一项最高风险缺口。

如需跨多轮持久化状态，最多维护一个 .planning/phases/04-reconciliation-workbench-improvements/04-EXECUTION.md；不要创建每轮 prompt 文件、临时报告目录或重复计划。

五、闭环循环

循环执行，直到 DONE 或真正 BLOCKED：

1. ANALYZE
   - 读取当前 worktree、04-PLAN.md、本轮受影响模块边界、代码、测试和上一轮真实结果。
   - 对本轮相关符号做 CodeGraph context/trace/impact；对旧类名、route、env、worker、scripts、tests、docs 做必要的 whole-repo scan。
   - 识别当前最高风险且可独立验证的一项缺口。不要按预设 backlog 机械推进。
   - 先判断是否能通过删除/复用现有边界解决；没有具体当前问题时不得新增抽象。

2. GENERATE EXACTLY ONE BOUNDED EXECUTION PROMPT
   - 只生成下一项工作的一个 prompt，并立即执行；不要同时生成未来 prompts。
   - prompt 必须写明：本轮目标、已知证据、必读文件、允许修改的模块/文件、禁止事项、预期删除/迁移、适用测试、验证命令、diff 审查点和停止条件。
   - 单轮范围要小到能够完成实现、测试、文档影响判断和验证；不要把多个高风险模块混成一次大改。

3. EXECUTE
   - 按 prompt 完成生产级实现，不只写计划或最小 demo。
   - 优先复用和删除；只有当前明确缺口才新增代码。
   - 同步更新适用测试和长期文档，删除被替代的旧代码、wiring、配置和测试。
   - 先跑最窄的验证，再按风险扩大。不得隐藏失败、跳过 cleanup、放松断言或用兼容 fallback 让测试表面通过。

4. REVIEW
   - 检查完整 diff 与 git status，确认没有碰其他 thread 文件。
   - 检查模块边界/I-O、事实源、freshness/version、缓存、transaction、错误映射、权限、安全和资源上限。
   - 检查旧链是否仍被任何运行代码、构造 wiring、worker/registry、env/deploy、script、test 或当前事实文档引用。
   - 检查其他页面是否仍错误依赖 Workbench full payload，或者本轮反向污染了它们的 read model/DTO/scope。
   - 检查测试是否覆盖本轮适用的七类类别；对不适用类别记录理由。
   - 验证失败时先定位根因；修复仍属于本轮边界则继续，否则把新事实送入下一轮决策。

5. DECIDE
   - DONE：仅当第七节“实施闭环完成证据”全部满足，且没有未完成的本地实现/测试/文档/旧链删除工作。输出 deployment_status: deferred_by_user，不执行第八节发布步骤。
   - BLOCKED：仅当必要合同无法从代码/文档/测试发现、目标文件与其他 thread 修改无法安全合并，或继续需要用户新增授权/超出计划的架构决策。必须给出阻塞证据、已尝试路径和解除阻塞所需的最小输入。
   - CONTINUE：从本轮实际结果重新选择最高风险缺口，生成并执行下一个唯一 bounded prompt。

建议风险顺序仅用于选择，不是强制 backlog：
1. 当前事实、受影响模块/边界、调用方和受控性能基线。
2. repository canonical-owner cold path 与同快照首屏查询。
3. query facade、HTTP 合同、缓存/version/freshness/action precondition。
4. 前端单请求、跨版本原子清理、refreshing 禁写与 imports 解耦。
5. Search/Batch Accounting/settings/write/ops 等窄 I/O 迁移。
6. legacy full payload、row-detail fallback、aggregate lane、warmer 全量删除。
7. 七类测试、E2E、架构 guard、长期文档、受控性能回归和统一发布交接。

六、性能与简洁性门禁

- 当前受控验证使用相同数据集/负载给出 before/after：样本数、p50/p95/p99、DB statement 数、rows scanned/returned、buffers、payload bytes、浏览器 parse/commit/layout。
- 必须验证 cold、hot、Redis unavailable、refreshing、generation switch、搜索/筛选/分页/detail、write-to-fresh 和混合负载；验证其他页面输出/状态合同不变，并尽可能证明 p95 无超过 5% 回归。
- 第 8 节 SLO 是最终生产门槛。本 goal 要求受控环境达到同一目标或给出可复现的环境差异和 query-plan 证据；不能因此自行引入 projection。
- 如果 query rewrite 后 cold p95 仍超标，先用 EXPLAIN 指向具体表达式/连接；只有证据满足 04-PLAN.md 的升级门，才停下向用户提出一个 Workbench-only index。不得直接实现未批准索引、projection 或新基础设施。
- 最终运行模型必须保持：一个既有 generation 事实源、一个 repository SQL owner、一个 query facade、一个首屏 API、一个可丢弃缓存、一个现有 Workbench worker lane。新增层级或 owner 即视为设计回归。

七、实施闭环完成证据

DONE 前逐项用文件、测试或命令结果证明：
- 首屏 summary、paired、unpaired 来自同一个 PostgreSQL 只读快照、相同 generation-set token 和唯一 canonical-owner 规则。
- initial、pagination、search/filter、group detail、row detail 全链 expected version 固定；不同 version 不混合 selection/detail/pagination。
- refreshing 展示旧 stable generation 时 UI 明示且前后端禁写；新 generation 激活后自动替换。
- Workbench relation/override/exception action 缺 version、冲突或 non-fresh 时服务端 fail closed；其他页面共享 command 行为不变。
- Redis hit/miss/down 的 DTO 等价；缓存仅覆盖默认首屏，不是事实源，不存在 warmer。
- ImportWorkflowPage 只消费既有 operation barrier targets，不以 GET Workbench 页面猜刷新完成。
- Search、Batch Accounting、settings reset、write facade、ignored rows、ops scripts/probes 已迁移到计划规定的最窄 I/O，输出合同有 regression 保护。
- legacy provider/API assembler/raw assembler/on-demand full build/generic fallback/row-detail fallback/workbench-aggregate/warmer 的运行代码、wiring、registry、env/deploy、测试和当前事实文档引用为零；历史归档被明确排除。
- main Workbench worker 可处理 ordinary all fan-out；month generation 原子发布和 cost-statistics 既有 fan-out 未被破坏。
- 七类适用测试、Workbench 定向 backend/frontend/E2E、架构/零引用 guard、lint 和 docs 验证通过；全量验证已尝试，失败均有可归属证据和处理结论。
- 受控性能报告包含 before/after 与资源证据；不能只给主观“更快”。
- docs/modules、module boundaries、app architecture、API、operations/deploy 当前事实与实现一致。
- final diff 只含本 goal 的文件，没有暂存/提交/覆盖其他 thread 改动。
- 统一发布交接明确列出 external consumer access-log 门、合并后复验、备份、old all-lane drain、release bundle、deploy-oa、canary、生产 SLO/隔离性矩阵、监控和回滚；这些项目全部标记 deferred，未执行。

八、本 goal 禁止执行的后续发布闭环

下列步骤只能在用户确认所有 thread 已完成并授权统一发布后执行；本 goal 只准备交接：
- 汇总最终 release candidate，处理跨-thread 冲突并复跑全部验证。
- 核查至少 35 天生产 access log，迁移任何外部旧 API consumer。
- 备份；短暂静默旧 aggregate producer；用旧 release/既有 queue ops 将 all-lane pending/processing/failed 收敛并 drain 到零。
- 使用 ./scripts/deploy-oa.sh 发布完整 frontend/backend/worker registry bundle。
- canary 后运行完整生产 cold/hot/write-to-fresh/浏览器/隔离性能矩阵；观察 timeout、DB、Redis、worker、409/503、payload 和其他页面 p95。
- 演练完整应用 bundle 回滚。禁止以恢复 hidden legacy path 作为新 release fallback。

九、首个 bounded execution prompt

先生成并立即执行这一轮，不做代码修改：
“建立 Phase 04 执行基线。读取 04-PLAN.md、仓库/模块边界/read-model/worker 权威文档；记录当前 git status 中所有既有 dirty 文件；使用 CodeGraph 和 rg 全量核对 Workbench 初始读取、active generation、canonical owner、row detail、actions、Search/Batch Accounting/settings/imports/ops 调用方、aggregate lane、warmer、部署配置、测试和文档。核对计划中的每个待删符号与迁移 owner，识别任何与当前代码不符的事实；在本地或隔离环境可用时记录现有慢路径 correctness/EXPLAIN/性能基线，但不得访问生产或加载生产 token。停止条件：形成可验证的影响/迁移矩阵、已存在用户改动清单、基线证据、计划偏差和下一项最高风险缺口；若计划事实有误，先最小更新 04-PLAN.md。完成后根据实际结果生成并执行下一个唯一 bounded prompt。”

十、最终报告格式

- Result：implementation-verified / BLOCKED。
- deployment_status：必须为 deferred_by_user。
- 设计结果：最终运行链和为什么没有引入 projection/额外层。
- Files changed：仅本 goal 文件，并区分新增/修改/删除。
- Old-chain removal proof：零引用扫描与保留的历史归档范围。
- Tests added or changed：逐项说明。
- Seven test categories：适用覆盖；不适用项及理由。
- Verification commands and results：包含失败及归属，不得省略。
- Performance evidence：受控 before/after、query plan、payload/browser 和不能外推到生产的限制。
- Docs impact：更新的长期事实源。
- Worktree isolation：证明其他 thread 文件未被覆盖、暂存或提交。
- Deferred unified-release checklist：external consumers、合并后复验、备份、queue drain、deploy、canary、生产性能/隔离性、监控、回滚。
- Remaining risk：只允许明确的生产发布/运行时验证风险；若仍有本地实现缺口则不得 DONE。
```
