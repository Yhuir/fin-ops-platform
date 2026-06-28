# 外部往来款管理 状态机

> 修改 `外部往来款管理` 相关业务状态、UI 状态、direct API 数据流或 legacy projection 清理链路前必须读取本文件。

## 业务状态

### 标签准入

事实源：

- 银行明细自动标签规则中的外部往来标签。
- App settings 中的 `turnover_ledger_tag_selection`。

状态：

| 状态 | 含义 | 允许动作 |
| --- | --- | --- |
| `active` | 当前可用且属于外部往来的标签 code | 可被选择或取消选择 |
| `selected` | 已保存为外部往来台账准入标签 | direct grouped GET 纳入符合三层分类条件的银行流水 |
| `inactive_selected` | 历史保存但当前停用、未知或不再属于外部往来的标签 | GET 返回提示；下次保存后清理 |
| `version_conflict` | PUT 的 `expected_version` 与当前版本不一致 | 返回 409；不得保存或刷新 |

规则：

- `selected_tag_codes` 可为空，表示暂不拉取新的外部往来流水。
- PUT 只能提交当前 `active_tags` 中存在且属于外部往来的 code。
- 保存成功必须写审计，并返回 affected scope diagnostics；页面随后直接重读 grouped ledger。

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
  -> frontend reloads grouped ledger and rebinds selected rows
  -> frontend rebinds selected bank row ids to latest same-group flow rows
  -> backend stale precondition passes
  -> Turnover manual confirmed relation
  -> Workbench active pair relation
  -> merge selected banks plus any selected banks' existing OA-bank active relations into one turnover_manual_closure case
  -> Workbench open relation until invoice/full business relation is completed in Workbench
  -> turnover/workbench/workbench_relation affected scopes and real outbox
  -> API 返回 affected months/scopes scope-only envelope（不返回 legacy barrier targets）
  -> frontend directly reloads grouped ledger
  -> workbench/cost/search 等下游按各自 direct API、operation projection 或真实后台任务收敛
  -> frontend emits Workbench refresh event; post-write sync/reload blockage is warning, not mutation failure
```

校验：

- `bank_row_ids` 必须至少两条，不能重复；不再限制为正好两条。
- 全部流水必须同组、同对方、同语义。
- 必须至少一收一支，收支合计差额为 `0.00`。
- 前端不能用抽屉打开时缓存的 flow row 版本直接提交；提交前必须刷新并重绑定，若任一流水消失、离开原 group、或刷新后不再零差额，必须中止并要求重新选择。
- 不得被其他 active Turnover confirmed relation 占用。
- 已处于 Workbench active relation 的所选银行流水，只有当既有 relation 的 row types 仅包含 `oa` 和 `bank` 时，外部往来闭环确认才可合并这些 relation；合并后新的 `turnover_manual_closure` active case 包含既有 OA rows、既有 bank rows 和本次新增 bank rows。既有 relation 包含 `invoice` 或其他业务 row type 时必须拒绝，并要求到关联台处理完整关系。
- `expected_versions` 必须在写 relation 和 Workbench pair relation 前校验。
- `idempotency_key` 相同 payload 重放返回第一次结果；不同 payload 返回 409。
- 已确认后不能追加流水；漏选时必须先撤回原闭环关系，再重新选择完整流水确认。
- 两笔流水保留 `evidence.closure_mode=manual_zero_difference_pair`；三笔及以上使用 `manual_zero_difference_group`。

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
  -> turnover/workbench/workbench_relation affected scopes and real outbox
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

extra 保存只影响 Turnover ledger direct payload 和局部 UI；前端可发 `turnoverLedgerExtraUpdated` 作为刷新提示，但不能让无关页面依赖该事件作为事实源。

## UI 状态

| 状态 | 当前行为 | 测试入口 |
| --- | --- | --- |
| loading | 首次或筛选加载 grouped ledger | `web/src/test/TurnoverLedgerPage.test.tsx` |
| empty | grouped response 无 groups 时展示空态 | `web/src/test/TurnoverLedgerPage.test.tsx` |
| error | ledger/detail/export/extra API 失败时显示错误或 toast | `shows a business error when relation detail disappears after the ledger was rendered` |
| direct grouped payload | 页面展示 `/api/turnover-ledger?view=grouped` 返回的 rows/summary；GET 不返回旧同步字段 | page tests |
| permission disabled | `canMutateData=false` 时禁用保存、确认、撤回等写动作 | API 403 + 前端 disabled tests |
| tag drawer | 加载 active tags，保存 selected codes 后 reload ledger | `opens tag selection drawer, saves selected bank detail labels, and reloads ledger` |
| closure drawer | 允许同组多条未闭环 flow rows；至少一收一支且收支合计差额为 0 才允许确认；仅已关联 OA 或发票但未闭环的 flow row 不阻断确认；点击确定前 reload grouped payload，并用最新 row versions 提交 | manual closure/cross-group/rebind tests |
| extra drawer | 从真实 flow row 打开，隐藏技术 relation id，可保存 extra | extra drawer tests |
| export dialog | preview 后下载 XLSX，不按 JSON 解析 blob | export API/page tests |
| operation pending | tag-selection、extra、confirm、withdraw 成功后显示全屏 overlay，并直接 reload grouped ledger；不再等待 legacy barrier | operation overlay / page tests |
| workbench relation feedback | grouped payload 中的 flow row 展示后端 projection 给出的正向 relation chip：`linked_oa=true` 显示“已关联 OA”，`linked_invoice=true` 显示“已关联 发票”，`cash_closure_linked=true` 显示“收支闭环”。未发生闭环时不显示负向闭环 chip。toolbar 的确认/撤回只看 `cash_closure_*` 字段，不看 OA/发票 chip；这些字段来自后端 projection，不来自前端本地事件 | API mapper / page tests |

前端跨页事件：

- confirm/withdraw 成功后发 `turnoverRelationUpdated` 和 `workbenchRelationUpdated`。
- extra 保存成功后发 `turnoverLedgerExtraUpdated`。
- 这些事件只提示当前浏览器刷新；后端 canonical facts、real outbox 和 direct reload 才是页面事实源。

## Legacy Projection / Worker 清理状态

Legacy key：`turnover_ledger`

Scope type：`turnover_ledger`

Scope key：正常写路径只返回 affected month diagnostics；`all` 仅作为 fan-out/未知月份诊断例外。

Worker instance：无 turnover 专用页面刷新 worker。

Refresh event：无 active turnover 页面刷新事件；写操作成功后页面直接重读 grouped ledger，下游模块按各自 direct API、operation projection 或真实后台 outbox 合同收敛。

Legacy projection 状态：

| 状态 | 含义 | 后续动作 |
| --- | --- | --- |
| `present` | 历史 source versions 与旧事实源记录仍存在 | 仅供迁移清理/诊断；页面 grouped GET 不等待它。 |
| `refreshing` | legacy 投影历史状态 | 不再由 active turnover worker 产生；写动作由后端 stale precondition/canonical write safety 判定。 |
| `outdated` | source versions 不一致 | 不得伪装为页面事实；仅作为 legacy projection 下线前诊断。 |
| `missing` | legacy SQL read model 缺失 | 仅作为后台兼容投影诊断；页面 direct grouped payload 不返回旧刷新状态合同。 |
| `failed` | legacy 投影历史状态 | 不再阻塞 turnover App Status domain；页面合同不暴露 read-model status。 |
| `unavailable` | runtime repository / queue 不可用 | App Status 不得显示 green；按 blocked/busy 暴露。 |

旧 refresh 触发来源已下线：

- tag-selection、bank-row-tags batch、relation extra、manual closure confirm/withdraw 不再 enqueue turnover 页面刷新。
- 底层银行流水分类、relation、extra、settings、source versions 变化后，页面读取走 direct grouped GET；下游 workbench/workbench_relation/cost/search 按各自合同处理。

worker 流程：

```text
GET /api/turnover-ledger
  -> TurnoverLedgerQueryService
  -> TurnoverLedgerService direct grouped/flat payload
  -> Workbench relation context from direct/read facade as required by the query path
  -> frontend reloads grouped ledger after writes without waiting for turnover legacy sync metadata
