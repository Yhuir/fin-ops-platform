# Phase 26 Research：冻结 requirement 的 Turnover Closure 分区修复

日期：2026-07-22

## Research conclusion

这是一个共享 completion 边界被 turnover 特例绕过、同时写入入口没有冻结真实 policy 的组合缺陷。最小正确解不是新增状态或 UI，而是：

1. 在统一 completion helper 删除 turnover bypass。
2. 在现有 Turnover adapter 创建 relation 时复用统一 policy metadata helper。
3. 删除 legacy no-OA 保存时追溯同步 turnover relations 的旧链。
4. 用现有 repair ops 修复历史 legacy-invalid snapshots。
5. bump Workbench v6 并用现有 active-generation 原子 rehydrate。

## Root cause and call chain

```text
TurnoverLedger confirm API
  -> TurnoverLedgerConfirmRequestBoundaryFacade
  -> TurnoverLedgerWriteFacade / UoW
  -> request-scoped TurnoverLedgerBankRowSelectionPort
  -> TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure
       当前：写死 requires_oa=true / requires_invoice=false / legacy source-version
  -> WorkbenchRelationCommandService
  -> canonical active relation + history + durable outbox
  -> Workbench projection/grouping
  -> evaluate_bank_relation_completion
       当前：turnover_manual_closure 无条件 complete
  -> zone = paired
```

直接根因是最后的无条件 complete。写死 metadata 没有造成当前截图的直接分区结果，但它让规则标签管理失去事实权威，必须与 bypass 一起修，否则双 false、invoice-only、双 true 和多标签关系仍会错误。

## Validation Architecture

### Shared business oracle

`build_bank_relation_requirement_metadata(...)` 已经定义：

- canonical source `bank_transaction_paired_policy`；
- tag codes snapshot；
- rule version；
- `requires_oa/requires_invoice`；
- 多标签 OR；
- unknown/missing/empty fail closed。

计划只复用该 helper，不引入新 policy service。`evaluate_bank_relation_completion(...)` 继续作为 grouping、SQL projection 和 preview 的统一 completion oracle。

### Online write validation

- `TurnoverLedgerConfirmPrimaryWriteFacadeBuilder` 已创建 request-scoped `TurnoverLedgerBankRowSelectionPort`。
- stale version check 和 closure preview 已复用 selected-row cache。
- adapter 应接收同一个 `rows_by_ids` provider 和现有 rules provider；确认时读取一次 rules payload，在内存 O(k) 计算 requirement。
- 必须新增 final relation bank-membership guard：合并已有 OA-bank relation 后，所有 bank member 都必须属于 selected ids。否则走现有 conflict/fail-closed 路径，不读取额外 bank rows。

这条 guard 同时解决正确性和性能：最终 requirement snapshot 覆盖 relation 全部 bank members，而 selected cache 已包含它们，银行 I/O 次数不增加。

### Projection validation

- active relation membership 不变，`workbench_relation` linked/unlinked contract 不变。
- 只改变 Workbench page zone：complete active -> paired；incomplete active -> same-case unpaired。
- 前端已映射 `missing_row_types` 并渲染“待补 OA/发票”，无需 production UI 变更。
- Workbench projection 语义变化需要 month/all schema v6；由 month schema 派生的 page cache key 随之失效。

### Historical validation

现有 repair ops 已有正确安全框架：active relation list、bulk fresh tag read、canonical rules payload、dry-run report、SHA-256 fingerprint、execute fingerprint gate、固定 actor、idempotency、history 和 command service。

最小扩展目标：

- active `turnover_manual_closure`；且
- `paired_requirement_source != bank_transaction_paired_policy`，或缺 canonical tag codes/version。

这覆盖旧 `turnover_ledger_manual_closure`、`no_oa_bank_batch_tag_selection` 和缺字段关系。ETC/batch 不纳入；普通 missing snapshot 仍沿用现有“保留已存在 legacy requires 值”的兼容行为。Turnover legacy-invalid target 必须覆盖旧写死 requires 值，用 fresh tags + 当前 canonical rules 做一次明确数据修复。

forward fingerprint 必须绑定每个 target 的 current metadata preimage 和 intended after image，而不只绑定输出；execute history note、operation 与 per-case idempotency key 都绑定该原始 fingerprint。partial execute 重跑不能只看仍是 legacy-invalid 的 fresh targets：必须把 fresh targets 与 fingerprint-bound execute histories 合并重建 original plan；已有 history 的 case 在 current 等于 recorded after 后 skip，未执行 case 在 current 等于 recorded before 后继续，合并 fingerprint 不一致则首写前零写入失败。

为保证发布可逆，同一 ops module 增加 `--rollback-dry-run` / `--rollback`，都强制传入原始 execute fingerprint：从 `list_history()` 精确选择匹配 actor/operation/fingerprint 的 before/after metadata，在任何 write 前批量校验 current active relation 等于 recorded after image，任一 drift 零写入失败；随后通过现有 `update_relation_metadata_for_case_id(... replace_special_metadata=True)` canonical UoW 原地精确恢复完整 `special_metadata` preimage并产生 durable history/outbox。pair/command service 的新 flag 默认 false 保持旧 metadata merge caller 完全不变，command fingerprint 包含该 flag，只有 repair rollback 显式 true；members/status/mode/lifecycle/created fields 不变，不 cancel/recreate relation，只有正常 update 的 updated_at/history 前进。该合同支持 partial execute 恢复和幂等 replay，成功后 rollback dry-run target 为 0，不增加 service/helper/API/DTO/table/worker/read model。

