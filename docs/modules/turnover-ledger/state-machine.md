# 外部往来款管理 状态机

> 修改 `外部往来款管理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 业务状态

### 标签准入

事实源：

- 银行明细自动标签规则中的外部往来标签。
- App settings 中的 `turnover_ledger_tag_selection`。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `active` | 当前可用且属于外部往来的标签 code | 可被选择或取消选择 |
| `selected` | 已保存为外部往来台账准入标签 | 列表/read model 纳入符合三层分类条件的银行流水 |
| `inactive_selected` | 历史保存但当前停用、未知或不再属于外部往来的标签 | GET 返回提示；下次保存后清理 |
| `version_conflict` | PUT 的 `expected_version` 与当前版本不一致 | 返回 409；不得保存或刷新 |

规则：

- `selected_tag_codes` 可为空，表示暂不拉取新的外部往来流水。
- PUT 只能提交当前 `active_tags` 中存在且属于外部往来的 code。
- 保存成功必须写 canonical settings/version/audit；不投递任何页面 refresh，当前台账页随后重跑 normal GET 并由 fresh gate 按需收敛。

### 台账候选和分组

事实源：

- 银行明细流水。
- 银行明细有效分类和外部往来标签。
- Turnover relation snapshot。
- Turnover extra snapshot。
- App settings tag selection。

状态：

| 状态 | 含义 | Workbench 影响 |
| --- | --- | --- |
| `suggested` | 系统发现可能的往来候选，但不是唯一零差额闭环 | 不进入 Workbench 已配对事实 |
| `deterministic` | 系统发现唯一零差额候选 | 仍不代表已闭环；不进入 Workbench 已配对事实 |
| `confirmed` | 用户人工确认的 Turnover relation | 只有 manual closure 写出的 Workbench pair relation 才进入 Workbench |
| `withdrawn` | 已撤回的人工 relation | 不再作为 active pair relation |
| `conflict` / `stale` | 分类、方向、金额或底层流水变化导致关系不再可信 | 不可作为 active closure |

分组维度：

- `family`: `personal`、`company`、`bank`、`business`。
- `counterparty_name`。
- 外部往来语义和标签路径。
- grouped response 中 `summary_row` 是组级入口，写操作必须使用 `flow_rows[*].source_bank_row_id` 等真实银行流水 ID。

禁止：

- 不得把 `deterministic` 当作已闭环。
- 不得用 grouped summary row 作为确认闭环的银行流水。
- 不得把内部转账 legacy tag 纳入外部往来 relation。
- 不得混合同一对方下不同业务语义的流水形成闭环。

### 人工零差额闭环

入口：

- `POST /api/turnover-ledger/closures/confirm`
- 前端 `confirmTurnoverClosure`

允许流转：

```text
same group flow rows selected
  -> one or more income rows + one or more expense rows
  -> amount delta == 0.00
  -> frontend waits affected turnover_ledger month scopes fresh and reloads grouped ledger
  -> frontend rebinds selected bank row ids to latest same-group flow rows
  -> backend stale precondition passes
  -> Turnover domain validates a deterministic closure descriptor without persistence
  -> reuse the same selected-row snapshot and read canonical rule payload exactly once
  -> canonical Workbench active pair relation only
  -> merge selected banks plus any selected banks' existing OA-bank active relations into one turnover_manual_closure case
  -> reject before command if any final bank member is outside selected bank row ids
  -> freeze tag code, requires_oa/requires_invoice, rule source and version in relation metadata
  -> Workbench evaluates the frozen turnover_manual_closure requirements
  -> bank-only stays open when requires_oa=true; OA + bank can become paired when requires_invoice=false
  -> canonical relation/history/version/audit 原子提交，零页面 dirty/outbox
  -> API 返回业务结果、case identity 与信息性 affected months；freshness target arrays 为空
  -> frontend 结束命令阻塞并重跑当前 turnover normal GET
  -> turnover fresh gate 发现 mismatch 时只入队当前 exact month；Workbench/成本/搜索等页面在访问或重新激活时各自收敛
  -> frontend emits lightweight refresh hints; post-write current-page reload blockage is warning, not mutation failure
