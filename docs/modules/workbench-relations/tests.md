# 关联台关系事实源 测试矩阵

## 现有可复用测试

- `tests/test_workbench_pair_relation_service.py`：领域规则、row 去重、row type 对齐、active overlap、cancel、ETC 删除不恢复旧二栏 relation。
- `tests/test_workbench_relation_command_service.py`：command service confirm/cancel/withdraw 基座、withdraw preview lock、row-id batch cancel、metadata update、freshness precondition、idempotency、mode registry 和 active row conflict。
- `tests/test_workbench_auth_context_idempotency.py`：workbench confirm/cancel/withdraw actor/tenant/idempotency、withdraw 写入委托 command service，以及纯候选 `split_candidate` suppress 边界。
- `tests/test_workbench_relation_sql_projection.py`：`workbench_relation` distribution、linked/candidate/unlinked rows、正式发票和 OA 附件发票 identity 去重。
- `tests/test_workbench_relation_read_facade.py`：freshness-gated facade、missing 入队刷新、unlinked 过滤、candidate relation status 映射不被硬编码为 active。
- `tests/test_platform_runtime_boundary_guards.py`：下游读模型不得直接 join `app.workbench_pair_relations`，银行明细关系标签必须走 facade，ETC summary 删除、server OA offset auto pair、OA 附件上下文 repair、batch accounting legacy repair 和 no-OA legacy repair/consolidation 不得退回 direct pair relation mutation。
- `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`：批量账务 relation freshness、submit/withdraw command service 委托、submit 缺 command fail-fast 和前端阻断。
- `tests/test_no_oa_bank_batch_*`：no-OA submit/withdraw、internal transfer confirm-link、command service 写入委托、relation read model stale fail-fast、Workbench paired/open 收敛。
- `tests/test_turnover_*`：turnover manual closure/withdraw command service 委托、relation read model stale fail-fast、Application wiring guard 和 workbench pair relation 集成。
- `tests/test_pending_invoice_service.py`：待找发票 attach/create 幂等、relation detail 读 distribution、manual/attach relation 写入委托 command service、relation read model stale fail-fast。
- `tests/test_etc_backend.py`：ETC 删除、历史修复、existing batch link、summary relation command service 委托、缺 command fail-fast 和 stale fail-fast。
- `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`：进项发票 OA reverse evidence detected 后通过 relation command service 写 `input_invoice_oa_reverse`，缺 command fail-fast，command stale/conflict 返回 409 且不推进本地 batch。
- `tests/test_workbench_relation_history_replay_tool.py`：PostgreSQL history replay 只读巡检，覆盖 active row 多 case 占用、row shape、未注册 mode severity、relation/history 差异、readiness 状态和 `--fail-on-issues`。

## 七类测试要求

### 1. Business core unit tests

适用。新增或更新：

- mode/state registry 合法 mode、非法 mode、automatic decision 不允许写 active fact。
- history replay 对 active 未注册 mode 报 error，对历史非 active 未注册 mode 报 warning。
- active row occupation、case reuse、duplicate row、conflicting row type。
- cancel、withdraw、supersede、repair 状态转换。
- idempotent replay 同 request 返回同 relation。
- 正式发票与 OA 附件发票强 identity 去重不被绕过。

### 2. Service-layer tests

适用。新增或更新：

- `PostgresWorkbenchRelationRepository` load/save/history/dirty scope 行为等价。
- `workbench_relation_history_replay` 只读读取 relation、history 和 readiness，不执行 repair/write。
- `WorkbenchRelationCommandService` confirm/cancel/withdraw/attach/no-OA/turnover/batch accounting/ETC/input reverse/OA offset 写入；withdraw 必须覆盖 preview lock、expected_versions conflict、恢复上一状态和无 history 撤到无关联。Phase 7A 已补 ETC row-id batch cancel 和 relation metadata update，Phase 7B 已补 ETC repair/link/migration 缺 command fail-fast，Phase 7C 已补 input invoice OA reverse command delegation 和缺 command fail-fast，Phase 7D 已补 batch accounting submit 缺 command fail-fast，Phase 7E 已补 turnover legacy fallback 缺 command fail-fast，Phase 7J 已补 OA offset mode 和 replace-existing repair history，Phase 7K 已补 batch accounting legacy repair command delegation 和缺 command fail-fast，Phase 7L 已补 no-OA legacy migration/repair/consolidation command delegation 和缺 command fail-fast。
- `PendingInvoiceApplicationService` manual invoice、attach existing 单条/批量必须委托 `WorkbenchRelationCommandService`，不得直接调用 pair service 写入。
- transaction rollback 不产生半写入。
- affected scopes 和 downstream refresh enqueue 完整。
- audit before/after、actor、reason、affected months 不丢。
- repository 不直接绕过 `ReadModelRefreshGateway` contract，事务内 writer 满足等价 contract。

### 3. API contract tests

适用。新增或更新：

