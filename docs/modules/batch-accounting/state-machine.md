# 批量账务 状态机

> 修改 `批量账务` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

| 状态 | 含义 | 事实源 |
| --- | --- | --- |
| `unsubmitted` | 银行流水符合批量账务条件，且当前没有 active relation 占用；右侧展示可选日常报销 OA 行。 | Workbench payload + `workbench_relation` read model |
| `submitted` | 银行流水存在 active batch accounting relation；右侧展示该关系下的 OA 行，只允许撤回。 | Workbench pair relation + relation distribution |
| `stale/conflict` | 前端持有的 bank row 或 relation version 已落后，提交/撤回应失败并要求刷新。 | `expected_version`、active relation version |
| `mismatch_pending_note` | 银行金额与选中 OA 合计不一致，尚未填写有效差额说明。 | 前端选择状态 + `BatchAccountingService` 金额校验 |
| `mismatch_closed` | 金额不一致但已填写差额说明，提交后视为人工差额闭环。 | batch relation history / `special_metadata` |
| `withdrawn` | 批量账务关系撤回，历史保留；只恢复真实 relation snapshot，OA 附件 case_id / `existing_case` 显示归属回到读侧分组，不恢复成 active relation。 | Workbench pair relation history |

### 允许流转

- `unsubmitted -> submitted`：选择一个合法银行流水、至少一个合法 OA 行；金额不一致时必须提供 trim 后非空差额说明；`expected_version` 必须匹配。
- `submitted -> withdrawn`：只能撤回 active batch accounting relation；必须提供 trim 后非空撤回原因；`expected_version` 必须匹配。
- `withdrawn -> unsubmitted`：撤回成功并完成 relation read model 刷新后，该银行/OA 行重新按 Workbench/关系事实归类。
- `stale/conflict -> unsubmitted/submitted`：用户刷新，API 返回 fresh payload 后按事实源重新归桶。

### 禁止流转

- `read_model_status !== "fresh"` 时不能把空关系显示为真实未提交，但不得仅因普通 relation distribution non-fresh 禁止提交和撤回；submit/withdraw 后端必须执行 canonical relation write safety、owner 状态、权限/session、idempotency 和 DB 可写性校验。
- 已有关联关系占用的银行流水不能再次作为 `unsubmitted` 提交。
- 非日常报销 OA 行、已有关联关系的 OA 行、空 OA 列表、空银行流水 ID、非法年份或非法 bucket 必须拒绝。
- 金额不一致但差额说明为空或仅空白字符时必须拒绝。
- 非 batch accounting relation 不能通过批量账务撤回接口撤回。
- GET 列表路径禁止执行 legacy relation repair 或其他写操作。

## UI 状态

| 状态 | 页面行为 |
| --- | --- |
| loading | 初次加载和刷新时显示 `StatePanel` loading，不提交当前选择。 |
| empty | 银行列表或 OA 表无行时分别展示空态；空态不能替代 non-fresh warning。 |
| error | GET 失败时显示页面错误 fallback；mutation 失败通过 feedback 展示错误信息。 |
| fresh | 可按 bucket 操作；unsubmitted 可提交，submitted 可打开撤回 dialog。 |
| stale/refreshing/missing/failed/unavailable | 显示 relation read model warning、后端 stale reason 和 scope；提交/撤回按钮禁用；用户可刷新等待 worker 收敛。`refresh_enqueued=false` 时提示刷新未入队并转向系统状态排查。 |
| mismatch | 显示金额不一致提示和差额说明输入；说明为空时前端阻止提交，后端再次校验。 |
| bucket 切换 | `unsubmitted` 与 `submitted` 切换时清空 bank/OA selection、差额说明、撤回状态。 |
| OA 年份切换 | 只切换 OA 年份时尽量保留仍存在的选中银行/OA 行；刷新后不存在的行必须清理。 |
| search/filter | 右侧 OA 搜索只过滤展示，不改变后端事实或已选中金额。 |
| submit success | 显示成功 feedback，发送 `workbenchRelationUpdated`，重新加载当前 bucket。 |
| withdraw success | 关闭撤回 dialog，显示成功 feedback，发送 `workbenchRelationUpdated`，重新加载当前 bucket。 |
| permission disabled/hidden | 当前没有独立权限开关；若后续接入权限，必须同时覆盖 API 403 和前端 hidden/disabled。 |

