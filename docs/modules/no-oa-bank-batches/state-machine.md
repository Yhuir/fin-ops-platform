# 免OA流水批量处理 状态机

> 修改 `免OA流水批量处理` 相关业务状态、UI 状态、direct API 数据流或 legacy projection 清理状态前必须读取本文件。

## 业务状态

### 标签准入

事实源：

- 银行明细自动标签规则。
- App settings 中的 `no_oa_bank_batch_tag_selection`。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `active` | 当前可用银行自动标签规则 | 可被选择或取消 |
| `selected` | 已保存为免 OA 候选准入标签 | 后续未提交候选纳入该 tag code |
| `inactive_selected` | 历史选择但当前停用或不可用 | GET 返回提示；保存后清理 |
| `version_conflict` | PUT 的 `expected_version` 过期 | 返回 409；不得保存，页面需重新读取当前版本 |

规则：

- 首次 `selected_tag_codes` 为空数组，不自动选中所有标签。
- `selected_tag_codes` 可为空，表示暂不生成新的未提交候选。
- 免 OA 标签准入不保存外部往来第三层分类字段。
- 自动标签规则变更时，已停用引用必须从 no-OA tag selection 中移除并审计。

### 批次状态

事实源：

- Bankdetail 分类 facts。
- No OA batch snapshot。
- Workbench pair relation。
- No OA public snapshot / historical SQL projection cleanup.

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `draft` | 未提交候选批次；兼容旧 SQL projection 中 `status=unsubmitted,status_bucket=unsubmitted` 的同义投影 | 可查看 detail；普通候选可选择行提交；internal_transfer 走 batch submit |
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

- 未提交候选只来自当前 tag selection 中的 tag code。
- 未提交候选必须排除被 Workbench active relation 占用的银行流水。
- 已提交历史批次即使标签不再准入，也继续可见并按状态管理。
- 已提交/已撤回批次详情使用提交时冻结的 `row_tag_snapshot`；银行明细当前标签变化只影响新的未提交候选，不覆盖历史批次内流水标签。
- 同月、同银行账户、同 category code 是 submit-selection 的硬约束。
- 前端 API mapper 和后端公开投影必须把旧 `status=unsubmitted,status_bucket=unsubmitted` 归一为 canonical `draft` 语义，并设置为可提交；页面操作能力由 `noOaBankBatches/policy.ts` 统一判断，避免状态徽标和右侧 checkbox/提交按钮分裂。
- 持久化必须保存公开生命周期 snapshot：`draft/submitted/withdrawn`。`conflict/stale/superseded` 不得继续写入公开主列表；生产历史数据用 `repair_no_oa_bank_batch_lifecycle` dry-run/apply 清理。

### Submit Selection

入口：

- `POST /api/no-oa-bank-batches/submit-selection`
- 前端 `submitNoOaBankBatchSelection`

允许流转：

```text
draft candidate rows selected
  -> transaction_ids non-empty and unique
  -> same month + same bank account + same category_code
  -> category_code currently selected
  -> submitted no-OA batch
  -> Workbench pair relation relation_mode=no_oa_bank_batch
  -> no_oa_bank_batch_changed lifecycle event + direct page refetch
```

禁止：

- 跨银行账户选择。
- 跨月份选择。
- 跨 category code 选择。
- 未在当前 tag selection 中的 category code。
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
  -> no_oa_bank_batch_changed lifecycle event + direct page refetch
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
| loading | 首次加载、月份/bucket 变化时显示加载 | `web/src/test/NoOaBankBatchPage.test.tsx` |
| empty | 未选择标签或当前筛选无批次时显示空态 | page tests |
| error | list/detail/tag/submit/withdraw API 失败显示反馈 | API/page tests |
| direct list | 页面直接消费业务 rows/summary/pagination，不消费旧同步状态，也不做基于 legacy projection 的后台轮询 | `keeps visible rows without page-level read model polling` |
| route inactive | 页面卸载或 inactive 后停止 domain event replay | `useActiveFinanceDomainEvent` tests |
| permission disabled | 无 mutation 权限时提交、撤回、保存标签不可用或 API 403 | route/API tests |
| tag drawer | 打开时重新 fetch tag selection；保存后 refetch list | tag drawer tests |
| selection guard | 只允许一个银行账户区域的 rows 同时被选择 | `prevents selecting rows from another bank before clearing the current bank region` |
| ordinary row selection | 普通未提交 draft 语义批次显示行级 checkbox；兼容旧 `status=unsubmitted` 投影；不受旧批次级 `can_submit` flag 控制 | `keeps draft row selection available when legacy read model rows omit can_submit`、`keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status`、`NoOaBankBatchPolicy.test.ts` |
| public lifecycle filter | `status=stale/conflict/superseded` 为内部兼容/诊断状态，不进入未提交主列表、summary 或 pagination；生产历史行通过 public snapshot/repair 清理 | `filters unsubmitted stale batches out of the main list`、`does not expose internal transfer conflicts in the main list` |
| internal transfer action | internal_transfer draft 走 batch submit endpoint，不走 selected rows submit | `submits internal transfer draft batches through the batch endpoint` |
| operation pending | submit-selection、submit、withdraw、tag-selection 保存成功后显示全屏 overlay，direct refetch list/detail/tag selection，且不得请求 operation barrier 或 legacy target wait | operation overlay / page tests |
| relation-backed stale projection | 旧 snapshot 返回 `status=stale` 且 `status_bucket=submitted` 或 `can_withdraw=true` 时，list/detail/mutation payload 和前端 mapper 对用户投影为 `submitted`，清空复核类阻断提示，仍显示撤回入口；页面 list 不再从 SQL read model 取数 | `test_list_batches_uses_direct_service_not_read_model_repository`、`presents relation-backed stale batches as submitted without review prompts` |
| withdrawn history | 历史 bucket 只读，不显示提交/撤回动作 | `shows withdrawn history as read-only` |

