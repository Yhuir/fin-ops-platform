# 模块边界与 I/O 文档入口

本目录是仓库级模块边界、I/O、文件范围和维护规则的长期事实源。它把 `docs/modules/` 的日常模块文档、`docs/app-architecture/` 的运行时事实、后端 read model manifest 和 worker registry 统一到一个可执行的架构入口。

`.planning/` 和 `.planning/refactors/` 只作为 GSD 执行工作区、历史计划和分析参考；其中仍然有效的结论必须提炼到本目录、`docs/modules/`、`docs/app-architecture/`、`docs/dev/` 或 `docs/operations/` 后，才可以作为当前开发依据。

## 使用顺序

处理任何 Bug、新功能、API、read model、worker、权限、导入、页面刷新或模块重构前，按以下顺序读取：

1. `README.md`：确认本文档体系、事实源边界和强制流程。
2. `inventory.md`：定位目标模块、入口文档和文件范围来源。
3. 涉及 PostgreSQL 业务事实写入、读取、迁移、修复或跨模块 owner 判定时读取 `canonical-facts.md`。
4. 目标模块的 `docs/modules/<module>/README.md`。
5. 目标模块的 `state-machine.md`、`tests.md`、`implementation-notes.md`，按影响范围读取。
6. 涉及 read model/worker 时读取 `read-model-contracts.md`、`docs/app-architecture/runtime-and-ownership.md`、`docs/operations/runtime-worker-governance.md`。
7. 涉及接口、本地验证或生产运维时读取 `docs/dev/` 与 `docs/operations/` 中的对应文档。

## 事实源分工

| 事实 | 长期事实源 |
| --- | --- |
| 模块边界、I/O、文件范围索引 | 本目录 + `docs/modules/<module>/README.md` |
| PostgreSQL 业务唯一真相、canonical fact owner 和写入 I/O | `canonical-facts.md` + `docs/modules/canonical-facts/` + 拥有事实的业务模块 `boundary-io.md` |
| 页面、运行链、页面间影响 | `docs/app-architecture/` |
| 产品和业务口径 | `docs/product-specs/` |
| API、测试、本地开发 | `docs/dev/`、`backend/README.md`、`web/README.md` |
| 部署、worker、生产验证 | `docs/operations/`、`deploy/oa/README.md` |
| Read model manifest 合同 | `read-model-contracts.md` + `backend/src/fin_ops_platform/services/read_model_manifest.py` |
| Runtime worker 合同 | `docs/operations/runtime-worker-governance.md` + `backend/src/fin_ops_platform/services/runtime_worker_registry.py` |

如果代码与文档冲突，先以代码和运行时 manifest/registry 为核验依据，再同步修正文档；不能让文档继续陈旧。

## 边界与 I/O 的定义

一个模块的边界必须至少说明：

- 模块负责什么业务能力、页面能力或资源能力。
- 模块不负责什么，哪些逻辑必须通过其他模块的公开接口进入。
- 输入 I/O：HTTP/API 入参、service 方法入参、repository 查询条件、read model scope、worker event、前端页面状态或用户操作。
- 输出 I/O：API 响应、read model payload、domain event、dirty scope、audit record、worker job、页面刷新信号。
- 持久化归属：哪些表、read model、索引、缓存或状态由该模块拥有或投影。
- 依赖方向：允许调用哪些服务、repository、gateway、adapter；禁止绕过哪些边界。
- 文件范围：后端 route/service/repository/worker、前端 page/feature/api/test/e2e、脚本和运维文件。
- 测试与验证入口：七类测试适用性、回归测试、生产验证方式和风险。

`boundary-io-template.md` 是新增或补齐单模块边界文档时的模板。当前所有登记模块都必须维护 `docs/modules/<module>/boundary-io.md`；模块 README 负责入口和快速定位，`boundary-io.md` 负责边界、I/O、文件范围、依赖方向、缺口和旧代码删除条件。

## Read Model 目标态

所有仍登记的 read model 的目标态是 Partitioned + Scoped + Incremental Projection：

- Partitioned：按业务可失效维度分区，常见分区是月份、方向、来源、账号、页面 scope 或父聚合 scope。刷新不得默认重建全量数据，除非 manifest 明确允许 all 作为 fan-out 或父聚合语义。
- Scoped：所有刷新、dirty scope、freshness gate 和查询状态必须有可验证 scope。页面不能读取旧 read model 却伪装 fresh。
- Incremental Projection：普通写操作只提交 canonical facts/version/audit；被访问页面比较 source proof 后只让当前精确 scope 变 dirty，并由 worker 增量重算或重放投影。显式维护/repair 才可主动入队；禁止为单个普通写触发跨页面或无界全量重建。

canonical direct-read 页面不进入 manifest，也不套用 projection freshness 合同。关联台已是
direct canonical consumer；当前 manifest 只保留共享 `workbench_relation`。任何例外必须写入
`read-model-contracts.md`，不能靠口头约定。

## GSD 使用规则

对以下任务必须使用 GSD 流程，并把长期结论沉淀回本目录或对应模块文档：

- 跨页面、跨后端模块、跨 read model/worker 的重构。
- 修改模块边界、I/O、文件范围、状态机、刷新链路或生产验证方式。
- 需要先全量分析再执行的任务。
- 需要可追踪计划、验收标准、风险闭环和多轮验证的任务。

GSD 输出可以保留在 `.planning/`，但 `.planning/` 不是长期事实源。完成后必须把稳定结论更新到 `docs/`，并避免把原始 prompt 放进主文档树。

## 维护清单

每次变更前：

- 定位目标模块和所有受影响模块。
- 阅读本目录、模块 README、相关状态机/测试文档。
- 如果涉及 PostgreSQL canonical facts，核对 `canonical-facts.md` 和事实 owner 模块的 `boundary-io.md`。
- 如果涉及 read model/worker，核对 `read-model-contracts.md`、manifest、registry 和运维文档。
- 明确当前变更是否改变边界、I/O、文件范围、状态机、测试矩阵或生产验证。

每次变更后：

- 更新受影响模块文档。
- 如果新增或移除模块，更新 `inventory.md` 和 `docs/modules/README.md`。
- 如果新增、移除或改变 canonical fact family、owner、允许写入口、跨模块读写路径或旧生产 source-of-truth 删除状态，更新 `canonical-facts.md` 和对应 owner 模块 `boundary-io.md`。
- 如果新增、移除或改变 read model，更新 `read-model-contracts.md`、manifest/registry、测试和运维文档。
- 如果改变模块边界或 I/O，更新对应模块 README 和 `boundary-io.md`。
- 运行相关文档、测试或验证命令，并在最终说明中写清未覆盖风险。
