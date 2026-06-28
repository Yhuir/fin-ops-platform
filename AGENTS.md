# fin-ops-platform Agent 导航

这份文件是本仓库的入口地图。它告诉后续 Agent 先读什么、去哪里找事实、哪些内容只作为历史归档。

## 读文档顺序

1. `README.md`：项目定位、运行入口和文档地图。
2. `ARCHITECTURE.md`：系统边界、模块关系、数据流和演进方向。
3. `docs/index.md`：长期文档索引。
4. `docs/app-architecture/README.md`：当前 app 架构、页面、运行时序和跨页面影响关系。
5. `docs/modules/README.md`：按页面或关键功能域定位模块维护文档。
6. `docs/architecture/module-boundaries/README.md`：模块边界、I/O、文件范围、direct API 目标读路径、legacy read model 合同和 GSD 维护规则。
7. `docs/product-specs/index.md`：按业务专题阅读需求。
8. `docs/dev/index.md`：按开发任务查接口、测试和本地运行说明。
9. `docs/operations/index.md`：部署、数据重置、备份、监控和故障处理。

## 文档事实源

- 产品和业务口径以 `docs/product-specs/` 为准。
- 当前 app 页面、运行时调用链、direct API 目标读路径、legacy read model/worker 和页面间影响关系以 `docs/app-architecture/` 为准。
- 页面或关键功能域的日常维护入口以 `docs/modules/` 为准；模块文档用于定位上下文、状态机、测试矩阵和实施记录，不替代产品、架构、开发或运维长期事实源。
- 模块边界、I/O、文件范围索引、direct API 目标读路径和 legacy read model 下线清单以 `docs/architecture/module-boundaries/` 为准；模块级边界细节以对应 `docs/modules/<module>/boundary-io.md` 为准。
- 系统边界和长期技术决策以 `ARCHITECTURE.md` 和 `docs/architecture/` 为准。
- 运行、测试、接口契约以 `docs/dev/`、`backend/README.md`、`web/README.md` 为准。
- 部署和生产操作以 `docs/operations/` 与 `deploy/oa/README.md` 为准。
- 历史 prompt、旧计划和阶段执行记录不作为当前需求或架构依据；仍有价值的结论应提炼到长期文档。

## 代码变更前的模块边界检查

- 每次修改代码、新增功能、修 Bug、调整 API、改页面、改 read model/worker、改权限、改导入导出、改部署或删除旧代码前，必须先识别直接受影响模块和上下游受影响模块。
- 使用 `docs/architecture/module-boundaries/inventory.md` 定位模块后，必须读取每个受影响模块的 `docs/modules/<module>/boundary-io.md`；不要只读模块 `README.md`。
- 跨模块改动必须读取所有直接模块和上下游模块的 `boundary-io.md`，并明确输入 I/O、输出 I/O、文件范围、依赖方向和旧代码删除条件是否变化。
- 涉及页面读取、列表、统计、搜索、导出、legacy read model 或 worker 时，还必须读取 `docs/architecture/direct-api-read-architecture.md`、`docs/architecture/module-boundaries/read-model-contracts.md`、`docs/modules/read-models/boundary-io.md`、`docs/modules/runtime-workers/boundary-io.md` 和 `docs/operations/runtime-worker-governance.md`。
- 如果改动改变模块职责、输入 I/O、输出 I/O、文件范围、依赖方向、read model scope、worker、API response shape、权限、测试矩阵或旧代码删除条件，必须同步更新对应 `boundary-io.md`。

## 写文档约定

