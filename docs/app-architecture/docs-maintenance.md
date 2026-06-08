# 文档维护规则

本仓库文档按“当前事实源短、专题文档深、历史过程不保留”为原则维护。

## 当前事实源

| 主题 | 优先文档 |
| --- | --- |
| 项目入口 | `README.md`、`AGENTS.md`、`docs/index.md` |
| 当前 app 架构和运行链 | `docs/app-architecture/` |
| 页面和关键功能域维护入口 | `docs/modules/` |
| 长期系统边界 | `ARCHITECTURE.md`、`docs/architecture/` |
| 后端重构计划 | `docs/architecture/backend-refactor/` |
| 产品和业务口径 | `docs/product-specs/` |
| API、测试、本地开发 | `docs/dev/` |
| 部署、监控、恢复、worker/read model 运维 | `docs/operations/` |
| 外部系统和原始业务源 | `docs/references/` |

## 删除和归档规则

- 不再新建过程性 prompt/spec/plan 堆积目录。
- 不再把 Codex prompt、subagent prompt、阶段执行计划放入主文档树。
- `docs/modules/*/implementation-notes.md` 只能记录提炼后的目标、决策、验收、风险和后续事项，不能保存原始 prompt。
- 已完成的阶段文档如果没有当前运维或架构价值，直接删除；有价值的结论提炼到 `docs/app-architecture/`、`docs/dev/`、`docs/operations/` 或 `docs/references/`。
- 原始业务需求只保留少量源文档，并明确“不作为当前验收标准”。
- 与当前代码冲突的历史文档不得保留为链接入口。

## 更新触发器

发生以下变化时先做 docs impact assessment；判断影响长期事实源时，同步更新对应文档：

| 变化 | 同步文档 |
| --- | --- |
| 新增/删除页面、路由、侧边栏入口 | `pages.md`、`docs/modules/README.md`、目标模块 `README.md`、`docs/dev/api-contracts.md` |
| 新增 API contract 或 DTO shape | 目标模块 `README.md` 或 `implementation-notes.md`、`docs/dev/api-contracts.md` |
| 新增前端 domain event | 目标模块 `README.md`、`pages.md` |
| 新增 derived lifecycle 事件或 domain | 目标模块 `README.md`、`runtime-and-ownership.md`、`pages.md` |
| 新增 read model 或 worker | 目标模块 `README.md`、`runtime-and-ownership.md`、`docs/operations/runtime-worker-governance.md` |
| 改 PostgreSQL runtime/queue/Redis/RabbitMQ 边界 | 目标资源模块、`runtime-and-ownership.md`、`docs/operations/postgresql-runtime.md` |
| 改业务规则、状态、验收口径 | 目标模块 `state-machine.md`、`docs/product-specs/` |

## 模块文档读取规则

- 每次修改或新增功能前，先从 `docs/modules/README.md` 定位目标页面或关键功能域。
- 读取目标模块 `README.md`，再按影响范围读取 `state-machine.md`、`tests.md`、`implementation-notes.md` 和模块链接的长期事实源。
- 如果一个改动跨多个页面或资源域，读取每个受影响模块；不要只读当前页面。
- 修改完成后，更新发生事实变化的模块文档；没有事实变化时，在最终说明中写明 `docs 不适用` 或 `模块文档无需更新`。

## 核心设计原则

- 业务事实优先：影响核销、台账、权限、导出、搜索、审计的状态必须有后端结构化模型。
- 预览先于写入：导入、数据重置、批量提交、自动匹配等高影响动作必须先展示影响范围，再执行确认。
- 写模型和读模型分离：确认关联、撤回、异常处理等写操作只改变最小事实；列表、搜索、导出优先消费物化读模型。
- OA 是外部事实源：OA Mongo 只读接入，app 可以建立映射、缓存和投影，但不能写 OA 原始库。
- 可追溯比“看起来完成”更重要：每个财务闭环都要能回答数据来源、处理人、处理原因、影响对象、撤回和恢复方式。
