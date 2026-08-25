# 设置状态机

> 修改设置相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。设置模块是高扇出配置域，不能只按页面局部状态理解。

## 业务状态

### 普通 settings

- 事实源：`AppSettingsService` 从 `ApplicationStateStore` 加载、normalize、保存。
- 主要状态：`loaded`、`editing`、`saving`、`saved`、`validation_failed`、`version_conflict`、`save_failed`。
- 允许流转：
  - `loaded -> editing -> saving -> saved`：保存项目、银行映射、OA 配置、标签和规则；ACL 使用下方独立 command 状态机。
  - `saving -> validation_failed`：非法标签、重复映射、历史非法 pending invoice 映射需要显式暴露，不得静默丢弃。
  - `saving -> version_conflict`：银行标签或待找发票规则 stale version。
- 禁止流转：
  - 保存非法 pending invoice 映射后产生 audit 或 finalize。
  - 非 admin/readonly 绕过 UI 直接写入高风险设置。
  - settings payload 包含 OA 申请人密码、密文或 token。

### 项目范围

- 状态：`oa_synced`、`manual_active`、`completed`、`local_deleted_override`。
- 允许流转：
  - OA 同步项目进入 active。
  - 手工项目新增后默认为 active。
  - active 与 completed 之间由 settings 保存切换。
  - OA 项目本地删除只记录 override，不删除 OA 事实。
- 影响：项目范围变化会影响成本统计、搜索和项目筛选；canonical 页面下一次 GET
  直接读取新 version，Search 共享模型由自身 owner 处理。

### 访问控制

- canonical snapshot：固定 `administrator=YNSYLP005`、独立 `access_control_version`、完整 `full_access` / `read_export_only` memberships；其他账号缺席即 `denied`，管理员不属于可写 membership。
- 用户名：比较/去重使用共享 casefold key，输出保留 OA canonical spelling；collision、跨 tier overlap、控制字符与 protected-admin 输入直接 `validation_failed`。
- 消费：permissions evaluator 每次非管理员判断最多读取同一 snapshot 一次；ACL 删除后下一次 session/API 立即 denied，不依赖 OA identity cache。
- 影响：权限不走 read model，但会影响所有写入按钮、导出、数据重置和运维修复入口；OA 三角色只投影菜单可见性，不能反向改变 APP tier。

### 业务规则和标签

- 银行标签状态：`active`、`archived`、`in_use_blocked`、`version_conflict`。
- 待找发票规则状态：income/expense 方向独立 version；非法映射可从历史 payload 加载并展示修复。
- 影响：规则保存只提交规则/version/audit；canonical 页面下一次 GET 直接应用，
  不产生已退役页面 dirty scope。

### OA 申请人凭据

- 事实源：独立 `oa_applicant_credentials` repository，本地内存或 PostgreSQL pgcrypto。
- 状态：`unconfigured`、`configured`、`disabled`。
- 允许流转：admin 保存目标 OA 申请人账号密码后 `unconfigured -> configured`；admin 删除后回到 `unconfigured`。
- 禁止流转：非 admin 维护凭据；列表、settings payload、日志、错误响应暴露密码、密文或 token。

### OA 精确附件刷新

- 事实源：`job.outbox_events(event_type='oa.sync')`；payload 显式为 `operation=refresh_attachments + row_ids`。
- 状态：`queued -> processing -> done`，失败为 `failed/dead_lettered`。
- POST 只返回 202/event id；页面轮询同资源状态，并且只有 terminal `done` 才用 worker result 更新附件/可导入发票计数。
- 缺失、非完成态、OCR/解析/promotion 失败必须显示真实错误；禁止返回旧 PostgreSQL projection 伪造成功。
- 新刷新开始或页面卸载时取消旧轮询；Settings 不执行 Mongo/OCR/promotion，不新增第二种 worker event。

### 数据重置

- 支持动作：`reset_bank_transactions`、`reset_invoices`、`reset_oa_and_rebuild`。
- job 状态：`idle`、`confirming`、`queued`、`running`、`succeeded`、`failed`、`cancelled/unavailable`；执行事实源是 `settings.data_reset.requested` durable event 与独立 `settings-maintenance` worker。
- protected targets：`form_data_db.form_data`、`fin_ops_platform_app.app_settings`、`fin_ops_platform_app.*_meta`、`fin_ops_platform_app.import_file_metadata`。
- 允许流转：
  - admin 输入确认密码后，API 创建 job 并只把 job id、owner、action 入队；密码不进入 job/outbox。
  - 页面重进后可恢复 active running job。
  - reset OA 清理完成并可靠登记 lifecycle 后返回 `rebuild_status=pending`；下游按 OA retention cutoff 重建并复用缓存附件发票。
- 禁止流转：
  - 密码缺失/错误或 verification service 失败时清理数据。
  - job payload、错误、日志保存 OA password。
  - 删除 protected targets。
  - reset 后让旧 read model/cache 显示为 fresh。
  - reset 请求/job 线程同步读取 Workbench 全页 payload、OA 行投影或 OCR，并把该结果当成重建完成证明。
  - API 启动生命周期隐式恢复/执行 reset，或 worker 自动重放未知的 interrupted destructive job。

## UI 状态