- 文档默认使用中文。
- 每次修改或新增功能前，先识别目标页面/功能域，读取 `docs/architecture/module-boundaries/README.md`、`docs/architecture/module-boundaries/inventory.md`、`docs/modules/README.md`、对应 `docs/modules/<module>/README.md` 和 `docs/modules/<module>/boundary-io.md`；若涉及状态机、API、页面读取、legacy read model、worker、权限、部署或测试，还要读取该模块下的相关维护文档和其链接的长期事实源。
- 每次功能、API、架构、read model/worker、运维、权限审计或数据流相关变更，都必须先做 docs impact assessment。
- 每次修改或新增功能后，若模块事实、状态机、测试矩阵、跨页面影响、实施决策或验证方式发生变化，必须同步维护对应 `docs/modules/<module>/` 文档；如果目标模块目录不存在，先创建模块骨架并在 `docs/modules/README.md` 登记。
- 每次模块边界、I/O、文件范围或 read model 合同变化后，必须同步维护 `docs/architecture/module-boundaries/` 和对应 `docs/modules/<module>/boundary-io.md`。
- 只有影响长期事实源时才更新 docs：业务口径更新 `docs/product-specs/`，页面/API/运行时更新 `docs/app-architecture/` 或 `docs/dev/`，部署/数据安全/worker 更新 `docs/operations/`。
- 纯内部实现、测试修复、无边界变化的小重构可以不改 docs，但最终说明必须写明 `docs 不适用`。
- 长期重构可以维护状态机或 state log，例如 `docs/architecture/backend-refactor/migration-state-log.md`；state log 只记录进度和决策，不替代产品、API、架构或运维事实源。
- 不把新的 Codex prompt 写进主文档树；模块目录中的 `implementation-notes.md` 只记录提炼后的目标、决策、验收和风险，不保存原始 prompt。
- 不在根目录散放临时 Excel、PDF、ZIP、截图或导出物。
- 大文件样例放本地 `fixtures/`，不要让自动化测试依赖真实业务文件。

## 工作约束

- 优先读取现有代码和现有文档，不猜测字段、接口或数据库结构。
- 变更范围保持最小；如果整理范围扩大到重构代码或改变业务口径，先说明并等待确认。
- 大型跨模块、read model/worker、后端边界重构或需要全量定位的任务必须使用 GSD 流程。GSD 过程产物可以留在 `.planning/`，但长期事实必须沉淀到 `docs/`；不要把原始 prompt 写入主文档树。
- 修复旧模块时，优先保持最小变更；但当旧模块职责边界已经错误，且继续补丁会让接口约定、数据流、测试责任或运维边界更分散时，不要在旧模块继续堆砌代码。应先设计符合当前架构方向的中心边界，小步迁移调用点，再删除重复、过期或绕过新边界的旧路径。此类重构必须有测试保护，并且不得扩大到与当前目标无关的业务行为。
- 生产级需求必须同时考虑权限、审计、回滚、数据一致性和验证方式。
- 后端改动必须遵循现有重构方向：`server.py` 只做路由、依赖组装和 HTTP 映射；业务逻辑放入 `services/`；持久化和 SQL 细节放入 repository；后台任务放入 worker/service。
- service 构造函数必须接收明确依赖，例如 repository、queue、store、orchestrator、settings provider；不要把整个 `Application` 传给 service。
- service 不直接读取 HTTP cookie/header，不直接 import `app.auth`，不构造 Flask/HTTP response。
- repository 可以知道 SQL 表结构；业务 service 不应散落 SQL。

## Direct API + Legacy Read Model 治理约束

- Worker 不得依赖 `Application`、`app.server`、`app.auth`、HTTP response 或 HTTP 状态对象。
- 页面读路径目标是 direct API：route -> service -> repository -> PostgreSQL canonical facts / OA SQL projection / import facts。新增页面、列表、统计、搜索或导出时不得新增 read model、freshness gate、read model dirty scope、read model refresh worker 或 operation barrier target。
- Legacy read model 只作为迁移清单存在。修改旧 read model 路径时必须优先制定删除条件；除非是在迁移期间保持生产不退化，否则不要继续优化 PSCIP/readiness/freshness 体系。
- Redis 只能作为 direct API 的可删除短 TTL response cache，不能作为 freshness proof；RabbitMQ 只能作为真实后台任务 wakeup/transport，不能作为页面数据状态事实源。
- 新增 worker 仅限导入、OA 同步、文件迁移、外部系统同步、受控修复等真实异步任务；不得新增页面 read model refresh worker。
- 旧 `workbench` active generation 是下线对象，不是新页面读取模式；迁移时必须以 direct SQL/query service 替代，而不是套成新的 gateway。
- 生产发布入口是 `./scripts/deploy-oa.sh`。发布和运维细节以 `docs/operations/runtime-worker-governance.md` 与 `deploy/oa/README.md` 为准。
