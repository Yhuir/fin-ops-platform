# 系统状态模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：系统状态页面聚合 app health、app status、runtime worker/read model readiness；受控运维动作只能通过明确 admin-only endpoint 入队 runtime job，不直接改业务事实或 read model 表。
- 当前缺口：server.py 仍保留部分 app health/status endpoint。
- 旧代码删除条件：所有 health/status endpoint 有明确 route/service owner 且前端只读观测 API。

## 职责边界

### 负责

- 系统状态页面、健康告警、read model/worker readiness 展示。
- 聚合 app status domain/read model/job/dependency registry。
- 为运维判断 fresh/drain/worker 状态提供只读入口。

### 不负责

- 不直接修改业务事实、relation 或 read model 表。
- 不绕过 durable runtime queue 直接刷新 read model。
- 不隐藏 stale/refreshing 状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面读取 | `AppHealthOperationsPage.tsx`、`features/appHealth/api.ts` | 只读 API |
| Health probe | app health endpoints | 返回 PostgreSQL、OA sync、canonical matching job、`workbench` 与 `workbench_relation` 的 readiness/status；不读取 Search、no-OA 或其它已退役 projection。`/health/ready` 实时读取 durable facts，同一请求内复用 current-effective outbox/dirty-scope 集合，不扫描历史 `done`；完整性能指标由 `/health`、`/metrics` 和 Operations dashboard 负责。 |
| Runtime registry | app status services | 聚合 worker/read model/job/dependency 状态；App Status summary 的 readiness I/O 只读取状态、scope、时间和错误等实际消费列，不读取/解码逐 scope `source_versions`；版本向量只由 Operations dashboard 的 scope-evidence 查询 owner 读取。operations dashboard 默认不等待 RabbitMQ management API，RabbitMQ queue metrics 作为可选 transport 观测以 unknown 降级。每个 read model 额外读取最近 scope 事件与 readiness，区分 `current_scope` 和 `full_history_batch`；该查询按精确 `event_type` 读取最近 5 条并由 `outbox_events_read_model_scope_evidence_idx` 支撑，禁止对每个 model 重复扫描、排序全量 outbox 历史 |
| Dashboard inventory facts | `app.bank_transactions`、`app.invoices` / `source_links`、`app.import_batches`、`app.oa_*`、`app.oa_sync_runs` | 发票 inventory 按 canonical invoice source link 和 `invoice_type` 统计；OA 上次读取时间优先使用 `app.oa_sync_runs(sync_type='oa_projection')` 的成功 run；导入历史只读 `app.import_batches` 中手工银行流水和发票导入批次 |
| OA sync runtime facts | `job.outbox_events(event_type='oa.sync')`、`runtime_worker_heartbeats`、`app.oa_sync_runs` | `/api/oa-sync/status` 和 AppHealth `oa_sync` 只读 durable queue、worker 和 projection run facts；不得依赖 HTTP 进程内内存状态 |
| 进项/销项页面全量审计 | `app.invoices`、`app.workbench_pair_relations` | 页面与 App Health 分别调用统一 `/api/operations/app-health/page-audit?page=input-invoice-usage` / `?page=output-invoice-collections`；在同一只读快照内检查 canonical 发票与 active relation。旧 specialized HTTP routes 和页面 projection 审计已删除。 |
| 已退休页面 refresh routes | 旧 admin request | `input-invoice-usage-refresh`、`output-invoice-collection-refresh`、`pending-invoice-refresh` 已删除并返回 `404`；这些页面直接读取 canonical facts，App Health 只保留只读 page audit，不再代页面写入 runtime queue |
| 页面 Audit registry 与统一入口 | `PAGE_AUDIT_REGISTRY` 的 19 个 frontend page key 和对应 proof owner metadata | `/api/operations/app-health/page-audit?page=<page_key>` admin-only 只读。registry 必须与 `web/src/app/pageRegistry.tsx` 集合严格相等；当前 19 页全部 `ready`。单页 Audit 各自打开一个 `REPEATABLE READ READ ONLY` snapshot；`page=app-health-operations` 是 system owner，只打开一个 outer snapshot 并把同一 `AuditSnapshot` 显式传给其余 18 个正式 proof owner。审计 snapshot 使用 transaction-local 60 秒 statement timeout，事务结束自动恢复，不改变普通 API/业务 SQL 的 10 秒默认上限。结果必须带 `page_key`、`contract_revision`、`proof_availability=ready`；不得刷新、修复或写入。 |
| App Health system Audit | 16 个页面正式 proof、dashboard database inventory、`READ_MODEL_MANIFEST`、`RUNTIME_WORKER_REGISTRY`、current durable runtime、四域 external manifest header/items | 返回 `database_system_snapshot`、`runtime_observation`、`external_evidence`。所有数据库证明共享同一 `snapshot_identity`/`system_audit_id`；外部 owner 独立重算 canonical exact set/field fingerprints/controls。缺证据 unknown，latest revoked/expired/mismatch fail，四域精确通过才是 `proven_as_of_external_evidence`。 |
| External evidence 运维输入 | 可信来源 artifact + manifest、显式 actor/reason、validate/dry-run/apply/revoke 命令 | 只允许 `ExternalControlEvidenceService -> PostgresExternalControlEvidenceRepository`；header/items immutable append，撤销写审计事件，不新增 HTTP/UI 写入口。artifact 必须在 DB I/O 前复验 sha256/size；System Audit 不采集外部网络、不登记、不修复。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| App health payload | 页面/indicator | 不伪装 readiness；OA pending/processing outbox 必须显示 refreshing，OA failed outbox/worker/run 必须显示 blocked/error。Workbench matching 只把 `dirty/retry/processing/failed` durable scope 作为当前异常状态，历史 `completed` 不进入 payload。runtime snapshot 的短 TTL cache 在 HTTP 进程内 single-flight；alert snapshot 只有发生状态迁移时才持久化，健康 GET 不做无变化写入。 |
| Read model scope evidence | App Health read model table | 每个 model 展示最近 scope 的 type/key、current-scope/full-history、expected/projection source versions、lag、queue wait、handler duration、attempt/retry、dedupe reason 与 last error；证据查询失败只降级该观测块并返回 warning，不伪装为 fresh。 |
| Read model historical diagnostics | App Status details | manifest `fan_out_command` 的 command-only parent readiness 不参与当前 domain/overall severity，输出到 `historical_scopes` 且 `current_effective=false`；同 scope 当前 dirty/outbox failure 和 child shard failure 仍参与 blocked/busy。 |
| Alert/status | shell/status page | 明确 stale/failed/degraded |
| Dashboard payload | operations page | 只读聚合 canonical invoice、OA、bank、import、worker 与两个保留 read model runtime；不读取其它已退役 projection。`data_inventory.invoice.sources` 固定为 `manual`、`input_invoice`、`output_invoice`、`oa_attachment`；OA completed/in-progress/items 均由 PostgreSQL canonical OA facts 和最近成功 sync run统计。RabbitMQ 管理指标默认以 unknown 输出，不能阻塞健康探针；任一局部 block 失败只降级该 block 并返回当前其它事实。 |
| 进项使用审计报告 | admin/API consumer | `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh` 才能证明已登记 invariant 一致；`*_sample_count` 是有上限样本，不是全量问题总数 |
| 销项收款审计报告 | admin/API consumer | `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh` 才能证明已登记 invariant 一致；`issues_found` 只报告有上限样本，不做自动修复 |
| 页面业务审计报告 | 页面标题 Audit icon / admin API consumer | 只有 `proof_availability=ready`、非空 `contract_revision`、`audit_status.integrity=pass`、`freshness=fresh`、`queue=drained` 且 `database_snapshot=true` 才显示“此数据库快照内已登记 App 内部合同一致”。relation consumer 页面还要求 registered typed edge equality；非消费者明确 `not_applicable`。任何页面成功都不证明后续写入，也不能证明外部银行/OA/发票/ETC 来源没有遗漏。 |
| System Audit 报告 | App Health 页面 / admin API consumer | 内部 `overall_status=pass` 与外部 `external_evidence.status` 分开判定。只有四域全部 exact pass 才输出 `proven_as_of_external_evidence`，并显示 evidence as-of/source snapshot；unknown/fail 都是 unproven。页面显示 system snapshot time/id，并在下一次 dashboard refresh 后清除旧绿色结果。 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Reads readiness of：all app status/read model/job registries。
- Reads facts of：`app.bank_transactions`、`app.invoices`、`app.import_batches`、`app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_runs`、`app.tax_certified_import_records`、`app.etc_invoices`、ETC archive/file facts、`audit.external_control_evidence*`、`job.outbox_events`、`job.runtime_worker_heartbeats`。
- Service owner：`AppHealthService`、`AppStatusOverviewService`、`RuntimeMonitoring`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/AppHealthOperationsPage.tsx` |
| Frontend feature/context | `web/src/features/appHealth/*`、`features/appStatus/*`、`contexts/AppHealthStatusContext.tsx` |
| Shell | `web/src/components/shell/AppStatusIndicator.tsx` |
| Backend route | `/api/app-health*`、`/api/operations/app-health-dashboard`、`/api/operations/app-health/page-audit` in `server.py` |
| Backend service | `app_health_service.py`、`app_health_alert_service.py`、`app_status_overview_service.py`、`runtime_monitoring.py`、`operations_audit_service.py`、`page_audit_registry.py` |
| Backend audit repository | `services/postgres_repositories/operations_audit.py`、`audit_report.py`、`app_health_system_audit.py`、`workbench_relation_audit.py`、`page_business_audit.py`、各 direct page audit repository、`external_control_evidence.py`、`external_control_evidence_audit.py` |
| Registries | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py`、`page_audit_registry.py` |
| Tools/tests | `tools/app_status_readiness_backfill.py`、`tools/audit_page_business_read_model.py`、`tests/test_app_health*.py`、`tests/test_app_status*.py`、`tests/test_audit_page_business_read_model_tool.py` |

## 依赖方向

- 允许依赖：status registries, runtime monitoring, app health services。
- 必须通过：`server.py(page key) -> OperationsAuditService -> PostgresOperationsAuditRepository -> registry-selected finite proof owner`；registry 只含 metadata，不含 SQL/HTTP/refresh。direct 页面审计 canonical facts/relations，两个保留 read model 由各自 proof owner 审计；`tools/audit_*.py` 只允许命令行参数与输出适配。
- 禁止绕过：系统状态页面直接改业务/read model 表；隐藏 failed/stale worker；用行级 projection `synced_at` 或内存状态覆盖 durable OA sync run/outbox/worker facts。

## 测试与验证

- `tests/test_app_health_api.py`
- `tests/test_app_health_service.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_operations_dashboard_service.py`
- `tests/test_audit_page_business_read_model_tool.py`
- `tests/test_operations_audit_service.py`
- `tests/test_operations_audit_report.py`
- `web/src/test/AppHealthOperationsPage.test.tsx`
- `web/src/test/PageAuditIcon.test.tsx`

## 当前缺口和删除条件

- 如果引入直接修复操作，必须拆成独立运维 command 模块并补权限/审计；只入队 read model refresh 的操作必须保持 admin-only、scope policy 校验和 runtime queue 边界。
- 19 个 registry 页面均已 ready。App Health 不拥有普通 read model 或业务 relation；它的 ready 合同是 system operational proof，而不是虚构页面 projection。
- App Health 旧 `InputInvoiceUsageAuditPanel`、专项 state/callback 和 Browser mock specialized URL 已删除；进项页仍通过自己的统一 page key Audit 控件证明自身合同。
- specialized input/output HTTP routes、frontend clients 和 service/repository public methods 已删除；统一 repository executor 与只读 CLI thin adapters 继续复用同一 invoice proof core。

## Page Audit contract v26（2026-07-21）

- v27 延续 Workbench canonical expected-set 的精确跨月关系、ETC collapsed
  membership/detail、OA pending alias/canonical 补载与成本统计合法 identity 合同。
  其它 canonical 页面 Audit 只绑定本次 immutable PostgreSQL snapshot；关联台 Audit 同时证明
  active generation 与 canonical source proof 一致。旧绿色结果不能跨 snapshot 复用。
- 绿色只证明同一 immutable PostgreSQL snapshot 内“已进入 App 的 canonical facts、
  页面 expected-set、active canonical relations 与关键字段”一致；两个保留 read model
  的 freshness/queue 由独立 runtime proof 负责。
- pre-contract import provenance warning 明确声明历史 workflow artifact 未被证明；对应 canonical bank/invoice/ETC 业务事实仍须由业务页面 Audit 阻断证明。