## Read Model / Worker 状态

| 状态 | 含义 | 批量账务处理 |
| --- | --- | --- |
| `fresh` | `workbench_relation` read model 与 source version 一致。 | 读侧可直接展示；提交/撤回仍按 canonical write safety 校验。 |
| `refreshing` | refresh 已入队或正在运行。 | API 可返回当前 payload 和 freshness 诊断；普通 refreshing 不应全局禁用具备 canonical write safety 的 mutation。 |
| `stale` | projection source version 落后。 | API 透出 stale reason/scope key；不能把空关系当真实空，mutation 阻断由 canonical write safety 决定。 |
| `missing` | 目标 scope 尚无 relation read model。 | facade/gateway enqueue refresh；mutation 默认不因普通 distribution missing 被 fresh gate 拒绝。 |
| `failed` | 最近 refresh 失败。 | App Status 标记读侧失败；只有目标写模型不可用或 write safety 不可确认时才阻断 mutation。 |
| `schema_mismatch` | read model schema 版本不匹配。 | 读侧必须重建后才能声明 fresh；写侧仍看 canonical write safety。 |
| `unavailable` | SQL runtime 或 repository 不可用。 | 不能展示为 green/fresh；需要 App Health/App Status 暴露。 |

Refresh 触发来源：

- 批量账务列表读取：通过 `WorkbenchRelationReadFacade` 以 `require_fresh=true` 请求 relation read model；缺失/stale scope 经现有 freshness/gateway 边界去重入队，GET 不同步 rebuild、不直接写 queue。
- 批量账务提交/撤回：`batch_accounting_relation_changed` -> `workbench_relation_read_model` invalidate/refresh。
- 关联台关系确认/撤回：`pair_relation_changed`。
- 银行流水或发票导入、OA rebuild、标签规则等影响 Workbench relation 的生命周期事件。
- backfill / runtime worker retry。
- `startup_stale_scan` 默认关闭，且不直接刷新 `workbench_relation` read model；它只标记 workbench matching dirty scopes。

失败恢复：

1. 先检查 App Status 中 `workbench_relation` read model readiness、dirty backlog、worker heartbeat。
2. 确认 `workbench-relation` worker 注册和 `workbench_relation.read_model.refresh` event 存在。
3. 对缺失或 stale scope 重新入队；不要通过页面 GET 同步 rebuild。
4. 修复 source/schema 后重新刷新；页面不能把 non-fresh 空关系当真实空，但 ordinary non-fresh 不应全局阻断具备 canonical write safety 的 mutation。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 首轮测试闭环状态机补齐 | 明确业务、UI、relation read model、worker 状态和禁止流转 | `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、relation facade/projection tests |
| 2026-06-11 | relation read model missing/stale 闭环 | 列表读取走 require_fresh 入队；页面展示 reason/scope 和未入队提示。写阻断口径已由 2026-06-13 canonical write safety 更新替代。 | `test_unsubmitted_list_requires_fresh_relation_read_model_to_enqueue_missing_refresh`、`test_submitted_list_requires_fresh_relation_read_model_to_enqueue_stale_refresh` |
| 2026-06-13 | 写安全改为默认 canonical relation gate | 普通 relation distribution non-fresh 只作为读侧诊断；submit/withdraw 默认由 relation command service、owner 状态、权限/session、DB 可写性、version/idempotency 决定 | `tests/test_workbench_relation_command_service.py`、`tests/test_batch_accounting_api.py` |
