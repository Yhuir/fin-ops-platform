# App Health Operations 模块边界与 I/O

日期：2026-08-15

## 职责

- 现金不在 page audit registry 或按接口页面耗时记录中；不得查询 `cash.*`、返回现金项目/金额/ID/查询条件。全局 HTTP 并发/错误计数可保留，技术日志现金路径统一脱敏为 `/api/cash`。现金性能通过已授权的专用只读测量验证，不塞回系统状态页。

- 聚合 session、OA sync、background jobs、四个 required worker、PostgreSQL 通用 outbox、Workbench matching dirty scopes 和依赖状态。
- 展示 HTTP/DB request timing、import inventory、operation audit。
- 编排只读 canonical page proof / System Audit；前端只允许 App Health 发起固定 System Audit，业务页面不暴露 Audit 控件。
- Admin-only；不直接修改 business facts。

## 输入

| 输入 | Owner |
| --- | --- |
| Health/dependency state | app health services |
| Worker registry/heartbeat | runtime worker registry/repository |
| PostgreSQL queue metrics | runtime monitoring repository |
| 导入任务与积压 | `job.import_jobs`；prepare、待确认、commit 共用同一任务，import worker 直接领取 |
| Workbench matching scopes | `job.workbench_matching_dirty_scopes`；只读 status/last_error |
| API/DB timing | request metrics collector |
| Canonical audit | page audit repositories，一个 caller-owned read-only snapshot |

## 输出

- `/api/app-health`：bounded global status。
- `/api/operations/app-health-dashboard`：admin-only inventory/performance/runtime DTO。
- `/api/operations/app-health/page-audit`：后端 page proof dispatch 与前端唯一 System Audit 的 bounded report。
- `/health`、`/health/ready`、`/metrics`：liveness/readiness/Prometheus。

输出不包含旧 projection registry、scope/readiness 或 freshness summary。Queue 分别显示 PostgreSQL 通用 event types 与直接领取的 import jobs，
缺少必要字段时必须标记 unavailable，不能伪造 queue healthy。

`/api/background-jobs/active` 聚合导入任务摘要及其他原有后台任务；导入状态从 `job.import_jobs` 派生，旧独立导入 BackgroundJob 不再参与执行状态。待确认可显式打开对应预览；失败可同意图重试，读取结果不执行导入。导入失败和待复核保持可见，但用户输入错误不阻断全部页面健康状态。三类导入 page audit 检查直接任务，不要求已退役的 import outbox 事件。

`workbench_matching.status=stale|rebuilding|error` 必须把 Workbench domain 标为 busy/yellow；failed scope 产生 critical alert 并携带 scope 与错误。该诊断不阻断全局写入，也不创建已退役的 `workbench_matching` BackgroundJob。

## 禁止边界

- 不 enqueue 修复，不写业务表，不清 queue/DLQ，不伪造 heartbeat。
- 不把 dashboard/Audit 作为业务页面事实来源。
- 不在 `/health/ready` 热路径执行无界 SQL 或外部管理接口查询。

## 验证

`tests/test_app_health_api.py`、`tests/test_app_health_service.py`、
`tests/test_app_status_overview_service.py`、`tests/test_audit_app_health_system.py`、
`web/src/test/AppHealthOperationsPage.test.tsx`。

## 2026-09-12 流水批次合并后的审计

流水批次成员审计直接读取 submitted 批次与 active canonical relation。原始独立批次关系要求成员集合严格相等；批次并入普通 OA/发票关系后，要求全部银行成员包含于同一个 active 关系，允许该关系包含其它成员。缺失成员、非 submitted 批次仍占用原始批次关系、孤立批次关系仍报错。只读 SQL 边界及审计 API 不变，不修写业务事实。真实 PostgreSQL 回归覆盖完整合并、缺失成员、额外原始成员和已撤回批次残留。

候选审计使用包含正式历史的同一 canonical source 重建批次，成员覆盖与重复检查仅针对 draft/unsubmitted/conflict 当前候选。submitted/withdrawn/stale 正式历史仍由原正式批次关系审计负责，不得将撤回历史当作第二个候选，也不得用历史成员掩盖当前候选缺失。共享 source query 的历史版本不能在审计调用方清空。

