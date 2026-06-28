# Canonical Facts 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium-high
- 目标边界：每类 PostgreSQL canonical fact 都有唯一业务 owner、明确写入口、明确读入口、明确下游输出和禁止绕过路径。
- 当前缺口：owner matrix 已建立首版；各业务模块还需要在自身 `boundary-io.md` 中逐步补齐具体 writer/read port、repair tool 和 deletion condition。
- 旧代码删除条件：生产 API/worker 不再依赖 legacy full snapshot、local pickle、`state:*` JSON、direct cross-module SQL write 或旧 fallback 来读写 canonical facts。

## 职责边界

### 负责

- 维护 canonical facts ownership matrix。
- 定义源业务事实、direct API facts、runtime facts、cache/transport 和 legacy read model delete inventory 的分层边界。
- 规定跨模块写入和读取 canonical facts 的 I/O 约束。
- 要求 owner 模块声明 affected ids/months/scopes、domain events、job/result diagnostics 和 audit。

### 不负责

- 不拥有所有业务表。
- 不新增集中式 `UnifiedFactSource` service。
- 不替代业务模块的状态机、权限、API、repository 或 legacy read model delete inventory。
- 不管理 read model freshness；legacy read model 只由 `read-models` 模块维护下线清单和 no-restore guard。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Canonical write | 页面 API、worker、业务 service、repair 工具 | 必须进入 fact owner 的 command/application service、UoW、repository port 或明确 adapter。 |
| Canonical read | 页面 service、query service、audit/repair 工具 | 必须走 owner 暴露的 read/query port；直接 SQL 读取必须在模块边界中登记。 |
| Cross-module mutation | 非 owner 模块 | 只能调用 owner 公开边界，不能直接改表。 |
| Runtime repair | 运维脚本、受控工具 | 必须 dry-run、审计、记录 rollback manifest，并说明 owner。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Business result | API/service caller | 返回业务对象、version、affected months/scopes 或明确不适用。 |
| Domain event | Derived lifecycle | 包含足够 scope 信息，不让下游猜测全量影响。 |
| Runtime job/outbox | runtime queue / real worker | 经 owner producer、outbox/job repository 或同事务等价 writer；不得恢复 page read-model refresh gateway。 |
| Affected scope diagnostics | 前端/API 调用方 | 高影响写操作返回业务结果、affected months/scopes 或 job/result 诊断；页面写后直接 refetch，不等待 operation barrier。 |
| Audit | `audit.*` | 记录 actor、action、scope、before/after 或 repair manifest。 |

## 持久化与投影

- Canonical facts 主要在 `app.*`。
- Runtime facts 在 `job.*` 和 `audit.*`。
- Legacy read model 投影在 `read_model.*`，不属于 canonical facts，也不作为页面 direct read proof。
- 外部源如 OA Mongo、Excel/PDF/ZIP 不是 app 内部 canonical facts；app 只保存导入或投影后的受控事实。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| 架构合同 | `docs/architecture/module-boundaries/canonical-facts.md` |
| 模块入口 | `docs/modules/canonical-facts/README.md`、`boundary-io.md` |
| Schema 来源 | `backend/src/fin_ops_platform/postgres/migrations/` |
| Repository | `backend/src/fin_ops_platform/services/postgres_repositories/` |
| Business owner | 各 `*_service.py`、`*_application_service.py`、`*_command_service.py`、`*_write_*.py` |
| Downstream diagnostics/jobs | `derived_data_lifecycle_service.py`、module-specific lifecycle producers、runtime worker/job registry |
| Tests | owner 模块 API/service/direct payload tests、architecture guards、runtime queue/worker tests |

## 依赖方向

- 允许依赖：owner module 的 public command/read port、repository port、derived lifecycle producer、runtime job/outbox boundary。
- 必须通过：owner boundary 或同事务等价 writer。
- 禁止绕过：非 owner direct SQL writes、production full snapshot fallback、read model 反向写 canonical fact、Redis/RabbitMQ/frontend event 作为业务事实源。

## 测试与验证

本模块本轮只新增文档合同；后续代码重构按 owner 模块补测试：

- Business core：事实状态机、金额/关系/分类/版本冲突。
- Service-layer：repository/UoW、audit、affected diagnostics、outbox/job、rollback/partial failure。
- API contract：写结果、affected scopes/job diagnostics、permission failure。
- Read model/cache/background job：canonical write 后 direct payload、cache warmup 或真实后台任务收敛；legacy read model 仅覆盖 no-restore/delete guard。
- Existing feature regression：旧页面/导出/权限/legacy read model guard 不被新 owner 边界破坏。

## 当前缺口和删除条件

- 首版 matrix 需要随着代码重构逐模块校准。
- shared repository 仍是过渡期 SQL owner；业务 owner 必须由模块文档和 service boundary 决定。
- 保留 migration/shadow/audit/rollback 工具时，必须写明保留理由、禁止生产主路径调用和删除条件。
