# 模块边界维护规则

本文件规定后续开发如何保持模块边界、I/O、文件范围和 read model 合同不过期。

## 何时必须更新文档

以下任一变化发生时，必须更新长期文档：

- 新增、删除或移动模块文件。
- 新增、删除或改变 API endpoint、API 响应 shape、前端页面入口。
- 改变 service、repository、gateway、facade、adapter 的职责或依赖方向。
- 新增、删除或改变 PostgreSQL canonical fact 表、owner、写入口、读入口、旧生产 source-of-truth 删除状态或跨模块读写路径。
- 改变 read model scope、dirty scope、outbox event、projection strategy、freshness gate 或 worker。
- 改变业务状态机、非法状态、权限、审计、部署、生产验证或回滚方式。
- 删除旧链路、引入新链路，或改变旧链路的兼容条件。

纯内部实现调整可以不更新长期文档，但最终说明必须写明 `docs 不适用`，并说明没有改变边界、I/O、状态机、API、read model、worker、权限、测试矩阵或生产验证。

## Docs Impact Assessment

每次实现前先回答：

- 目标模块是什么？受影响模块还有哪些？
- 是否改变模块职责、输入、输出、持久化、worker、read model 或 API？
- 是否改变 PostgreSQL canonical facts 的 owner、写入口、读入口、禁止路径、旧生产 source-of-truth 删除状态或 downstream 输出？
- 是否需要更新 `docs/modules/<module>/README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md` 或新增 `boundary-io.md`？
- 是否需要更新 `inventory.md`、`canonical-facts.md` 或 `read-model-contracts.md`？
- 是否需要更新 `docs/app-architecture/`、`docs/dev/` 或 `docs/operations/`？
- 是否有旧代码需要删除或标记删除条件，避免旧链路污染新链路？

## 文件范围维护

每个模块文档的代码入口必须至少覆盖：

- 后端 route/API 文件。
- 后端 service/facade/gateway/orchestrator 文件。
- repository/SQL/read model projection 文件。
- worker/job/runtime registry 文件。
- 前端 page/feature/api 文件。
- tests/e2e 文件。
- scripts/deploy/operations 文件。

如果某层不适用，应写明“不适用原因”，不要留空让后续开发猜测。

## GSD 执行要求

使用 GSD 时：

- `.planning/` 保存计划、阶段记录、执行状态和历史分析。
- `docs/` 保存长期事实、边界合同、验收规则和维护入口。
- 生成的 prompt 不进入主文档树；需要保留的结论必须提炼成架构或模块文档。
- 阶段完成后，必须更新受影响模块文档和本目录相关文件。

适合 GSD 的任务包括：

- read model 全量重构或跨页面刷新链路变更。
- 后端服务边界拆分、旧链路删除、跨模块 API 调整。
- PostgreSQL canonical facts owner 收口、跨模块写入收口、旧事实源 fallback 删除。
- 需要生产 rollout、可控写操作样本、性能验证或回滚方案的任务。
- 需要先全量定位再大规模修改的任务。

## 旧代码清理规则

发现旧代码时不要默认保留，也不要无测试删除。必须先判断：

- 是否还有 route、service、worker、脚本、测试或前端调用。
- 是否仍承担兼容、迁移或生产回滚职责。
- 是否绕过了新的 module boundary、read model freshness gate 或 scope policy。
- 删除后是否有测试覆盖旧行为不再需要，或新链路已经覆盖。

如果旧代码污染新链路，优先迁移调用点到新边界，再删除旧路径。删除条件和验证方式应写入模块 `implementation-notes.md` 或 `boundary-io.md`。

## Canonical Facts 维护规则

修改 PostgreSQL 业务唯一真相时必须同时检查：

- `docs/architecture/module-boundaries/canonical-facts.md` 的 owner matrix。
- 事实 owner 模块 `docs/modules/<owner>/boundary-io.md`。
- 允许写入口、允许读入口、跨模块 adapter/UoW 和 direct SQL 禁止路径。
- 写后 dirty scope、domain event、operation barrier target、audit 和 rollback manifest。
- 是否引入或删除 legacy full snapshot、local pickle、`state:*` JSON、Mongo app snapshot、GridFS fallback 或 direct owner bypass。
- 对应 owner 模块的 service/API/read model/regression tests。

旧生产 source-of-truth 路径默认必须删除。migration、audit、rollback 工具如果暂时保留，必须隔离在生产 API/worker 主链路之外，并且不算 canonical facts closure。

不能只把表登记到 shared repository，却不声明业务 owner 和 I/O 边界。

## Read Model 维护规则

修改 read model 时必须同时检查：

- manifest entry。
- scope policy registry。
- refresh gateway / runtime queue。
- worker registry 和 deployment env/systemd。
- query freshness/status gate。
- API contract tests。
- worker/read model tests。
- 前端 loading/stale/refreshing/fresh 状态。
- 生产 drain、freshness 和性能验证方式。

不能只改 projection SQL 或 service 逻辑而不更新 scope/freshness/worker 合同。
