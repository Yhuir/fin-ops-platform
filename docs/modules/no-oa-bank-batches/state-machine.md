# 免OA流水批量处理 状态机

> Legacy: 新通用方向为 `docs/modules/bank-flow-rule-batches/state-machine.md` 的流水规则批量处理。本文只描述迁移完成前 no-OA 旧模块行为和历史兼容状态。

> 修改 `免OA流水批量处理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

### 标签闭环规则

事实源：

- 银行明细自动标签规则。
- App settings 中的 `no_oa_bank_batch_tag_selection`。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `active` | 当前可用银行自动标签规则 | 左侧只读展示，不允许在 no-OA 抽屉新增、编辑或删除标签 |
| `rule_requires` | 已保存 OA/发票闭环要求 | 可勾选或取消 `OA`、`发票` 要求 |
| `selected` | 兼容状态：`requires_oa=false` 且 `requires_invoice=false` 的标签 | 后续未提交候选纳入该 tag code |
| `inactive_selected` | 历史选择或规则引用但当前停用或不可用 | GET 返回提示；保存或银行标签归档后清理 |
| `version_conflict` | PUT 的 `expected_version` 过期 | 返回 409；不得保存或刷新 |

规则：

- 首次 `selected_tag_codes` 为空数组，不自动放行所有标签。
- `rules` 是主合同；旧 `selected_tag_codes` 只兼容为这些标签 `requires_oa=false` 且 `requires_invoice=false`。
- 新增银行自动标签默认 `requires_oa=true` 且 `requires_invoice=true`，避免新增标签自动进入免 OA 未提交候选或关联台已配对。
- `selected_tag_codes` 可为空，表示免 OA 页面暂不生成新的未提交候选。
- 免 OA 标签规则不保存外部往来第三层分类字段。
- 自动标签规则变更时，已停用引用必须从 no-OA tag selection 中移除并审计。
- no-OA 抽屉左侧 `收支类型 / 流水主标签 / 流水子标签` 只来自银行明细自动标签事实源，用户不能在该抽屉新增、编辑或删除标签。

### 批次状态

事实源：

- Bankdetail 分类 facts。
- No OA batch snapshot。
- Workbench pair relation。
- No OA SQL read model。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `draft` | 未提交候选批次；兼容旧 SQL/read model 中 `status=unsubmitted,status_bucket=unsubmitted` 的同义投影 | 可查看 detail；普通候选可选择行提交；internal_transfer 走 batch submit |
| `submitted` | 已提交免 OA 批次并写入 Workbench pair relation | 可撤回 |
| `withdrawn` | 已撤回批次 | 只读；如果源流水仍 current，可重新生成 draft |

内部兼容状态：

| 状态 | 含义 | 公开投影 |
| --- | --- | --- |
| `conflict` | 规则/金额/内部往来配对不唯一或不完整 | 不进入主列表/summary；用户需在银行明细、标签或关系事实源修复后重新生成 draft |
| `stale` | 历史内部异常或源流水缺失诊断状态 | 有 active no-OA relation 时投影为 `submitted` 并允许撤回；无 active relation 时从公开 snapshot 清理。普通银行明细标签变化不得把 submitted batch 转成 stale |
| `superseded` | 历史单行批次被合并替代 | 从公开 snapshot 清理 |

历史兼容归一规则：

- 已保存为 `submitted` 但对应 `relation_mode=no_oa_bank_batch` 的 Workbench relation 已经 `cancelled` 时，公开投影必须转为 `withdrawn`，并关闭 `can_withdraw`。
- 该归一不重新创建 relation，也不恢复源流水候选；如果源流水仍 current，后续由正常候选生成链路重新生成 draft。
- 生产修复只能通过 no-OA lifecycle repair 工具和 `PostgresStateStore.save_no_oa_bank_batches` 保存公开 snapshot，不能直接改数据库表。

候选生成规则：

- 未提交候选只来自当前 tag selection 中 `requires_oa=false` 且 `requires_invoice=false` 的 tag code。
- 未提交候选必须排除被 Workbench active relation 占用的银行流水。
- 已提交历史批次即使标签不再准入，也继续可见并按状态管理。
- 已提交/已撤回批次详情使用提交时冻结的 `row_tag_snapshot`；银行明细当前标签变化只影响新的未提交候选，不覆盖历史批次内流水标签。
- 同月、同银行账户、同 category code 是 submit-selection 的硬约束。
- 前端 API mapper 和后端公开投影必须把旧 `status=unsubmitted,status_bucket=unsubmitted` 归一为 canonical `draft` 语义，并设置为可提交；当前迁移页面操作能力由 `bankFlowRuleBatches/policy.ts` 统一判断，legacy no-OA API/read model 不再拥有前端 policy 边界，避免状态徽标和右侧 checkbox/提交按钮分裂。
- 持久化必须保存公开生命周期 snapshot：`draft/submitted/withdrawn`。`conflict/stale/superseded` 不得继续写入主 read model；生产历史数据用 `repair_no_oa_bank_batch_lifecycle` dry-run/apply 清理。

### Submit Selection

入口：

- `POST /api/no-oa-bank-batches/submit-selection`
- 前端 `submitNoOaBankBatchSelection`

允许流转：

```text
draft candidate rows selected
  -> transaction_ids non-empty and unique
  -> same month + same bank account + same category_code
  -> category_code currently selected by no-requirement rule
  -> submitted no-OA batch
  -> Workbench pair relation relation_mode=no_oa_bank_batch
  -> relation special_metadata carries paired_requires_oa / paired_requires_invoice
  -> no_oa_bank_batch / workbench / influenced read models refresh
