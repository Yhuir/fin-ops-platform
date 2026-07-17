# OA 集成模块边界与 I/O

日期：2026-07-17

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：OA 集成负责 OA 身份、Mongo adapter、projection sync、附件识别、OA 凭证和 OA 相关页面/API 的外部系统边界。
- 当前缺口：OA 相关能力横跨 OA 待付款、ETC、进项反提、设置和权限，变更必须声明受影响模块；生产周期性自动读取必须由运维层定时 enqueue durable `oa.sync`，不能恢复 HTTP 进程内 polling。
- 旧代码删除条件：旧 Mongo 直读/手写 projection path 不再被业务页面直接调用。

## 职责边界

### 负责

- OA 身份/权限适配、OA Mongo 读取、OA projection sync、OA 附件发票识别和 OA applicant credentials。
- 对 OA 待付款、ETC、进项反提等模块提供外部系统 adapter。

### 不负责

- 不拥有业务页面状态机。
- 不直接确认业务关联或付款。
- 不把外部 OA 数据直接当作页面 fresh read model。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| OA session/token | `auth.py`、session API | 权限和身份必须可校验 |
| OA Mongo/query | `mongo_oa_adapter.py` | projection sync 只调用 `load_sync_application_batch(scope_key)`：每个启用 form/scope 单次读取后输出 `projection_records` 与 `admission_records` 两个不可变视图。前者遵守通用 OA form/status 配置；后者固定接纳 completed + in-progress，不受通用 status filter 污染。任一 form 读取或目标文档投影失败时整批 fail-closed，不得提交部分集合 |
| OA sync event | `job.outbox_events(event_type='oa.sync')` / runtime worker | 手动同步、附件解析版本变化和 projection 版本变化都必须入 durable queue；HTTP 进程不得 inline sync 或自行轮询 Mongo |
| OA attachment/import | OA attachment services | 识别结果必须审计和可追踪 |
| OA source alias | `app.oa_source_aliases` | 仅 `active` alias 可参与 OA 附件票 duplicate canonicalization；不得按金额/申请人/项目自动合并 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| OA projection rows | repositories/read models | 带 source version；完成态 workflow status 由 OA projection 边界统一归一/识别，必须兼容 canonical `completed` 和历史完成态别名（如 `已完成`、`approved`、`2`），下游 read model 不得各自实现完成态判断。repository 以业务列与规范 JSON 的 `IS DISTINCT FROM` 判定真实变化；相同 snapshot 不更新 `app.oa_applications.updated_at`，不重写 item/attachment。snapshot output 必须拆成 `completed_projection_changed_scopes` 与 `oa_pending_payment_changed_scopes`：admission/payment-status-only 变化只刷新 OA 待付款；completed canonical 真实新增、修改、删除才由 sync service 交给既有 shared owner fan-out。snapshot repository 不直接 enqueue Workbench/shared consumers。 |
| OA sync status/run facts | AppHealth/AppStatus/operations dashboard | `app.oa_sync_runs(sync_type='oa_projection')` 是每次 Mongo/projection run 的事实源；成功、失败都必须落 run，失败不得提交部分 projection/snapshot。`job.outbox_events` 和 worker heartbeat 表示 refreshing/error，不得使用进程内内存状态或行级 `app.oa_applications.synced_at` 覆盖运行事实 |
| in-progress attachment metadata | OA pending admission | 当前只传递原始/上下文化文件元数据，不执行附件证据解析、发票识别或 OCR，不产生 artifact/evidence/invoice。未来 OCR 必须作为独立版本化链路设计，不得在本同步热路径内隐式启用 |
| OA session/permission payload | frontend session | 不泄露 secret |
| Attachment invoice result | invoice/ETC/input usage modules | 经 service 边界传递 |
| OA source alias canonicalization | object identity audit / downstream duplicate classifier | 只读消费 `active` alias，未批准 alias 仍按原 OA row/source 判定 |
| OA manual import mutation result | settings/workbench frontend、operation barrier | `refresh-attachments`、`manual-imports` create/remove 必须返回 affected scopes、read model scope keys、freshness targets 和 operation barrier targets |

## 持久化与投影

- Own read model：无单一页面 read model；影响 `oa_pending_payment`、`input_invoice_usage`、`invoice_lifecycle` 等。
- OA manual import/create/refresh/remove 影响 `workbench`、`workbench_relation`、`invoice_lifecycle`、`tax_offset`、`search` 和 `cost_statistics`；返回 target envelope 后由页面等待 operation barrier。
- OA projection sync 由 runtime worker 一次读取 dual-view source batch、条件写 `app.oa_*` projection、记录 `app.oa_sync_runs` / `app.oa_sync_watermarks`，再按明确 change cause 标记 downstream dirty scopes；周期性相同输入必须是零 projection rewrite、零 downstream fan-out。`all` 替换必须把旧 watermark scopes 纳入删除比较，不能漏掉最后一条 completed 被删除的月份。
- External system：OA Mongo / OA app。
- Repository：`postgres_repositories/oa_projection.py`、`oa_applicant_credentials.py`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Auth/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts` |
| Adapter/projection | `mongo_oa_adapter.py`、`oa_projection_sync.py`、`postgres_repositories/oa_projection.py`、`runtime_worker_registry.py` |
| OA services | `oa_identity_service.py`、`oa_manual_import_service.py`、`oa_attachment_invoice_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Related routes | `routes_oa_pending_payments.py`、`routes_etc.py`、`routes_input_invoice_usage_oa_reverse.py`、`server.py` |
| Related modules | OA pending payments、ETC、input invoice usage、settings、permissions |
| Tests | `tests/test_oa_*.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_session_api.py` |

## 依赖方向

- 允许依赖：external adapter, credential repository, access control service。
- 必须通过：OA adapter/service boundary。
- 禁止绕过：业务页面直接查 OA Mongo；service 直接读取 HTTP cookie/header。

## 测试与验证

- `tests/test_mongo_oa_adapter.py`
- `tests/test_oa_projection_sync_service.py`
- `tests/test_oa_manual_import_api.py`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_target_oa_applicant_token_provider.py`

## 当前缺口和删除条件

- OA token/credential 变更必须同步 permissions/security docs。
- sync service 的多次 list/month 扫描与 adapter fingerprint polling 已删除；架构 guard 禁止恢复第二套 Mongo 扫描、部分结果 fallback 或混合变化集合 fan-out。

## Canonical facts ownership

- Owned facts: `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_runs`、`app.oa_sync_watermarks`、`app.oa_attachment_invoice_cache*`、`app.oa_source_aliases`、`app.manual_oa_imports`、`app.oa_applicant_credentials`。
- Allowed writes: OA sync worker、manual OA import service、OA credential service、受控 attachment repair/alias tools。
- Allowed reads: OA projection adapters/read ports、OA integration APIs。
- Downstream outputs: workbench、pending invoice、OA pending、invoice lifecycle、search dirty scopes 或 owner producer 输出。
- Forbidden paths: production API 不得直接读 OA Mongo；HTTP 进程不得启动 OA polling、热重建 Workbench read model 或 fallback inline sync；OA cache 不得当作正式发票池；OA source alias 不得由弱业务指纹自动激活；OA credential 不得通过 settings snapshot fallback 写入。
- Old code deletion: direct Mongo runtime adapter fallback、OA snapshot fallback、进程内 `OASyncService` polling/hot rebuild、无调用方 fingerprint polling、sync service 多 list 扫描和绕过 projection/queue 的 API 读取必须删除；migration/audit/rollback 工具保留不算 closure。
