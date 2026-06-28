# 批量账务 状态机

> 修改 `批量账务` 相关业务状态、UI 状态或后台任务状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

| 状态 | 含义 | 事实源 |
| --- | --- | --- |
| `unsubmitted` | 银行流水符合批量账务条件，且当前没有 active relation 占用；右侧展示可选日常报销 OA 行。 | BatchAccounting direct payload + canonical relation facts |
| `submitted` | 银行流水存在 active batch accounting relation；右侧展示该关系下的 OA 行，只允许撤回。 | Workbench pair relation + relation distribution |
| `outdated/conflict` | 前端持有的 bank row 或 relation version 已落后，提交/撤回应失败并要求刷新。 | `expected_version`、active relation version |
| `mismatch_pending_note` | 银行金额与选中 OA 合计不一致，尚未填写有效差额说明。 | 前端选择状态 + `BatchAccountingService` 金额校验 |
| `mismatch_closed` | 金额不一致但已填写差额说明，提交后视为人工差额闭环。 | batch relation history / `special_metadata` |
| `withdrawn` | 批量账务关系撤回，历史保留；只恢复真实 relation snapshot，OA 附件 case_id / `existing_case` 显示归属回到读侧分组，不恢复成 active relation。 | Workbench pair relation history |

### 允许流转

- `unsubmitted -> submitted`：选择一个合法银行流水、至少一个合法 OA 行；金额不一致时必须提供 trim 后非空差额说明；`expected_version` 必须匹配。
- `submitted -> withdrawn`：只能撤回 active batch accounting relation；必须提供 trim 后非空撤回原因；`expected_version` 必须匹配。
- `withdrawn -> unsubmitted`：撤回成功并完成页面重读后，该银行/OA 行重新按 Workbench/关系事实归类。
- `outdated/conflict -> unsubmitted/submitted`：用户刷新，API 返回最新 payload 后按事实源重新归桶。

### 禁止流转

- 页面不展示 旧投影同步状态 状态；submit/withdraw 后端必须执行 canonical relation write safety、owner 状态、权限/session、idempotency 和 DB 可写性校验。
- 已有关联关系占用的银行流水不能再次作为 `unsubmitted` 提交。
- 非日常报销 OA 行、已有关联关系的 OA 行、空 OA 列表、空银行流水 ID、非法年份或非法 bucket 必须拒绝。
- 金额不一致但差额说明为空或仅空白字符时必须拒绝。
- 非 batch accounting relation 不能通过批量账务撤回接口撤回。
- GET 列表路径禁止执行 legacy relation repair 或其他写操作。

## UI 状态

| 状态 | 页面行为 |
| --- | --- |
| loading | 初次加载和刷新时显示 `StatePanel` loading，不提交当前选择。 |
| empty | 银行列表或 OA 表无行时分别展示空态。 |
| error | GET 失败时显示页面错误 fallback；mutation 失败通过 feedback 展示错误信息。 |
| ready | 可按 bucket 操作；unsubmitted 可提交，submitted 可打开撤回 dialog。 |
| mismatch | 显示金额不一致提示和差额说明输入；说明为空时前端阻止提交，后端再次校验。 |
| bucket 切换 | `unsubmitted` 与 `submitted` 切换时清空 bank/OA selection、差额说明、撤回状态。 |
| OA 年份切换 | 只切换 OA 年份时尽量保留仍存在的选中银行/OA 行；刷新后不存在的行必须清理。 |
| search/filter | 右侧 OA 搜索只过滤展示，不改变后端事实或已选中金额。 |
| operation pending | submit/withdraw API 成功后显示全屏 overlay，直接重新加载当前 bucket。 |
| submit success | reload 完成后显示成功 feedback，发送 `workbenchRelationUpdated`。 |
| withdraw success | reload 完成后关闭撤回 dialog，显示成功 feedback，发送 `workbenchRelationUpdated`。 |
| permission disabled/hidden | 当前没有独立权限开关；若后续接入权限，必须同时覆盖 API 403 和前端 hidden/disabled。 |

## 后端 Relation 读取 / 后台状态

| 状态 | 含义 | 批量账务处理 |
| --- | --- | --- |
| `available` | 后端能从 canonical relation facts 组装当前 relation context。 | 后端可用于当前关系分布；提交/撤回仍按 canonical write safety 校验。 |
| `unavailable` | canonical relation context 不可确认。 | 不进入批量账务 GET/submit/withdraw payload；写入口返回业务级 relation unavailable/conflict，不返回 旧投影同步状态 字段。 |

