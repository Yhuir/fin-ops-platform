# Canonical Facts 模块维护入口

- Module key: `canonical-facts`
- 类型: 资源治理模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/persistence-and-read-models.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/read-models/README.md`
- 受影响业务模块的 `docs/modules/<module>/boundary-io.md`

## 职责定位

本模块不是一个新的运行时代码模块，也不集中拥有所有业务表。它维护业务唯一真相的模块化治理规则：每类 PostgreSQL canonical fact 必须归属一个现有业务模块，写入和读取必须经过该 owner 的公开边界。

`read-models` 只负责 legacy read model 下线清单和 no-restore guard；`canonical-facts` 负责记录源业务事实的 owner、I/O、禁止路径、affected diagnostics 和文档维护规则。

## 代码入口

Canonical facts 分散在现有模块和 PostgreSQL repository 中。定位时先看：

- `backend/src/fin_ops_platform/postgres/migrations/`
- `backend/src/fin_ops_platform/services/postgres_repositories/`
- `backend/src/fin_ops_platform/services/*_service.py`
- `backend/src/fin_ops_platform/services/*_application_service.py`
- `backend/src/fin_ops_platform/services/*_command_service.py`
- `backend/src/fin_ops_platform/services/*_write_*.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

长期事实源是 `docs/architecture/module-boundaries/canonical-facts.md`。本模块目录只作为日常维护入口；具体业务状态机、API、权限、测试和实现细节仍由对应业务模块维护。

## 维护触发器

发生以下变化时，必须同步更新 canonical facts 边界：

- 新增、删除或改变 `app.*` canonical fact 表。
- 一个模块开始写入另一个模块拥有的业务事实。
- 新增 repair、migration、backfill 或 rollback 工具会写 canonical facts。
- 写操作影响 affected ids/months/scopes、domain event、job/result diagnostics 或 audit 行为。
- 将 legacy snapshot、local pickle、`state:*` JSON 或 direct SQL fallback 移入或移出 production 主路径。