## Version and cache boundary

- 当前 Workbench month/all schema 为 v5。
- completion semantics 改变后必须同步 bump 到 v6。
- groups/initial Redis cache schema由 Workbench month schema 派生，无需新增 cache 或手写清理链。
- 旧 v5 generation/cache 应被 fresh gate 拒绝；v6 用现有 rehydrate 生成新 generation 并原子激活。
- 不改变 `workbench_relation` projection schema，因为 canonical ownership/linked-unlinked 没变。

## Old pollution chain

`NoOaBankBatchApplicationService.update_tag_selection(...)` 当前仍触发 turnover requirement sync：

- list all active relations；
- 过滤 turnover cases；
- 读取 bank categories；
- 逐 relation 更新 metadata；
- 再触发 downstream refresh。

该链既违反 frozen-at-creation，也使 legacy rule save 具有 O(active relations) 的同步 I/O。应删除调用、函数、专用 tag/rule derivation/current-check helpers、常量和无用 imports。规则保存只影响以后创建的 relation；历史纠错只通过受控一次性 repair。

## UI reuse

现有前端合同已足够：

- API mapper：`missing_row_types -> missingRecordTypes`。
- `RelationGroupGrid`：incomplete relation 的空 pane 显示“待补 OA/发票”。
- 页面已经区分 paired/unpaired relation groups。

因此只补 mapper/render regression，不修改 production TSX，不增加新 DTO/status/copy。

## Performance evidence and budgets

本阶段不建立新缓存或 worker。可自动证明的性能合同：

- bank rows provider 调用次数不高于修复前；
- rules provider 每次 closure confirm 至多一次；
- requirement 计算 O(选中 tag 数)；
- legacy no-OA rule save relation list/update 调用数为零；
- 无 per-row/per-tag/per-month 新 I/O；
- no relation full-table scan 留在用户请求路径。

生产 latency 只通过仓库已有受控 read-model SLO/write-operation E2E 工具和 test-owned 可恢复场景验证。计划不把截图业务数据当 fixture，不虚构 p99、数据规模或未核实 CLI 参数。

## Test architecture

七类全部适用：

| Category | Evidence |
| --- | --- |
| Business core | requirement 四组合、多标签 OR、unknown/missing fail closed、selected-bank 完整性、保留 ETC/batch 例外 |
| Service layer | cached bank rows、单次 rules provider、frozen metadata、UoW/idempotency/rollback、no-OA 无 relation scan |
| API contract | confirm response shape/权限/version/freshness 不变；fresh Workbench GET 返回正确 zone/completion |
| Read model/cache/worker | v6 month/all/cache 失效，v5 不冒充 fresh，existing worker 原子 rehydrate |
| Frontend interaction | mapper + missing OA/发票 render；loading/stale/permission 既有回归 |
| E2E | confirm -> active unpaired -> add OA -> same case paired -> withdraw/recover；双 false direct paired |
| Existing regression | ordinary Workbench、OA-bank merge、invoice、bank-flow、no-OA、batch-accounting、ETC、Turnover chips/downstream |

## Docs impact assessment

必须修正：仍把 active relation 等同 paired、写死 turnover requirement、或描述规则保存追溯同步历史 relation 的段落。

按实际差异更新：

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/modules/turnover-ledger/`
- 必要的 `reconciliation-workbench`、`workbench-relations`、`bank-flow-rule-batches`、`read-models` 测试/实施记录

不机械更新：已经正确陈述 frozen requirements、incomplete active relation 同 case unpaired、规则保存不追溯、active generation 原子发布的文档；不修改 API、worker registry/manifest/env 文档。

## Plan split

### 26-01（wave 1，autonomous）

在线修复：先写失败测试，再删除 completion bypass、冻结真实 policy、加 selected-bank 完整性 guard、删除 legacy no-OA sync、补最小 docs 与回归。该计划不触碰 repair/version/生产。

### 26-02（wave 2，human-gated）

历史与发布：扩展现有 repair ops 的 forward/rollback 四模式、bump v6、跑自动验证，然后停在生产 checkpoint。生产按 exact release 上传不激活 -> captured previous baseline -> candidate dry-run -> activate -> final dry-run/重新审批 -> execute/target=0 -> rehydrate -> readiness/Audit/SLO/E2E；post-execute 失败先 exact metadata rollback，再激活并 rehydrate previous release。

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| 删除 bypass 使旧错误 metadata 立即参与分区 | v6 使旧 generation stale；deploy 后先 repair，再原子 rehydrate |
| 合并关系含未选择 bank member，snapshot 不完整 | D-03 guard fail closed，要求转 Workbench，不额外读取 |
| rule provider unavailable | fail closed；不回退写死值或 no-OA settings |
| repair 改错历史关系 | metadata preimage+after-image fingerprint、original-plan rebuild、fixed actor/operation/idempotency、history、备份和 human approval |
| repair 后发布验证失败 | exact history metadata rollback；首写前 after-image drift 全量校验，原地替换 metadata 而不改变 ownership/lifecycle，drift 则零写入 hard stop；成功后 target=0 再切 previous release |
| 其它 relation mode 受影响 | 只删除 turnover 条件；ETC/batch 和普通 relation 回归 |
| 生产操作误连真实库 | 自动计划禁止 repair CLI；所有生产命令放 human-action checkpoint |
| 文档扩散 | 只更新过时事实，正确文档不机械改 |