写后影响来源：

- 当前后端批量账务列表读取通过 `WorkbenchRelationReadFacade` 的 canonical relation context；GET/submit/withdraw 合同不透出 同步状态/status/scope。
- 批量账务提交/撤回：`batch_accounting_relation_changed` -> direct reload / relation outbox /真实下游后台任务；不再调度 Workbench page-level 旧投影 persist。
- 关联台关系确认/撤回：`pair_relation_changed`。
- 银行流水或发票导入、OA rebuild、标签规则等影响 canonical relation/direct payload 的生命周期事件。
- backfill / runtime worker retry 只处理真实后台任务，不作为页面 旧投影同步状态 proof。
- `startup_stale_scan` 默认关闭，且不刷新 `workbench_relation` page-level 旧投影；它只标记 Workbench matching dirty scopes。

失败恢复：

1. 先检查 BatchAccounting direct GET、canonical relation facts、relation outbox、真实后台任务和 worker heartbeat。
2. 确认 `batch_accounting_relation_changed` lifecycle/direct reload 事件存在；不要恢复 removed workbench relation worker。
3. 对失败的真实后台任务按其 job/outbox 语义重试；不要通过页面 GET 同步 rebuild 或重新入队 page-level 旧投影。
4. 修复 source/schema 后重新读取 direct payload；页面不能把暂不可用的空关系当真实空，但普通 relation distribution 诊断不应全局阻断具备 canonical write safety 的 mutation。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-28 | BatchAccounting route owner 删除 Workbench page-level 旧投影 persist callback | submit/withdraw 写后只发 `batch_accounting_relation_changed` lifecycle/direct reload，不再接收或调用 `schedule_read_model_persist` | `tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-27 | 移除 BatchAccounting GET/submit/withdraw 旧投影状态 合同 | 后端不再返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`，写操作不再被普通 relation distribution 同步状态 阻断 | `PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q` |
| 2026-06-26 | 移除 BatchAccounting 页面写后 旧操作屏障 等待 | submit/withdraw 成功后直接重读页面 payload；页面不再调用 `/api/operation-barrier/status` | `web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts`、docs verify |
| 2026-06-24 | 删除无调用者的 app-level repair helper：`Application._repair_batch_accounting_relation_case_ids(...)` 不再存在；service-level `repair_legacy_case_id_collisions(...)` 保留 | 移除 unused legacy write wrapper；业务/UI/旧投影/worker 状态定义不变 | 静态 route/repair guard、GET 只读回归、service repair command-boundary tests |
| 2026-06-24 | Submit/withdraw route owner 抽取：mutation session/JSON 仍在 `server.py`，DTO/service/error mapping 与写后 scope/lifecycle orchestration 进入 `BatchAccountingApiRoutes` 显式 callback 边界 | route ownership 变化；业务/UI/后台任务状态定义不变；2026-06-28 起该 route owner 不再接 Workbench page-level 旧投影 persist callback | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_route_handlers_do_not_bypass_service_boundaries`、批量账务 submit/withdraw API 回归 |
| 2026-06-23 | Route handler 边界守卫：GET 只能委托 `BatchAccountingService.build_payload(...)`，不得执行 repair/write/旧投影 schedule；submit/withdraw route 必须经 mutation session 并委托 service，不得 direct relation write | `server.py` 批量账务 route ownership；不改变业务/UI/后台任务状态定义 | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` |
| 2026-06-11 | 首轮测试闭环状态机补齐 | 明确业务、UI、relation 旧投影、worker 状态和禁止流转 | `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、relation facade/projection tests |
| 2026-06-11 | relation 旧投影 missing/stale 闭环 | 历史行为；已由 2026-06-27 删除页面/API status 字段透出。 | 历史测试已替换为字段缺失断言 |
| 2026-06-13 | 写安全改为默认 canonical relation gate | 普通 relation distribution 诊断只作为读侧诊断；submit/withdraw 默认由 relation command service、owner 状态、权限/session、DB 可写性、version/idempotency 决定 | `tests/test_workbench_relation_command_service.py`、`tests/test_batch_accounting_api.py` |
| 2026-06-14 | submit/withdraw 接入 operation overlay 与 旧同步等待 | 历史实现：写 API 成功后等待 `workbench_relation` 旧等待完成 并 reload；已被 2026-06-26 direct reload 合同取代 | `web/src/test/BatchAccountingPage.test.tsx` |
