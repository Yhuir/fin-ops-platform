# Workbench 正式关系测试

日期：2026-08-26

## OA + 外部往来闭环模式选择

- `tests/test_workbench_auth_context_idempotency.py` 证明 preview 与 submit 共用一个 canonical confirm plan：完整 OA + external-turnover 双边零差额选择写 `turnover_manual_closure`、专属 evidence/history，并以 OA 同方向本金侧核对；单边选择保留 `manual_confirmed`，结构化 action 缺失零写失败。
- `tests/test_bank_details_canonical_query.py` 保护 role/action/family 在既有批量分类投影中返回；没有新 repository、SQL round-trip、read model 或 worker。

## 大成员关系确认/撤回（专项）

- Business core：`tests/test_workbench_relation_command_service.py::test_large_relation_confirm_and_withdraw_keep_all_members_and_idempotency` 以 100 个 typed members 证明 confirm、preview、exact-set withdraw 和同 key 重放均保留完整成员，撤回后 active relation 为空。
- Service/repository：`tests/test_workbench_direct_query_facade.py` 覆盖 30/100/500 条完整转交；`tests/test_workbench_page_selection_repository.py` 证明 500 条 selection 只使用正式 group members，OA `source_links` 广扫为零。
- Frontend/Browser：`WorkbenchApi.test.ts` 与 `WorkbenchSelectionModel.test.ts` 覆盖 500 条 payload/成员展开；`workbench-large-scroll-flow.spec.ts` 覆盖浏览器选择 30 条后 preview request 不截断。
- Regression：空输入、typed 对齐、重复 identity、missing/ambiguous、stale preview、expected versions、权限和单关系 exact-set 合同继续由既有矩阵覆盖。

## 关系撤回事务安全闭环（专项已验证）

- Exact selection：`test_preview_withdraw_relation_requires_exact_active_member_set`、`test_withdraw_relation_case_and_explicit_rows_must_identify_same_exact_relation` 和显式空 rows 回归，保护 preview/submit 的 exact full active typed member set；错误码为 `workbench_relation_exact_selection_required`。
- Transaction restore：`test_withdraw_relation_rejects_missing_canonical_restored_member`、`test_withdraw_relation_rejects_reused_predecessor_case`、cancelled predecessor case reuse 与 `test_withdraw_relation_rejects_restored_member_owned_by_another_active_case`，保护事务锁内 canonical/case/unique-owner 重验并在冲突时零写。
- Same-case predecessor：`test_withdraw_restores_same_case_historical_predecessor_topology` 与 `test_withdraw_restores_same_case_predecessor_through_command_boundary` 保护最近 confirm history 的 predecessor 沿用当前 case identity 时，preview 可提交、submit 原子取消当前 topology 并以单调 version 恢复历史 topology；被移除成员释放 owner，同 key 重放不产生第二次写。无关 case 复用规则保持不变。
- Preview/submit parity：pair service 在生成恢复计划时即执行 case/owner 校验，command 的加锁前后预览均走同一错误映射；删除无人调用的 `fallback_after_relations` 和 submit-only 二次校验，避免“预览可撤回、提交才 409”的规则分叉。
- Version / fingerprint：`test_withdraw_restored_relation_version_advances_past_existing_topology_version`、create/cancel 的 version=`1/2` 断言，以及 `test_withdraw_preview_fingerprint_changes_with_topology_and_history_identity`，保护 topology version 单调推进与 preview 绑定 current/after topology + confirm-history identity。
- Locks / idempotency：`test_relation_member_lock_includes_case_identity_and_persisted_members_in_stable_order` 保护 case/member 稳定锁顺序；`test_withdraw_relation_replays_same_idempotency_key_without_second_save` 保护重放零第二次 save。
- API / actor regression：`test_relation_restore_state_conflicts_map_to_http_conflict` 保护 exact selection→400、canonical/restore drift→409；`test_exception_apply_uses_authenticated_actor_instead_of_client_payload` 保护兼容 exception apply 只使用认证 actor。`internal_transfer` 人工确认继续统一走 relation UoW，独立 no-OA API 保留。
- 当前结果：本节中的历史验证数字只描述当时执行记录；每次实现须在交付报告中列出本轮实际重跑的测试、Browser、部署与生产验证结果。

## 人工 confirm-link 内部转账旧分流删除（已验证）