```

禁止：

- 跨银行账户选择。
- 跨月份选择。
- 跨 category code 选择。
- 未在当前 no-requirement tag rule 中的 category code。
- 单边 internal transfer 选择。
- 已被 active relation 占用的流水。

### Internal Transfer From Workbench

入口：

- `POST /api/workbench/actions/confirm-link`

规则：

- 选中银行流水全部为 `internal_transfer` 时，后端必须委托 no-OA 批次提交入口。
- 成功事实必须是 `status=submitted` 的 no-OA internal transfer batch，以及 `relation_mode=no_oa_bank_batch` 的 Workbench active pair relation。
- 如果同一组 `row_ids` 已经存在 submitted no-OA internal transfer batch，关联台再次 confirm-link 必须返回同一个 `case_id` 并保持幂等，不能创建第二条 active relation。
- 存量两行 `manual_confirmed` active relation 只有在 `internal_transfer` 已纳入免 OA 标签准入，且全银行流水、同金额、不同账户、收支成对、有效分类均为 `internal_transfer` 时，才作为历史内部往来入口迁移到 submitted no-OA 批次；其他 `manual_confirmed` 关系不归本模块迁移。
- Workbench active pair relation 对 row 是独占事实；不同 active case 不允许复用同一 row。
- 响应保持 Workbench `confirm_link` 兼容 shape。
- 如果选中流水只有部分为 `internal_transfer`，必须返回 `400 no_oa_bank_batch_selection_internal_transfer_conflict`，不得静默写普通 `manual_confirmed`。
- 非 internal transfer 的银行-only 平衡确认仍可保持普通 Workbench `manual_confirmed` 语义。

### Withdraw

入口：

- `POST /api/no-oa-bank-batches/{batch_id}/withdraw`

允许流转：

```text
submitted no-OA batch
  -> expected_version matches
  -> reason provided
  -> pair relation cancelled
  -> batch status withdrawn
  -> no_oa_bank_batch_changed lifecycle + read model refresh