```

现代确认不得写 `app.turnover_relations` 或 `app.turnover_relation_events`。成功响应以 `workbench_pair_relation.case_id` 作为撤回身份；projection 只有在历史 relation 的 `special_metadata.turnover_relation_id` 显式存在时才输出 `cash_closure_relation_id`，不得从 case id 推断。

校验：

- `bank_row_ids` 必须至少两条，不能重复；不再限制为正好两条。
- 全部流水必须同组、同对方、同语义。
- 必须至少一收一支，收支合计差额为 `0.00`。
- 前端不能用抽屉打开时缓存的 flow row 版本直接提交；提交前必须刷新并重绑定，若任一流水消失、离开原 group、或刷新后不再零差额，必须中止并要求重新选择。
- 不得被其他 active Turnover confirmed relation 占用。
- 已处于 Workbench active relation 的所选银行流水，只有当既有 relation 的 row types 仅包含 `oa` 和 `bank` 时，外部往来闭环确认才可合并这些 relation；合并后新的 `turnover_manual_closure` active case 包含既有 OA rows、既有 bank rows 和本次新增 bank rows。既有 relation 包含 `invoice` 或其他业务 row type 时必须拒绝，并要求到关联台处理完整关系。
- 合并后的每个 bank member 都必须属于本次 `bank_row_ids`；既有 OA-bank relation 若带入未选择银行流水，必须在 relation command 前返回冲突，不能扩大用户确认范围。
- `expected_versions` 必须在写 relation 和 Workbench pair relation 前校验。
- `idempotency_key` 相同 payload 重放返回第一次结果；不同 payload 返回 409。
- 已确认后不能追加流水；漏选时必须先撤回原闭环关系，再重新选择完整流水确认。
- 两笔流水保留 `evidence.closure_mode=manual_zero_difference_pair`；三笔及以上使用 `manual_zero_difference_group`。
- 写入 Workbench active relation 时，必须从本次 selected-row 快照的 `effective_category_code`（缺失时回退 `category_code`）和一次 canonical rules payload，经统一 helper 冻结 tag code、`requires_oa`、`requires_invoice`、`paired_requirement_source` 与版本。关联台只读取 relation metadata 判断 required row type 是否满足；未知/空规则和 metadata 缺失的旧关系 fail closed，不得在关联台查询当前设置兜底，也不得由规则保存追溯改写。

### 撤回

入口：

- `POST /api/turnover-ledger/relations/{id}/withdraw`

允许流转：

```text
manual confirmed relation
  -> stale precondition passes
  -> Workbench relation scope check passes
  -> withdrawn
  -> command service withdraws only turnover_manual_closure case
  -> restorable previous OA-bank relations are reactivated
  -> canonical relation/history/version/audit 原子提交，零页面 dirty/outbox
  -> 当前 turnover 页 normal GET；其它消费者仅在访问/重新激活时收敛