- Service/UoW：全 `internal_transfer` 银行成员、mixed `internal_transfer` + 其它银行分类和普通银行分类都必须构造 `manual_confirmed` command，并进入相同 canonical revalidation、active overlap、idempotency、history 与 rollback 边界；断言 no-OA batch callback 零调用。
- API contract：preview/confirm request 与 response shape 不变；mixed 不再返回 `no_oa_bank_batch_selection_internal_transfer_conflict`，全 `internal_transfer` 不再返回 no-OA batch payload；`amount_check.requires_note=true` 时才要求既有 `note`。
- Boundary/regression：guard 证明 facade 不再注入或引用 `submit_internal_transfer_rows_from_workbench`、`_bank_only_internal_transfer_confirm_status`、`_confirm_internal_transfer_rows_via_no_oa_batch`；独立 no-OA batch 的 API/service、登记 mode、幂等与 relation UoW 回归保持通过。
- Read model/Frontend/E2E 非适用：本次没有 schema、relation projection、scope、worker、API shape 或可见页面流程变化；不新增 Browser case，内部 dispatch 由 474 项关系专项矩阵与 4259 项全后端回归中的 service/API、真实 UoW 幂等和边界 guard 证明。

## 七类覆盖

1. Business core：relation mode/state registry、row overlap、replace/cancel/withdraw、withdrawal fingerprint、人工至少 2 个不同 canonical members、同栏/跨栏组合、上一稳定拓扑恢复、任意 typed member set。
2. Service layer：command repository adapter、人工 confirm 不按银行分类转调 no-OA、UoW 原子性、idempotency、history/`before_relations` restore、dirty/outbox、partial failure rollback。
3. API contract：confirm/preview/withdraw shape 不变、mixed/all `internal_transfer` 使用普通人工关系响应、`amount_check.requires_note` + `note`、expected versions、权限、错误 envelope、barrier targets。
4. Read model/worker：linked/unlinked projection、source versions、freshness、rebuild 和 fan-out。
5. Frontend：paired/unpaired、任意至少 2 个成员确认、两区 active relation withdraw、旧人工异常入口缺席且系统异常抽屉保留、权限交互；provenance 不形成第三状态。
6. E2E：同栏/跨栏正式确认、paired/unpaired 关系级撤回与下游 fan-out。
7. Regression：520 case、ETC、独立 no-OA batch、turnover、batch accounting、pending invoice、OA reverse。

## 主要测试

- `tests/test_workbench_pair_relation_service.py`
- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_relation_command_repository_adapter.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_relation_sql_projection.py`
- `tests/test_workbench_relation_read_facade.py`
- `tests/test_workbench_formal_relation_repository.py`（含 OA/流水/发票人民币币种别名统一进入 `CNY` matching bucket、日常报销日期占位符跳过、OA owned/active source alias 归一）
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_formal_relation_repository.py` 额外保护 matching 银行分类只使用一次有界 canonical projection，且缺失分类行在进入 UoW 前失败。
- `tests/test_workbench_relation_grouping.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_bank_category_relation_closure_service.py`
- `tests/test_workbench_relation_requirement_repair_ops.py`

## 必须断言

