# 免OA流水批量处理 状态机

> 修改 `免OA流水批量处理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

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
| `version_conflict` | PUT 的 `expected_version` 过期 | 返回 409；不得保存或刷新 |

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
- No OA SQL read model。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `draft` | 未提交候选批次 | 可查看 detail；普通候选可选择行提交；internal_transfer 走 batch submit |
| `submitted` | 已提交免 OA 批次并写入 Workbench pair relation | 可撤回 |
| `withdrawn` | 已撤回批次 | 只读；如果源流水仍 current，可重新生成 draft |
| `conflict` | 规则/金额/内部往来配对不唯一或不完整 | 不可提交，需人工处理底层分类/关系 |
| `stale` | 已提交批次的源流水或分类漂移 | 不可撤回或需复核；active relation 应被清理 |
| `superseded` | 历史单行批次被合并替代 | 只作为迁移/兼容状态 |

候选生成规则：

- 未提交候选只来自当前 tag selection 中的 tag code。
- 未提交候选必须排除被 Workbench active relation 占用的银行流水。
- 已提交历史批次即使标签不再准入，也继续可见并按状态管理。
- 同月、同银行账户、同 category code 是 submit-selection 的硬约束。

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
  -> no_oa_bank_batch / workbench / influenced read models refresh
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
| loading | 首次加载、月份/bucket 变化时显示加载 | `web/src/test/NoOaBankBatchPage.test.tsx` |
| empty | 未选择标签或当前筛选无批次时显示空态 | page tests |
| error | list/detail/tag/submit/withdraw API 失败显示反馈 | API/page tests |
| stale/refreshing | `readModelStatus !== "fresh"` 时保持当前 rows 可见并后台轮询 | `shows read model stale state and reloads until the no OA read model is fresh` |
| route inactive | 页面卸载或 inactive 后停止 stale polling / event replay | `cleans up stale read model retry reload after route unmount`、`useActiveFinanceDomainEvent` tests |
| permission disabled | 无 mutation 权限时提交、撤回、保存标签不可用或 API 403 | route/API tests |
| tag drawer | 打开时重新 fetch tag selection；保存后 reload list | tag drawer tests |
| selection guard | 只允许一个银行账户区域的 rows 同时被选择 | `prevents selecting rows from another bank before clearing the current bank region` |
| internal transfer action | internal_transfer draft 走 batch submit endpoint，不走 selected rows submit | `submits internal transfer draft batches through the batch endpoint` |
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
  -> NoOaBankBatchApplicationService.refresh_batches(scope_key)
  -> all scope: 读取全量银行流水并生成完整 no-OA snapshot
  -> YYYY-MM scope: 只读取目标月银行流水，只替换目标月批次，保留其它月份批次
  -> save_no_oa_bank_batches 以合并后的完整 snapshot 覆盖，并删除 snapshot 缺席批次行
  -> complete dirty scope and readiness
```

失败恢复：

- worker handler event type 或 scope type 错误必须拒绝。
- stale source version event 必须 skip，不得 rebuild 或覆盖 read model。
- 读取 Bankdetail tag/read model 时遇到 `*_read_model_not_fresh` 必须保持 `refreshing`/defer，不得把 no-OA readiness 标记为 `failed`。
- GET list/detail 不得为了 missing/stale 同步 rebuild 全量批次。
- 本地测试不能证明真实 RabbitMQ/Redis/systemd drain，发布前按运维 smoke 验证。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐免 OA 流水批量处理状态机 | 固定 tag selection、batch lifecycle、internal transfer from Workbench、UI stale polling、read model/worker 状态 | 待本轮模块验证命令 |
| 2026-06-11 | 固定内部往来双入口闭环 | Workbench/no-OA 同一组内部往来幂等复用同一 no-OA fact；存量两行 manual internal-transfer relation 迁移；active relation row 独占；SQL read model 保存清理缺席旧批次 | `pytest` no-OA service/workbench integration、pair relation service 目标用例 |
| 2026-06-14 | no-OA 月度 read model refresh 和依赖未 fresh 状态收敛 | `no_oa_bank_batch` scope policy 支持 `all`/月份；月度 worker 不全量读取、不删除其它月份批次；Bankdetail 依赖未 fresh 时记录 refreshing，不再污染 failed blocker | `tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_workbench_integration`、`tests.test_read_model_readiness_reporter`、`tests.test_read_model_refresh_gateway` |