```

禁止：

- system/generated relation 撤回。
- stale relation version 撤回。
- duplicate withdraw 产生第二次 mutation 或第二次 refresh。
- 外部往来页不得撤回包含发票或其他业务 row type 的 Workbench active relation；必须去关联台撤回完整 relation，避免误删 OA/发票关系。
- 外部往来页撤回只撤回 `turnover_manual_closure` 这个多流水闭环关系；确认闭环前已经存在且被合并的 OA-bank relation 必须恢复为 active，不能被取消或删除。

### Relation extra

入口：

- `GET /api/turnover-ledger/relations/{id}/extra`
- `PUT /api/turnover-ledger/relations/{id}/extra`

状态：

| 状态 | 含义 |
| --- | --- |
| default | relation 存在但没有 extra，返回默认结构 |
| saved | 保存利率、支付方式、备注、日期等补充字段 |
| invalid | 利率类型、负数、日期或过长文本非法 |
| stale | `expected_versions` 不匹配，拒绝保存 |

extra 保存只改变 Turnover canonical extra/version/audit 和局部 UI；前端只重跑本页 normal GET，不发送跨页刷新事件，也不能让无关页面自动读取。

## UI 状态

| 状态 | 当前行为 | 测试入口 |
| --- | --- | --- |
| loading | 首次或筛选加载 grouped ledger | `web/src/test/TurnoverLedgerPage.test.tsx` |
| empty | grouped response 无 groups 时展示空态 | `web/src/test/TurnoverLedgerPage.test.tsx` |
| error | ledger/detail/export/extra API 失败时显示错误或 toast | `shows a business error when relation detail disappears after the ledger was rendered` |
| stale/refreshing | `readModelStatus !== "fresh"` 时展示当前可用数据和诊断，不能把 grouped payload 当作最终业务结论；manual closure 发起/提交必须被阻断或先等 fresh 后重刷重绑，最终仍由后端 stale precondition/canonical write safety 兜底 | read model / page tests |
| permission disabled | `canMutateData=false` 时禁用保存、确认、撤回等写动作 | API 403 + 前端 disabled tests |
| tag drawer | 加载 active tags，保存 selected codes 后 reload ledger | `opens tag selection drawer, saves selected bank detail labels, and reloads ledger` |
| closure drawer | 允许同组多条未闭环 flow rows；至少一收一支且收支合计差额为 0 才允许确认；仅已关联 OA 或发票但未闭环的 flow row 不阻断确认；点击确定前先等台账 fresh、reload grouped payload，并用最新 row versions 提交 | manual closure/cross-group/fresh-rebind tests |
| extra drawer | 从真实 flow row 打开，隐藏技术 relation id，可保存 extra | extra drawer tests |
| export dialog | preview 后下载 XLSX，不按 JSON 解析 blob | export API/page tests |
| operation pending | 只覆盖 tag-selection、extra、confirm、withdraw HTTP 请求；成功后结束全局阻塞并 reload grouped normal GET，non-fresh 使用页面内状态 | page/API tests |
| workbench relation feedback | grouped payload 中的 flow row 展示后端 projection 给出的正向 relation chip：`linked_oa=true` 显示“已关联 OA”，`linked_invoice=true` 显示“已关联 发票”，`cash_closure_linked=true` 显示“收支闭环”。未发生闭环时不显示负向闭环 chip。toolbar 的确认/撤回只看 `cash_closure_*` 字段，不看 OA/发票 chip；这些字段来自后端 projection，不来自前端本地事件 | API mapper / page tests |

前端跨页刷新已删除：confirm/withdraw/extra 成功后只处理当前 Turnover 页面；其它页面/tab 在 route 重进、查询变化、浏览器手动刷新或明确重试时，从 canonical source version 与自身 read-model gate 取得事实。

## Read Model / Worker 状态

Read model key：`turnover_ledger`

Scope type：`turnover_ledger`

Scope key：普通写只返回信息性 affected month scopes，不 enqueue；页面 GET 发现 stale 时按精确月份入队。普通写无法确定月份时 fail closed，不能退回 `all` fan-out。

Worker instance：`turnover-ledger`

Refresh event：`turnover_ledger.read_model.refresh`

状态：

| 状态 | 含义 | 页面/API 行为 |
| --- | --- | --- |
| `fresh` | read model source versions 与当前事实源一致 | 可读可写 |
| `refreshing` | 缺失或 stale 后已入队刷新 | 可展示当前 payload 或空 payload；写动作由后端 stale precondition/canonical write safety 判定 |
| `stale` | source versions 不一致 | 不得伪装 fresh；应 enqueue `api_stale` refresh |
| `missing` | required SQL read model 缺失 | 返回 empty refreshing payload 并 enqueue `api_miss` |
| `failed` | worker 或 readiness 记录失败 | App Status 标记 domain blocked |
| `unavailable` | runtime repository / queue / readiness 不可用 | App Status 不得显示 green；按 blocked/busy 暴露 |

refresh 触发来源：

- route 进入/重进、筛选/月 scope 变化、浏览器手动刷新或明确重试时，GET fresh gate 发现 exact scope missing/stale/source-version mismatch；focus/visibility/BFCache 不触发业务 GET。
- 显式 App Health/初始化/修复命令；`all` 只允许在这些已授权维护入口使用。
- tag-selection、bank-row-tags、relation extra、manual closure confirm/withdraw 和底层事实变化只推进 canonical version，不在写路径触发 refresh。

worker 流程：

```text
job.outbox_events / job.read_model_dirty_scopes
  -> turnover-ledger worker consumes turnover_ledger.read_model.refresh
  -> TurnoverLedgerReadModelRefreshService.handle_runtime_event
  -> TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope
  -> WorkbenchRelationReadModelRepositoryPort.workbench_relation_source_bundle_from_source
  -> fresh relation distribution enriches grouped payload; non-fresh relation context fails without saving
  -> save_turnover_ledger_rows
  -> complete dirty scope and readiness