- `automatic_decision` / `automatic_match` 不能作为 formal write mode。
- 自动安全 plan 与人工 command 进入同一 UoW、active relation、history 和 outbox 合同。
- 人工 confirm 对 normalize 后 requested IDs 要求至少 2 个不同 canonical rows，并逐个精确解析为 `oa|bank|invoice`；同类型成员集合合法。不得保留至少两个 pane、必须含银行、完整性或金额相等的通用人工 gate。
- 人工 confirm 不按银行分类选择 mutation owner；mixed/all `internal_transfer` 与普通银行选择统一走 `manual_confirmed` command/UoW，旧 no-OA conflict、callback 和 payload 不得出现。独立 no-OA batch 继续只从其专属入口进入。
- 只有 `amount_check.requires_note=true` 时既有 `note` 才是提交门禁；缺 `note` 返回既有 `workbench_pair_relation_note_required`，填写后可以创建 active relation。材料不完整只决定关联台保持 `unpaired`，不会单独触发备注门禁。
- paired/unpaired active case 都只能按 exact full active typed member set 撤回；最近 confirm history 的 `before_relations` 必须在同一 UoW 的 current/predecessor case/member locks 内通过 topology、canonical、case reuse 与唯一 owner 重验后，才恢复上一稳定拓扑，无 predecessor 才输出 singleton。display metadata、row `case_id` 和部分选中不得决定恢复。
- relation topology version 必须单调推进：create=1，status/member topology 变化 +1，cancel +1，restore 使用当前 predecessor/history snapshot 最大 version +1；withdraw preview fingerprint 必须同时绑定 current/after topology 和 confirm-history operation identity。
- ambiguous/unsafe/resource-limited 结果零 relation write。
- active case 保持稳定；显式引用或唯一 exact composite 扩展均使用原 case 并在一次 UoW 原子替换；撤回 exact set 不自动重建。
- 日常报销申请人与银行对方户名使用独立员工强证据：2～3 字真实姓名可用，支付申请不得误用；OA 完成/审批日期优先、申请日期兜底；30 天接受、31 天拒绝，通用公司证据继续保持 365/366 天边界。已有 OA+附件发票关系补银行时，只搜索缺失的银行 pane；同员工大量未配对 OA 即使形成独立资源受限组件也不得阻断目标 relation 扩展，缺失 pane 内多笔流水精确合计仍可一次补全。
- 已有 OA+附件发票 relation 可由唯一同额员工流水补齐第三栏；流水必须与 OA 合计一致，附件发票差额继续进入异常链路，currency/direction、连通性和 `target_case_id` 必须同时成立。唯一同额单笔优先于同额多笔组合；多个同额单笔、跨 case 竞争、完整三栏与撤回 fingerprint 均 fail closed。全局建图或高密度 active case 的资源保护不得丢弃已证明安全的单笔计划或同批其它独立 exact case；大量同类型 OA 噪声不得消耗跨 pane 建边预算，多笔精确合计兜底仍必须可用。
- changed-case 持久化后只替换或删除目标 case/history；无关关系与审计保持不变，且 adapter 不得调用全局 `snapshot()` 做镜像重建。
- persisted effective category 实际变化时，category fact 与受影响普通 relation requirement/history 必须同事务提交；无变化、无 active relation、ETC/批量账务关系均零 metadata 写。外层 UoW 只在 commit 后发布进程镜像，失败/rollback 不污染。
- requirement repair 只自动修复 missing snapshot 或有 `manual|auto_confirmation|manual_confirmation|turnover_ledger` 有效分类来源证据的 tag drift；canonical confirmation proof 必须同时按 UUID/legacy identity 证明持久化绑定，rule-derived/未知来源只报告人工复核，dry-run fingerprint、幂等续跑、history 和 rollback 必须保留。
- 正常规则传播不再使用 explicit case-id repair。semantic changed tag codes 必须通过 settings/job/outbox 原子边界驱动；worker 按 tag proof 集合定位、完整 tag OR、全量预验证、正式 command/history、精确月份 refresh 和同 job 幂等重放。缺 proof/rule/scope 时整批零写。
- active case 校验只执行一条 relation query，不查询 history；in-memory fallback 直接按 case 读取，不能复制全局 snapshot。
- confirm overlap 校验只执行 active relation query，不加载 cancelled relation/history；command delta 只携带本次 history event，数据库不删除或重写旧 history，重复 operation id 保持幂等。
- 下游只把 active relation 视为 linked；关联台的 `paired` 还必须满足页面完整性合同。普通 OA+发票 active relation 缺银行时保持 owner/case 不变但显示为 `unpaired`；只有显式 batch-accounting 关系豁免完成要求，ETC marker 只证明 batch identity。
- 人工确认必须在 relation UoW 内重读 selected canonical rows；行缺失、pane/type 漂移、多 ETC batch 或非法 summary 必须整批 409 且零半写。合法 `etc-summary-*` 必须持久化唯一 external batch marker，worker 与 Page Audit 以 marker + 确定性 summary row 双重证明重建。
- OA Mongo/流程来源 alias 必须确定性指向唯一 canonical OA；alias collision fail closed。`attachment_source` formal plan 必须保存 exact binding，canonical `inv_imported_*` 附件关系也必须不可拆散。
- 多 scope freshness 仍逐 scope 比较 canonical expected/source proof；年度批量账务必须用一次 bulk SQL 返回 12 个月精确映射，并由真实 PostgreSQL 测试证明与 12 次单月 proof 完全相等，禁止年度汇总替代或逐月 N+1 回归。
- old candidate/decision 表、service、state key 和 API 不存在生产调用。
- 旧未配对工具栏“异常处理”人工入口与至少两个 pane/必须含银行人工 confirm gate 不存在生产调用；右上统一异常抽屉与自动 OA/发票异常仍存在。
- Release A 静态 guard 证明运行时不再访问旧状态；Release B 届时使用下一个可用 migration version，其 contract 必须证明只删除派生旧状态，不删除 canonical facts/relations/history。
- browser deterministic mocks 即使保留相同历史 `case_id` metadata，也必须把无 active relation 的 OA、流水和发票输出为三个 `row:<typed-id>` singleton；确认后才合并为 relation，撤回后恢复三个 singleton。

## 验证命令

```bash
python3 -m pytest -q \
  tests/test_workbench_v2_api.py \
  tests/test_workbench_pair_relation_service.py \
  tests/test_workbench_relation_command_service.py \
  tests/test_workbench_relation_command_repository_adapter.py \
  tests/test_workbench_uow_contract.py \
  tests/test_workbench_idempotency_contract.py

python3 -m pytest -q \
  tests/test_workbench_relation_sql_projection.py \
  tests/test_workbench_relation_read_facade.py \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_platform_runtime_boundary_guards.py

cd web && npm test -- --run \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchZone.test.tsx \
  src/test/WorkbenchApi.test.ts \
  src/test/WorkbenchWriteGate.test.ts \
  src/test/WorkbenchExceptionDrawer.test.tsx
```