## 2026-09-20 Matching 完成通知

`/api/app-health.workbench_matching.last_completed_at` 是现有 matching scope 列表中最新 completed_at，可为 null。复用已有队列读取，不增加每次轮询 SQL；前端状态 context 向关联台透出时间变化以触发一次回读。仍不写业务事实、不增加页面门禁或轮询列表。

## 2026-09-21 Shell 状态完整性

Shell 接受后端关联域 `error/rebuilding` 与 worker `mismatch` 状态，不因这些有效状态丢弃整份 overview。运行摘要缺失时前端模型为 null，Worker、Queue 和空数据域显示“状态未知”；有明确队列摘要且计数为零时仍显示“无队列积压”。权限和写入门禁不变。

## 2026-09-22 导入状态与恢复闭环

运行状态、共享任务进度和任务诊断的导入执行事实统一为 `job.import_jobs`。`scoped_import_jobs` 根据选中文件所属会话及已登记类型批量投影归属，未知归属返回 import_unknown，不广播到银行/发票两域。不同状态分别计数，backlog=pending+processing；failed/needs_review/awaiting_confirmation 是待处理而非运行中。全局计数不受个人详情权限/样本上限影响，不泄露原文件或其他用户业务错误内容。管理员诊断采用独立的分页导入任务 GET；Dashboard 不再携带旧 import_jobs 样本。健康读取只读、零修复命令。前端旧 RabbitMQ 字段已移除，展示真实 PostgreSQL 队列字段。业务失败不新增全站写入门禁。

实施和验收见 [修复计划](../../dev/import-runtime-status-repair-plan.md)。

## 2026-09-22 管理员导入任务处理

现有系统状态页的任务诊断改为独立的导入管理员查询（默认20条可翻页），详情与处理命令由 imports owner 提供。健康 GET/Audit 仍只读。Dashboard 库存和请求统计保持原缓存，runtime 在缓存命中时重新读取；移除旧 dashboard import_jobs 20条样本查询、DTO 和展示，避免已处理任务被整页缓存恢复。

实施、验证与旧链路清理见[处理闭环](../../dev/import-task-disposition-plan.md)。

## 2026-09-23 共享导入任务

银行、发票和 ETC 的已登记 durable import task 向所有已获平台访问权的登录用户开放查看、复核、重新预览、重试、确认和结束处理；不按创建人或管理员分层。未登记的私人草稿继续校验创建人；OA、税务和其他任务保留原权限。原页面权限、App Health 管理权限、设置和现金边界不扩大。

- 输入：`GET /api/imports/jobs?page&page_size&domain`、按任务 UUID 读取详情/银行映射、既有 session/review/confirm/retry/discard API。session 访问必须由同一 durable task 的类型、session ID 和原创建人事实证明；没有 task 时仅允许原草稿本人。`domain` 在分页与计数之前筛选，详情按需读取。
- 输出：共享任务摘要与分页详情、既有预览/任务 DTO、状态变化与真实操作人审计。创建人与文件 provenance 不修改；确认/重试的 actor 快照随任务持久化，worker 按实际操作人的当前平台授权执行，成功结果和领域审计与事实同事务。
- 前端：全局状态、银行/发票/ETC 页和 App Health 复用 `ImportJobDiagnostics`；共享抽屉复用 `ImportWorkflowPage` 的任务模式，不要求进入受页面 ACL 限制的原页。正常上传页仍为空白草稿；打开共享任务使用独立组件实例，不覆盖当前未保存内容。
- 刷新：沿用现有全局轮询，写后回读当前任务/列表；共享任务跨状态保持可见。不新增定时器、缓存、read model、队列、依赖、迁移或备份。
- 旧链清理：删除导入任务 admin-only、共享任务 creator-only、跨用户无法继续预览文案与对应旧测试假设；非共享任务的 owner 校验保留。失败不能用普通已读绕过明确结束处理；原错误历史保留。
- 验证：共享权限、私人草稿隔离、跨用户确认/异步审计、分页筛选、并发与回滚、丢失响应核实、旧页面导入回归；见[共享实施与验收](../../dev/import-task-disposition-plan.md#共享处理修订2026-09-23)。