```

失败恢复：

- worker handler event type 错误必须拒绝。
- projection 失败不得保存半成品 read model。
- dirty scope 未 complete 时 App Status 应保持 busy/blocked。
- 本地测试不能证明真实 RabbitMQ/Redis/systemd drain，发布前按运维 smoke 验证。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-26（历史） | 普通 turnover 写操作曾从 `turnover_ledger:all` 收敛为 affected month scopes | 该写后 barrier 方案已由 Phase 27 的“写后零页面 fan-out、页面访问时 exact-scope 收敛”取代；本行仅保留演进记录。 | `tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-23 | 补 read model manifest 合同守卫 | 不改变外部往来业务/UI/read model/worker 状态；锁定 `turnover_ledger` 为 `partitioned_scoped_incremental`、`all` 为 fan-out command，并保持 query owner、permission owner 和 repository ports 不与 cost/tax 混用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` |
| 2026-06-11 | 补齐外部往来款管理状态机 | 固定标签准入、候选/人工闭环、撤回、extra、UI stale、read model/worker 状态 | 待本轮模块验证命令 |
| 2026-06-14 | tag-selection/extra/confirm/withdraw 接入 operation overlay 与 freshness barrier | 写 API 成功后等待 `turnover_ledger` barrier fresh 并 reload，避免旧 grouped payload 暴露给用户 | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/OperationBarrierApi.test.ts` |
| 2026-06-15 | manual closure 提交前刷新并重绑定所选 flow rows | 防止抽屉缓存旧 `categoryVersion` 导致后端 stale precondition 拒绝，也防止刷新后流水消失时误发 POST | `web/src/test/TurnoverLedgerPage.test.tsx` fresh-rebind/stale tests |
| 2026-06-16 | grouped payload 投影 Workbench relation 状态 | 关联台反向变化可通过 fresh `workbench_relation` read model 反馈到流水台；relation 不 fresh 时不发布新的 turnover read model | `tests/test_turnover_ledger_read_model_refresh.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-17 | 拆分 OA/业务单据关联展示与外部往来闭环状态 | OA/业务单据关联 chip 仅展示，不参与确认/撤回闭环判断；确认闭环可合并既有 OA-bank relation，撤回只撤回 `turnover_manual_closure` 并恢复旧 OA-bank relation | `tests/test_workbench_pair_relation_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-17 | grouped flow row 版本投影与 schema version 失效 | `category_version=0` 占位时 grouped payload 必须回退到 `manual_category_version` 或基础 `version`；版本语义变化必须 bump `turnover_ledger_schema_version`，让旧 read model stale/rebuild | `tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_source_versions.py` |
