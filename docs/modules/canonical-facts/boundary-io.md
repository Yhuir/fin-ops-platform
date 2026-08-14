# Canonical Facts 模块边界与 I/O

日期：2026-08-04

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：每类 PostgreSQL canonical fact 都有唯一业务 owner、明确写入口、明确读入口、明确下游输出和禁止绕过路径。
- 当前缺口：无 final closure blocker。owner matrix 已建立；旧生产 source-of-truth 路径已删除或 guard；`file_object.gridfs_migration` worker 已随 07-owned registry 同切片删除；retained bank/ETC 运维工具是 owner-runbook I/O，必须经过 lightweight tool runtime/public app ports，不得成为业务事实源。
- 旧代码删除条件：生产 API/worker 不再依赖 legacy full snapshot、local pickle、`state:*` JSON、direct cross-module SQL write 或旧 fallback 来读写 canonical facts。

## 职责边界

### 负责

- 维护 canonical facts ownership matrix。
- 定义源业务事实、read model、runtime facts、cache/transport 的分层边界。
- 规定跨模块写入和读取 canonical facts 的 I/O 约束。
- 要求 owner 模块声明 downstream dirty scopes、domain events、operation barrier targets 和 audit。
- 要求旧生产 source-of-truth 路径删除。

### 不负责

- 不拥有所有业务表。
- 不新增集中式 `UnifiedFactSource` service。
- 不替代业务模块的状态机、权限、API、repository 或 read model。
- 不管理 read model freshness；该职责属于 `read-models`。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Canonical write | 页面 API、worker、业务 service、repair 工具 | 必须进入 fact owner 的 command/application service、UoW、repository port 或明确 adapter。 |
| Canonical read | 页面 service、read model builder、audit/repair 工具 | 必须走 owner 暴露的 read/query port；直接 SQL 读取必须在模块边界中登记。 |
| Cross-module mutation | 非 owner 模块 | 只能调用 owner 公开边界，不能直接改表。 |
| Runtime repair | 运维脚本、受控工具 | 必须 dry-run、审计、记录 rollback manifest，并说明 owner。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Business result | API/service caller | 返回业务对象、version、affected months/scopes 或明确不适用。 |
| Domain event | Derived lifecycle | 包含足够 scope 信息，不让下游猜测全量影响。 |
| Durable domain job/outbox | runtime queue / domain worker | 经 owner service 或同事务 writer；页面读取不产生任务。 |
| Operation barrier target | 前端操作闭环 | 高影响写操作必须返回或透出 freshness target。 |
| Audit | `audit.*` | 记录 actor、action、scope、before/after 或 repair manifest。 |

## 持久化与投影