- loading：settings payload、credential list、active data reset job 并行加载时展示加载态，不能误显示可保存状态。
- empty：无手工项目、无凭据、无 pending invoice 规则时显示空状态，但保留创建入口。
- error：settings save、凭据保存、data reset job、active job 恢复失败必须展示可理解错误。
- job progress：设置页自身不是 read model 页面；显式 data reset job 展示 queued/running/failed/succeeded，OA 精确附件刷新展示 queued/processing/done/failed/dead-lettered。普通规则保存没有下游 refreshing。
- permission disabled/hidden：readonly/full access 非 admin 不显示高风险 credential/reset 入口；API 仍必须二次校验。
- credential form：密码只存在于当前表单；保存成功后清空；列表只展示目标 OA 申请人、OA 登录账号和配置状态。
- reset dialog：必须有动作说明、影响范围、确认密码、运行中 job progress、失败状态和重进恢复。

## Read Model / Worker 状态

- 设置事实本身不是 read model，普通 save 不产生页面 dirty scope/outbox。
- 仅当前 manifest 登记的 `workbench` / `workbench_relation` 可在各自 owner 明确登记的
  reset/maintenance 合同中接收精确 refresh；Settings 不维护第二份 fan-out matrix，也不恢复 Search/no-OA projection。
- Workbench stale scan 只由 matching worker 启动，不属于 API 生命周期；API 初始化不得执行 reset recovery、historical reconcile 或 maintenance。
- settings save 只等待 canonical settings transaction；data reset 单独展示 durable job
  状态，不用 read-model barrier 伪装 job 完成。
- OA 精确附件刷新只复用 `oa.sync` durable queue/status，不写 read-model queue，不等待 operation barrier；worker terminal result 才是解析完成事实。
- 失败恢复：
  - settings 保存失败不得产生半写入 audit 或半更新规则。
  - data reset 失败必须保留可诊断 job 状态，不泄露密码。
  - PostgreSQL 凭据模式保存/读取密码需要 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。

## Access control command 状态

| 状态 | 条件 | I/O 与结果 |
| --- | --- | --- |
| `loaded` | admin GET 成功 | 返回固定管理员、当前 snapshot version 和完整 accounts；非 admin 为 `forbidden`/403 |
| `validation_failed` | DTO、tier、username 或 canonical collision 非法 | 400；在 OA/PG I/O 前失败 |
| `conflict` | critical section 锁定 snapshot 后发现 `expected_version` stale | 409/current_version；保留前端 draft；零 OA/PG 覆盖 |
| `no_op` | 同一锁定 snapshot version 下 memberships 语义相同 | 200/changed=false；零 DB write、audit、OA |
| `oa_target_failed` | 严格 menu/三角色目标未配置、漂移、超时或同步失败 | 502；transaction 回滚，canonical/audit 不变 |
| `persistence_failed_compensated` | OA target 成功，ACL/audit commit 失败且旧 OA memberships 恢复成功 | 503 `access_control_persistence_failed`；canonical/audit 不半写，OA 回到旧 snapshot |
| `commit_recovered` | commit ACK 丢失但 mutation audit 与 version+1 canonical snapshot 一致 | 200/changed=true；不重复提交或补偿 |
| `commit_rolled_back_compensated` | ACK 丢失且确认无 audit/version 未变，旧 OA memberships 恢复成功 | 503 `access_control_persistence_failed`；保持旧 snapshot |
| `compensation_failed_or_unknown` | OA 恢复失败、snapshot 漂移或 commit outcome 无法一致证明 | 503 `access_control_sync_inconsistent`；fail closed，人工核对同一 version、audit 与 OA members |
| `committed` | OA target 与 PostgreSQL ACL/audit transaction 成功 | version +1，canonical ACL/audit 原子提交，下一次 session/API 使用新 snapshot |

管理员身份没有状态迁移：`YNSYLP005` 始终是 protected administrator；任何 APP 请求尝试修改该事实均为非法输入。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-02 | 关闭 generic ACL 提权链 | ACL 独立 API/CAS/audit/OA 补偿；固定 protected admin；删除旧前后端路径 | `tests.test_app_settings_service`、`tests.test_workbench_settings_sync_api`、`web/src/test/SettingsPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts` |
| 2026-08-01 | data reset 迁移到 durable settings-maintenance worker | API 不再持有线程任务；密码不持久化；worker 独立构造 reset 依赖并在完成后安全 reload API runtime | `tests.test_settings_data_reset_job`、`tests.test_runtime_worker_registry` |
| - | 初始骨架 | 待补充 | - |
| 2026-06-10 | 新增 OA 申请人凭据管理后端状态 | 设置页新增独立凭据事实源，admin-only，状态为 `已配置/未配置` | `tests.test_oa_applicant_credentials_service`、`tests.test_oa_applicant_credentials_api`、`tests.test_postgres_oa_applicant_credentials_repository`、`tests.test_postgres_migrations` |
| 2026-06-10 | 落地 OA申请人凭据设置页 UI | 管理员可在设置页维护目标申请人凭据；保存走独立凭据 API；普通 settings save 不包含密码 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` |
| 2026-06-11 | 补齐 settings 测试闭环状态机 | 将项目、权限、规则、OA 凭据、data reset 和 read model/worker fan-out 纳入同一维护边界 | `tests.test_app_settings_service`、`tests.test_settings_data_reset_service`、`web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` |
| 2026-06-16 | 统一 settings mutation API 权限 gate | 项目同步/新增/删除和 OA 手动导入 mutation 必须校验 `can_mutate_data`；有 OA session 时 actor 来自 session，不接受 body 伪造 | `tests.test_workbench_settings_sync_api`、`tests.test_oa_manual_import_api` |
