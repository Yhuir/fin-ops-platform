# fin-ops-platform Agent 导航

这份文件是本仓库的入口地图。它告诉后续 Agent 先读什么、去哪里找事实、哪些内容只作为历史归档。

## 读文档顺序

1. `README.md`：项目定位、运行入口和文档地图。
2. `ARCHITECTURE.md`：系统边界、模块关系、数据流和演进方向。
3. `docs/index.md`：长期文档索引。
4. `docs/app-architecture/README.md`：当前 app 架构、页面、运行时序和跨页面影响关系。
5. `docs/modules/README.md`：按页面或关键功能域定位模块维护文档。
6. `docs/product-specs/index.md`：按业务专题阅读需求。
7. `docs/dev/index.md`：按开发任务查接口、测试和本地运行说明。
8. `docs/operations/index.md`：部署、数据重置、备份、监控和故障处理。

## 文档事实源

- 产品和业务口径以 `docs/product-specs/` 为准。
- 当前 app 页面、运行时调用链、read model/worker 和页面间影响关系以 `docs/app-architecture/` 为准。
- 页面或关键功能域的日常维护入口以 `docs/modules/` 为准；模块文档用于定位上下文、状态机、测试矩阵和实施记录，不替代产品、架构、开发或运维长期事实源。
- 系统边界和长期技术决策以 `ARCHITECTURE.md` 和 `docs/architecture/` 为准。
- 运行、测试、接口契约以 `docs/dev/`、`backend/README.md`、`web/README.md` 为准。
- 部署和生产操作以 `docs/operations/` 与 `deploy/oa/README.md` 为准。
- 历史 prompt、旧计划和阶段执行记录不作为当前需求或架构依据；仍有价值的结论应提炼到长期文档。

## 写文档约定

- 文档默认使用中文。
- 每次修改或新增功能前，先识别目标页面/功能域，读取 `docs/modules/README.md` 和对应 `docs/modules/<module>/README.md`；若涉及状态机、API、read model、worker、权限、部署或测试，还要读取该模块下的相关维护文档和其链接的长期事实源。
- 每次功能、API、架构、read model/worker、运维、权限审计或数据流相关变更，都必须先做 docs impact assessment。
- 每次修改或新增功能后，若模块事实、状态机、测试矩阵、跨页面影响、实施决策或验证方式发生变化，必须同步维护对应 `docs/modules/<module>/` 文档；如果目标模块目录不存在，先创建模块骨架并在 `docs/modules/README.md` 登记。
- 只有影响长期事实源时才更新 docs：业务口径更新 `docs/product-specs/`，页面/API/运行时更新 `docs/app-architecture/` 或 `docs/dev/`，部署/数据安全/worker 更新 `docs/operations/`。
- 纯内部实现、测试修复、无边界变化的小重构可以不改 docs，但最终说明必须写明 `docs 不适用`。
- 长期重构可以维护状态机或 state log，例如 `docs/architecture/backend-refactor/migration-state-log.md`；state log 只记录进度和决策，不替代产品、API、架构或运维事实源。
- 不把新的 Codex prompt 写进主文档树；模块目录中的 `implementation-notes.md` 只记录提炼后的目标、决策、验收和风险，不保存原始 prompt。
- 不在根目录散放临时 Excel、PDF、ZIP、截图或导出物。
- 大文件样例放本地 `fixtures/`，不要让自动化测试依赖真实业务文件。

## 工作约束

- 优先读取现有代码和现有文档，不猜测字段、接口或数据库结构。
- 变更范围保持最小；如果整理范围扩大到重构代码或改变业务口径，先说明并等待确认。
- 生产级需求必须同时考虑权限、审计、回滚、数据一致性和验证方式。
- 后端改动必须遵循现有重构方向：`server.py` 只做路由、依赖组装和 HTTP 映射；业务逻辑放入 `services/`；持久化和 SQL 细节放入 repository；后台任务放入 worker/service。
- service 构造函数必须接收明确依赖，例如 repository、queue、store、orchestrator、settings provider；不要把整个 `Application` 传给 service。
- service 不直接读取 HTTP cookie/header，不直接 import `app.auth`，不构造 Flask/HTTP response。
- repository 可以知道 SQL 表结构；业务 service 不应散落 SQL。

## Worker + Read Model 治理约束

- Worker 不得依赖 `Application`、`app.server`、`app.auth`、HTTP response 或 HTTP 状态对象。
- Read model 查询必须走 freshness/status/enqueue 边界，不能让页面读旧 read model 却伪装 fresh。
- Read model refresh 的事实源是 PostgreSQL durable queue：`job.outbox_events` 与 `job.read_model_dirty_scopes`。
- 所有 read model refresh 请求必须通过 `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 或事务内 writer；业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
- Redis 只能缓存 fresh gate 之后的 payload；RabbitMQ 只能作为可选 transport/wakeup，不能作为 read model 状态事实源。
- 新增 read model 或 worker 时，必须同步更新 registry、manifest/systemd env、tests、docs。
- `workbench` 保留 active generation 原子发布模型；不要把它机械套成普通 read model gateway。
- 生产发布入口是 `./scripts/deploy-oa.sh`。发布和运维细节以 `docs/operations/runtime-worker-governance.md` 与 `deploy/oa/README.md` 为准。