- Canonical facts 主要在 `app.*`。
- Runtime/audit facts 在 `job.*` 和 `audit.*`。
- Read model 投影在 `read_model.*`，不属于 canonical facts。
- 外部源如 OA Mongo、Excel/PDF/ZIP 不是 app 内部 canonical facts；app 只保存导入或投影后的受控事实。
- OA 附件解析 cache 不是正式发票池。只有 `OAAttachmentInvoicePromotionService` 可按强发票身份和显式 OA/expense-item/attachment source context 调用 canonical invoice repository；同批身份一次查询、批量保存，重复输入不得刷新 `app.invoices.updated_at`。20 位纯数字 `invoice_no` 与显式 `digital_invoice_no` 使用同一强身份。service 必须先按强身份批量加载既有发票，repository 读取时完整恢复 normalized payload 中参与附件 merge 的发票字段，并只按既有 canonical `legacy_mongo_id` 更新；`source_unique_key` 唯一索引继续阻止并发或漏加载产生重复事实，但禁止用一个新 persistence object 对 strong-key conflict 做全字段覆盖。
- `0134_restore_invoice_import_provenance.sql` 只修复同时存在 OA 附件来源、正式 import row 证据、但缺失对应 `manual_invoice_import` source-link 的发票；从 batch/row 事实恢复全部来源边、owner batch、`人工导入` tag 与 normalized payload，一次审计、重复执行零写。它不扫描或修改没有该精确交集的发票。
- `0103_etc_reconciliation_task_timestamps.sql` 是 ETC owner 的一次性确定性 payload backfill：只把 `app.etc_reconciliation_tasks` 同行 typed `created_at/updated_at` 复制到缺失的 normalized payload 字段，不改变状态、版本、scope、typed 时间或任何下游 read model/queue 事实。
- `0129`、`0130` 先以 `NOT VALID` 保护 canonical outbox/fact/relation/job 的新写入；只读领域合同审计归零后，`0131` 仅把历史 background job 的退休月份标记 `all` 归一化为空或保留的真实 `YYYY-MM`，同步其 normalized raw payload，并验证全部 28 个约束。该迁移不修改业务金额、关系状态或页面 read model。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| 架构合同 | `docs/architecture/module-boundaries/canonical-facts.md` |
| 模块入口 | `docs/modules/canonical-facts/README.md`、`boundary-io.md` |
| Schema 来源 | `backend/src/fin_ops_platform/postgres/migrations/` |
| Repository | `backend/src/fin_ops_platform/services/postgres_repositories/` |
| Business owner | 各 `*_service.py`、`*_application_service.py`、`*_command_service.py`、`*_write_*.py` |
| Downstream domain work | 明确的 OA sync、import、settings maintenance 或 matching owner |
| Tool runtime I/O | `backend/src/fin_ops_platform/tools/runtime_application.py`，只允许 retained owner-runbook 工具通过 lightweight app bootstrap 和 public app tool ports 访问所需 I/O。 |
| Tests | owner 模块 API/service/read model tests、architecture guards、runtime queue/read model tests |

## 依赖方向

- 允许依赖：owner module 的 public command/read port、repository port、derived lifecycle producer、read model refresh gateway。
- 必须通过：owner boundary 或同事务等价 writer。
- 禁止绕过：非 owner direct SQL writes、production full snapshot fallback、read model 反向写 canonical fact、Redis/RabbitMQ/frontend event 作为业务事实源。

## 测试与验证

本模块 wave 1 只新增文档合同；后续代码重构按 owner 模块补测试：

- Business core：事实状态机、金额/关系/分类/版本冲突。
- Service-layer：repository/UoW、audit、dirty/outbox、rollback/partial failure。
- API contract：写结果、affected scopes、operation barrier target、permission failure。
- Read model/cache/background job：canonical write 后 downstream projection 收敛。
- Existing feature regression：旧页面/导出/权限/read model 不被新 owner 边界破坏。

## 当前缺口和删除条件

- owner matrix 后续只随 owner 模块常规维护校准；不再是 Canonical Facts final closure blocker。
- shared repository 仍是过渡期 SQL owner；业务 owner 必须由模块文档和 service boundary 决定。
- 旧生产 source-of-truth 路径必须删除。migration/shadow/audit/rollback 工具保留时，必须写明保留理由、禁止生产主路径调用和删除条件，且不算 closure。
- 当前仍保留的 ETC historical migration/link/cleanup 和 bank auto-tag restore 运维工具必须通过 `tools/runtime_application.py` 的 lightweight tool runtime builder 取得 public app tool ports；业务工具文件不得直接调用 `build_application(...)`、访问 `Application._*`、`Application._state_store` 或 `_initialize_runtime_services`。`tool_runtime_ports()` 不得暴露完整 `state_store`，工具初始化只能通过 `Application.tool_runtime_state_snapshot()` 取得最小 state。该边界不是新的长期业务事实源，可在工具退休或归并 owner module CLI 后删除。
- `file_object.gridfs_migration` final closure blocker 已删除：registry registration、worker flag/handler、legacy GridFS service/config、deploy env examples 和 RabbitMQ dispatch event 已同切片移除，guard 禁止回归。
- `ApplicationStateStore` / local pickle 只保留为非生产 fixture/tooling I/O；它不是 canonical facts owner，也不得通过 production factory、app、service、worker 或 tool 主路径成为业务事实源。