```

禁止：

- 从 Workbench 绕过批次直接撤回 no-OA relation。
- stale expected version。
- 未知 batch。
- 非 submitted 或不可撤回状态。
- 空撤回原因。

## UI 状态

| 状态 | 当前行为 | 测试入口 |
| --- | --- | --- |
| loading | 首次加载、月份/bucket 变化时显示加载 | `web/src/test/BankFlowRuleBatchPage.test.tsx` |
| empty | 未选择标签或当前筛选无批次时显示空态 | page tests |
| error | list/detail/tag/submit/withdraw API 失败显示反馈 | API/page tests |
| stale/refreshing | `readModelStatus !== "fresh"` 时保持当前 rows 可见并后台轮询 | `shows read model stale state and reloads until the no OA read model is fresh` |
| route inactive | 页面卸载或 inactive 后停止 stale polling / event replay | `cleans up stale read model retry reload after route unmount`、`useActiveFinanceDomainEvent` tests |
| permission disabled | 无 mutation 权限时提交、撤回、保存标签不可用或 API 403 | route/API tests |
| tag drawer | 打开时重新 fetch tag selection；保存后 reload list | tag drawer tests |
| selection guard | 只允许一个银行账户区域的 rows 同时被选择 | `prevents selecting rows from another bank before clearing the current bank region` |
| ordinary row selection | 普通未提交 draft 语义批次显示行级 checkbox；兼容旧 `status=unsubmitted` 投影；不受旧批次级 `can_submit` flag 控制 | `keeps draft row selection available when legacy read model rows omit can_submit`、`keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status`、`BankFlowRuleBatchPolicy.test.ts` |
| public lifecycle filter | `status=stale/conflict/superseded` 为内部兼容/诊断状态，不进入未提交主列表、summary 或 pagination；生产历史行通过 public snapshot/repair 清理 | `filters unsubmitted stale batches out of the main list`、`does not expose internal transfer conflicts in the main list` |
| internal transfer action | internal_transfer draft 走 batch submit endpoint，不走 selected rows submit | `submits internal transfer draft batches through the batch endpoint` |
| operation pending | submit-selection、submit、withdraw、tag-selection 保存成功后显示全屏 overlay，等待 `no_oa_bank_batch` operation barrier fresh，再 reload list/detail/tag selection | operation overlay / page tests |
| relation-backed stale projection | SQL read model 返回 `status=stale` 且 `status_bucket=submitted` 或 `can_withdraw=true` 时，list/detail/mutation payload 和前端 mapper 对用户投影为 `submitted`，清空复核类阻断提示，仍显示撤回入口 | `test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`、`presents relation-backed stale batches as submitted without review prompts` |
| withdrawn history | 历史 bucket 只读，不显示提交/撤回动作 | `shows withdrawn history as read-only` |

前端跨页事件：

- submit/withdraw 成功后发 `workbenchRelationUpdated`，携带 `affectedMonths`。
- `bankTransactionCategoryUpdated` 和 `bankAutoTagRulesUpdated` 会刷新 tag selection、list 和 detail cache。
- 事件只作为同浏览器刷新提示；一致性事实源仍是后端 dirty/outbox/read model freshness。

## Read Model / Worker 状态

Read model key：`no_oa_bank_batch`

Scope type：`no_oa_bank_batch`

Scope key：`all` 或 `YYYY-MM`。`all` 表示全量 snapshot 重建；月份 scope 只读取目标月银行流水，并在保存前与其它月份现有批次合并，不能删除其它月份批次。

Worker instance：`no-oa-bank-batch`

Refresh event：`no_oa_bank_batch.read_model.refresh`

状态：

| 状态 | 含义 | 页面/API 行为 |
| --- | --- | --- |
| `fresh` | SQL read model 与当前 source versions 一致 | 正常展示和允许可用写动作 |
| `refreshing` | 后台刷新中 | 前端保持当前 rows，后台重试 |
| `stale` | source versions 不一致 | API 返回当前可用 rows + stale reasons + refresh enqueue |
| `missing` | SQL read model 缺失 | API 返回空 payload + refresh enqueue，不同步重建 |
| `schema_mismatch` | read model schema 不兼容 | 按非 fresh 处理，等待 worker 重建 |
| `unavailable` | repository/queue 不可用 | App Status 不得 green，页面按错误或 busy/blocked 处理 |
| `failed` | worker/readiness 失败 | App Status domain blocked |

refresh 触发来源：

- tag selection 保存。
- submit-selection / submit batch / bulk submit。
- withdraw。
- bank auto tag rules changed。
- bank transaction category changed。
- Workbench confirm-link internal transfer path。
- runtime repair。
- `startup_stale_scan` 默认关闭；启用时只标记 stale workbench matching dirty scopes，不直接刷新免 OA read model。

worker 流程：

```text
job.outbox_events / job.read_model_dirty_scopes
  -> no-oa-bank-batch worker consumes no_oa_bank_batch.read_model.refresh
  -> NoOaBankBatchReadModelRefreshService.handle_runtime_event
  -> 读取目标 scope 银行流水、Bankdetail tag read model 和 Workbench relation source_versions metadata
  -> 如果现有 SQL read model source_versions summary 与当前依赖 source_versions 完全一致，skip rebuild，只 complete dirty scope
  -> 否则 NoOaBankBatchApplicationService.refresh_batches_from_prepared_rows(scope_key)
  -> all scope: 读取全量银行流水并生成完整 no-OA snapshot
  -> YYYY-MM scope: 只读取目标月银行流水，只替换目标月批次，保留其它月份批次
  -> scoped persistence 保存合并后的 public snapshot，并删除 snapshot 缺席批次行
  -> complete dirty scope and readiness