- workbench confirm/cancel。
- pending invoice attach/create 已在 Phase 4 覆盖 application service command delegation、stale fail-fast 和 API 旧 shape 回归；后续仍需补 HTTP 层 non-fresh response shape 专项断言。
- no-OA submit/withdraw 已覆盖 success、rollback、version conflict 和 relation read model stale fail-fast；legacy migration/repair/consolidation 已覆盖 command delegation、active row occupation、single-source case reuse 和 read model worker 不隐式 repair。
- turnover manual closure/withdraw 已覆盖 command service 委托、缺 command fail-fast、stale fail-fast、API wiring guard 和 Workbench 集成。
- batch accounting submit/withdraw。
- batch accounting submit 缺 command service 时不得 direct pair fallback。
- ETC repair/delete 可见入口；已提交业务批次删除必须在本地 reset 前检查 `workbench_relation` fresh，非 fresh 返回 409 且不删除 batch 或 relation。
- input invoice OA reverse evidence detected 写入：success、command service unavailable、relation read model stale/conflict 409、no half-write。

每个写 API 至少覆盖 success、missing fields、illegal state、permission/actor mapping、version conflict、idempotent repeat、non-fresh relation read model 和 refresh_enqueued response。

### 4. Read model/cache/background job tests

适用。新增或更新：

- relation 写入后 `workbench_relation` dirty/outbox 入队；ETC summary delete command result 必须返回 changed case ids 和 affected months 并驱动 Workbench relation invalidation。
- downstream `bank_detail`、`pending_invoice`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`no_oa_bank_batch`、`turnover_ledger`、`search`、`cost_statistics`、`tax_offset` scope 覆盖。
- worker rebuild 后 relation distribution fresh。
- open/proposed unmatched candidate decision 必须分发为 `relation_status='candidate'`，并由 `WorkbenchRelationReadFacade` 统一提供给下游页面；paired/active 关系才是 `linked`。
- OA 待付款、待找发票、进项发票使用情况、销项发票收款、银行明细必须覆盖至少一个 candidate relation status 不丢失的 regression；其中支付/收款/待补票状态和金额汇总必须证明 candidate 不参与 linked-only 业务计算。成本统计等非 relation chip 页面必须覆盖 candidate 不进入业务金额/状态计算。
- read facade missing/stale/source mismatch 返回非 fresh，不伪装空关系；但 scope 已 fresh 时，`get_by_row_ids` 中个别请求 row 缺失应由调用方按无 relation/unlinked 处理，不能阻断整页 read model。
- App Status registry 仍能观测 `workbench_relation`。
- PostgreSQL history replay 必须报告 readiness missing/not fresh，不能把 read model 状态缺失当成 pass。

### 5. Frontend component and interaction tests

适用。新增或更新：

- 关联台、待找发票、no-OA、turnover、batch accounting mutation success 后 refetch/invalidate。
- bank detail、cost statistics 等监听 `workbenchRelationUpdated` 只作为刷新提示。
- bank detail 必须显示 `候选oa` / `候选发票`，OA 待付款、待找发票、销项发票收款必须显示候选 chip；这些 chip 只能由后端 `relationStatus` / `relation_status` 驱动，不能由金额或页面本地状态推断。
- relation read model non-fresh 时按钮禁用并展示后端 message/reasons/scopes。
- API 失败时不更新本地事实，不把 event 当成功。

### 6. End-to-end business-flow integration tests

适用。至少覆盖：

- 在关联台 confirm 后，bank detail、pending invoice、invoice usage/OA pending 或 batch accounting 通过后端 read model 看到同一 relation。
- no-OA submit/withdraw 与关联台 internal transfer confirm-link 对同一组 row 收敛到同一 case，并在 Workbench paired/open 之间恢复。
- turnover closure submit/withdraw 影响 workbench_relation、cost/search；Phase 6 已覆盖 stale relation read model 下不产生半写入。
- pending invoice attach existing 后，发票页和银行页关系一致。
- batch accounting submit/withdraw 后，workbench_relation 恢复。

### 7. Existing feature regression tests

适用。必须保护：

- 旧 API response shape 不丢字段。
- 新增 `relationStatus` / `relation_status` 字段不能破坏旧页面筛选、排序、分页、导出；旧 linked/no-relation 样式和详情按钮位置必须保持。
- 旧页面筛选、排序、分页、导出不因 relation module 抽离变空。
- 旧 Mongo snapshot/shadow read/repair tools 迁移观察期可读。
- App Health/readiness 仍能展示 workbench relation worker。
- 权限和 audit 不被新 command service 绕过。

## 架构守卫测试

后续必须继续扩展架构守卫：

- downstream query/read service 禁止接受 `pair_relation_service`。
- 页面 service 禁止 `from app.workbench_pair_relations`。
- `server.py` 禁止新增 relation business helper，允许列表只保留 route/dependency wiring。
- relation 写入口必须依赖 `WorkbenchRelationCommandService` 或明确的 command port；ETC 业务批次删除、历史 repair、historical migration、existing link、input invoice OA reverse、server OA offset auto pair、OA 附件上下文 repair、batch accounting legacy repair 和 no-OA legacy repair/consolidation 不得在生产 wiring 或 service fallback 中直接调用 pair service mutation。
- `PostgresWorkbenchRepository` 不再拥有 relation SQL 实现。
- turnover closure/withdraw 的 Application wiring 不得回退到只注入 `pair_relation_service`。

## 验证命令建议

分阶段最小命令：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_history_replay_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_fails_fast_when_workbench_relation_read_model_is_stale -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py tests/test_no_oa_bank_batch_api.py tests/test_turnover_ledger_api.py tests/test_pending_invoice_service.py -q
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx
cd web && npm run build
```

全量闭环前必须补充目标 e2e 或 integration smoke，证明一个页面 mutation 后其他页面通过后端事实重新读取到一致 relation。