```

失败恢复：

- worker handler event type 错误必须拒绝。
- legacy projection 失败不得保存半成品。
- 写操作 outbox 或真实后台任务未完成时 App Status 应按对应运行事实保持 busy/blocked。
- 本地测试不能证明真实 RabbitMQ/Redis/systemd drain，发布前按运维 smoke 验证。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-26 | 前端写后移除 legacy barrier 等待 | tag-selection、extra、manual closure confirm/withdraw 成功后直接 reload grouped ledger；后端写响应仅保留 affected scopes，不再返回 target envelope | `web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-26 | 普通 turnover 写操作从 `turnover_ledger:all` 收敛为 affected month diagnostics | bank-row-tags、manual closure confirm、relation confirm/withdraw 的后端响应默认使用 affected month diagnostics；`all` 只保留为 fan-out/未知月份例外，降低写后全量诊断长尾 | `tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-23 | 补 legacy manifest 合同守卫 | 不改变外部往来业务/UI 状态；锁定 `turnover_ledger` 历史合同，并保持 query owner、permission owner 和 repository ports 不与 cost/tax 混用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` |
| 2026-06-11 | 补齐外部往来款管理状态机 | 固定标签准入、候选/人工闭环、撤回、extra、UI version conflict、legacy projection/worker 清理状态 | 待本轮模块验证命令 |
| 2026-06-14 | tag-selection/extra/confirm/withdraw 接入 operation overlay 与旧 barrier | 历史实现：写 API 成功后曾等待 `turnover_ledger` barrier fresh 并 reload；已被 2026-06-26 direct reload 合同取代 | `web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-15 | manual closure 提交前刷新并重绑定所选 flow rows | 防止抽屉缓存旧 `categoryVersion` 导致后端 stale precondition 拒绝，也防止刷新后流水消失时误发 POST | `web/src/test/TurnoverLedgerPage.test.tsx` fresh-rebind/stale tests |
| 2026-06-16 | grouped payload 投影 Workbench relation 状态 | 关联台反向变化通过 Workbench relation read boundary 反馈到流水台；relation context 不可用时不得发布新的 turnover payload | `tests/test_turnover_ledger_read_facade.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-17 | 拆分 OA/业务单据关联展示与外部往来闭环状态 | OA/业务单据关联 chip 仅展示，不参与确认/撤回闭环判断；确认闭环可合并既有 OA-bank relation，撤回只撤回 `turnover_manual_closure` 并恢复旧 OA-bank relation | `tests/test_workbench_pair_relation_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 2026-06-17 | grouped flow row 版本投影与 schema version 失效 | `category_version=0` 占位时 grouped payload 必须回退到 `manual_category_version` 或基础 `version`；版本语义变化必须 bump `turnover_ledger_schema_version`，让旧 read model stale/rebuild | `tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_source_versions.py` |