```

失败恢复：

- worker handler event type 或 scope type 错误必须拒绝。
- stale source version event 必须 skip，不得 rebuild 或覆盖 read model。
- unchanged source_versions event 必须 skip，不得 rebuild 或覆盖 read model；skip 前必须已经读取 Bankdetail 和 Workbench relation 依赖 source_versions，但不得为了 skip proof 加载完整 relation rows 或 no-OA batch payload rows。
- 读取 Bankdetail tag/read model 时遇到 `*_read_model_not_fresh` 必须保持 `refreshing`/defer，不得把 no-OA readiness 标记为 `failed`。
- GET list/detail 不得为了 missing/stale 同步 rebuild 全量批次。
- 本地测试不能证明真实 RabbitMQ/Redis/systemd drain，发布前按运维 smoke 验证。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐免 OA 流水批量处理状态机 | 固定 tag selection、batch lifecycle、internal transfer from Workbench、UI stale polling、read model/worker 状态 | 待本轮模块验证命令 |
| 2026-06-11 | 固定内部往来双入口闭环 | Workbench/no-OA 同一组内部往来幂等复用同一 no-OA fact；存量两行 manual internal-transfer relation 迁移；active relation row 独占；SQL read model 保存清理缺席旧批次 | `pytest` no-OA service/workbench integration、pair relation service 目标用例 |
| 2026-06-14 | no-OA 月度 read model refresh 和依赖未 fresh 状态收敛 | `no_oa_bank_batch` scope policy 支持 `all`/月份；月度 worker 不全量读取、不删除其它月份批次；Bankdetail 依赖未 fresh 时记录 refreshing，不再污染 failed blocker | `tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_workbench_integration`、`tests.test_read_model_readiness_reporter`、`tests.test_read_model_refresh_gateway` |
| 2026-06-14 | submit/withdraw/tag-selection 接入 operation overlay 与 freshness barrier | 写 API 成功后等待 `no_oa_bank_batch` barrier fresh 并 reload，避免旧批次/旧候选暴露给用户 | `web/src/test/BankFlowRuleBatchPage.test.tsx`、`web/src/test/OperationBarrierApi.test.ts` |
| 2026-06-17 | Browser e2e 补齐选择提交/撤回/历史只读闭环 | 真实 Chromium 保护未提交选择、`submit-selection` 请求体、operation barrier、已提交 bucket 撤回 dialog、withdraw 请求体和历史只读状态 | `cd web && npx playwright test e2e/bank-flow-rule-batches-flow.spec.ts` |
| 2026-06-17 | read-only 写入口门禁接入权限矩阵 | `read_export_only` 用户可查看批次和标签范围，但不能提交、撤回、批量勾选或保存 tag selection；权限矩阵归 `permissions-and-audit` 统一覆盖 | `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`、`cd web && npm test -- --run src/test/BankFlowRuleBatchPage.test.tsx` |
| 2026-06-17 | relation-backed stale 用户可见状态收敛 | SQL read model 中仍有 active no-OA relation 的旧 `stale` 批次按已提交展示并可撤回；页面不显示“分类已变更，需复核”提示 | `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`、`web/src/test/BankFlowRuleBatchPage.test.tsx` |
| 2026-06-23 | read-side manifest 合同守卫 | 仅锁定 `no_oa_bank_batch` 的 self-managed freshness、`scoped_incremental`、fan-out `all`、`no-oa-bank-batch` worker、query/permission owner 和 repository port；不改变业务/UI/read model/worker 状态定义 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts` |
| 2026-06-26 | unchanged source_versions worker fast-path | worker 从 state_store 注入 no-OA SQL read repository，先读取 Bankdetail tag 与 Workbench relation metadata source_versions，再比较现有 SQL source_versions summary；一致时只 complete dirty scope，不 rebuild、不保存 snapshot、不加载完整 relation rows/batch payload rows | `tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_unchanged_scope_skips_rebuild_and_snapshot_save` |
| 2026-06-26 | submitted + cancelled relation 历史归一 | 历史 `submitted` 批次若其 no-OA Workbench relation 已取消，public snapshot 归一为 `withdrawn` 且不可撤回，避免页面把已撤回历史误当可撤回样本 | `tests/test_no_oa_bank_batch_lifecycle_repair.py::test_public_lifecycle_repair_normalizes_cancelled_submitted_relation_to_withdrawn` |