前端跨页事件：

- submit/withdraw 成功后发 `workbenchRelationUpdated`，携带 `affectedMonths`。
- `bankTransactionCategoryUpdated` 和 `bankAutoTagRulesUpdated` 会触发 tag selection、list 和 detail cache refetch。
- 事件只作为同浏览器 refetch 提示；一致性事实源是后端 canonical facts、relation/outbox 和 direct API 重新读取结果。

## Legacy Projection / Worker 清理状态

no-OA 页面不再拥有 page-level projection runtime。以下运行时对象已删除：

- legacy key / scope type：`no_oa_bank_batch`
- worker instance：`no-oa-bank-batch`
- refresh event：`no_oa_bank_batch.read_model.refresh`
- repository/worker/producer：`no_oa_bank_batch_read_model_repository.py`、`no_oa_bank_batch_read_model_refresh.py`、`no_oa_bank_batch_read_model_refresh_producer.py`

现行规则：

- `GET /api/no-oa-bank-batches` list/detail 只从 `NoOaBankBatchService` 和 direct relation/category providers 组装业务 payload。
- tag selection、submit、withdraw 和 Workbench internal transfer 写入后只触发 canonical fact 更新、audit、Workbench/cost/search 等真实下游 lifecycle；不得写 no-OA page projection scope 或 outbox event。
- App Status 的 `no_oa_bank_batches` domain 不绑定 no-OA page projection worker/readiness/job type。
- 生产历史修复仍通过 no-OA lifecycle repair / legacy relation migration 的业务边界执行，不通过 read-model refresh worker。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐免 OA 流水批量处理状态机 | 固定 tag selection、batch lifecycle、internal transfer from Workbench、legacy projection/worker 清理状态 | 待本轮模块验证命令 |
| 2026-06-11 | 固定内部往来双入口闭环 | Workbench/no-OA 同一组内部往来幂等复用同一 no-OA fact；存量两行 manual internal-transfer relation 迁移；active relation row 独占；SQL read model 保存清理缺席旧批次 | `pytest` no-OA service/workbench integration、pair relation service 目标用例 |
| 2026-06-14 | no-OA 月度 read model refresh 和依赖未 fresh 状态收敛 | 历史 worker/runtime 行为，已于 2026-06-28 随 no-OA page read-model family 删除 | 历史记录 |
| 2026-06-14 | submit/withdraw/tag-selection 接入 operation overlay 与旧 barrier | 历史实现：写 API 成功后等待 `no_oa_bank_batch` barrier 并 reload，避免旧批次/旧候选暴露给用户；2026-06-27 后页面合同已迁移为直接业务 payload/refetch，不再消费旧同步字段 | `web/src/test/NoOaBankBatchPage.test.tsx` |
| 2026-06-17 | Browser e2e 补齐选择提交/撤回/历史只读闭环 | 真实 Chromium 保护未提交选择、`submit-selection` 请求体、已提交 bucket 撤回 dialog、withdraw 请求体、direct refetch 和历史只读状态；旧 operation barrier 断言已删除 | `cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts` |
| 2026-06-17 | read-only 写入口门禁接入权限矩阵 | `read_export_only` 用户可查看批次和标签范围，但不能提交、撤回、批量勾选或保存 tag selection；权限矩阵归 `permissions-and-audit` 统一覆盖 | `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`、`cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx` |
| 2026-06-17 | relation-backed stale 用户可见状态收敛 | 旧 snapshot 中仍有 active no-OA relation 的旧 `stale` 批次按已提交展示并可撤回；页面不显示“分类已变更，需复核”提示；页面 list 不再从 SQL read model 取数 | `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_list_batches_uses_direct_service_not_read_model_repository`、`web/src/test/NoOaBankBatchPage.test.tsx` |
| 2026-06-23 | read-side manifest 合同守卫 | 历史 no-OA manifest/worker 合同，已于 2026-06-28 删除；当前 guard 断言 no-OA manifest entry 不存在 | `tests/test_read_model_manifest.py` |
| 2026-06-26 | unchanged source_versions worker fast-path | 历史 no-OA worker fast-path，已于 2026-06-28 删除；当前页面 list 直接读取业务事实，不再需要 read-model source_versions skip | 历史记录 |
| 2026-06-28 | no-OA page read-model runtime family removed | 删除 no-OA page read-model repository/refresh worker/producer、runtime worker/App Status/readiness/manifest/scope policy/deploy/env/UoW outbox 绑定；页面保持 direct service list/detail | `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_workbench_integration.py tests/test_bankdetail_write_uow_contract.py tests/test_app_status_overview_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_runtime_worker_registry.py tests/test_read_model_manifest.py tests/test_platform_runtime_boundary_guards.py -q --tb=short` |
| 2026-06-26 | submitted + cancelled relation 历史归一 | 历史 `submitted` 批次若其 no-OA Workbench relation 已取消，public snapshot 归一为 `withdrawn` 且不可撤回，避免页面把已撤回历史误当可撤回样本 | `tests/test_no_oa_bank_batch_lifecycle_repair.py::test_public_lifecycle_repair_normalizes_cancelled_submitted_relation_to_withdrawn` |
