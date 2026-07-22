# Phase 26 Context：外部往来闭环按冻结 OA/发票要求分区

日期：2026-07-22

## 目标

修复外部往来款“确认闭环”后的关联台分区语义：确认闭环只创建或合并 canonical active relation，active relation 只代表成员归属；只有关系创建时冻结的 Bank Transaction Paired Policy 已满足，关系才进入关联台 `paired`。冻结要求未满足时，关系保持同一个 case 出现在 `unpaired`，并显示“待补 OA/发票”。

当前复现场景的规则为 `requires_oa=true`、`requires_invoice=false`，因此 bank-only turnover closure 必须留在未配对区等待 OA；补入 OA 后，同一个 case 才进入已配对区。

## 已确认根因

1. `evaluate_bank_relation_completion(...)` 对 `relation_mode=turnover_manual_closure` 无条件返回 complete，绕过 relation 上冻结的 `requires_oa/requires_invoice`。
2. `TurnoverLedgerWorkbenchPairPort.create_turnover_manual_closure(...)` 写死 `requires_oa=true`、`requires_invoice=false` 和旧 source/version，而不是从流水实际标签与规则标签管理读取真实 policy。
3. legacy no-OA 标签保存仍扫描并追溯改写 active turnover relations，既违反“创建时冻结”的合同，也给规则保存热路径增加无界 relation I/O。
4. 现有错误测试把 bank-only turnover closure 直接进入 paired 固化为预期，必须先改为正确失败合同。

## 决策

### D-01：active ownership 与 completion 分离

- `status=active` 只表示 canonical relation 拥有这些 typed members。
- Workbench zone 只由统一 completion 判定决定：要求全部满足进入 `paired`；否则保持同 case 进入 `unpaired`。
- 只删除 turnover 的无条件 complete 例外；batch-accounting 和 ETC 的现有明确例外不在本阶段改变。

### D-02：确认时冻结真实 Bank Transaction Paired Policy

- 复用已有 `build_bank_relation_requirement_metadata(...)`，不得新建 policy service/helper。
- 标签输入来自本次确认已选择银行流水的有效主/子标签 code；多标签按 OA/发票要求分别 OR。
- 未知标签、缺失规则、空标签继续使用现有 helper fail closed。
- relation metadata 冻结 canonical source、tag codes、rule version、`requires_oa` 和 `requires_invoice`；后续规则保存不追溯改写历史 relation。
- 复用 `TurnoverLedgerBankRowSelectionPort` 已获取的 request-scoped rows/cache；每次确认 rule provider 至多调用一次，银行 list I/O 不增加。

### D-03：合并关系必须满足 selected-bank 完整性

- turnover closure 可以合并所选银行流水已拥有的 OA-bank active relations。
- 合并后最终 relation 的每一个 bank member 必须属于本次 `selected_bank_row_ids`。
- 如果既有 relation 含未选择 bank member、invoice、未知 row type 或其它不允许 owner，使用现有冲突/失败关闭路径，要求转 Workbench 处理；不得静默追加读取额外银行数据，也不得冻结不完整 policy snapshot。
- 该不变量保证 selected-row cache 覆盖最终全部 bank members，实现零额外 bank list I/O。

### D-04：删除旧污染链，不保留兼容 fallback

- 删除 turnover relation 创建时的写死 requirement metadata。
- 删除 `NoOaBankBatchApplicationService.update_tag_selection(...)` 对 active turnover relations 的 `_sync_turnover_rule_relation_requirements(...)` 调用。
- 删除只服务该同步的扫描、标签推断、metadata compare/update helpers、常量和无用 imports。
- 不增加第二套同步、历史兼容 fallback 或 route/query 临时判断。

### D-05：历史修复与 Workbench v6 分阶段发布

- 扩展现有 `workbench_relation_requirement_repair_ops`，不新建 repair 工具。
- active turnover relation 若 `paired_requirement_source != bank_transaction_paired_policy`（含旧 `turnover_ledger_manual_closure`、`no_oa_bank_batch_tag_selection`），或缺 canonical tag codes/version，则属于 legacy-invalid repair target。
- ETC/batch 继续 exempt；ordinary missing snapshot 保持现有兼容行为，不被本阶段顺手改口径。
- repair 继续使用同一个 ops module、固定 actor、审计 history、幂等 key 和 `WorkbenchRelationCommandService`；禁止 direct SQL、新 runtime service/helper/API/table/worker/read model。
- forward fingerprint 必须覆盖每个 target 的 current metadata preimage 与 intended after image；execute 的 history note、operation 和 idempotency 均绑定原始 fingerprint。重跑时以 fresh targets 与 fingerprint-bound histories 合并重建 original plan：已应用 case 在 current 等于 recorded after 后 skip，未应用 case在 current 等于 recorded before 后继续；合并 fingerprint 不一致则首写前失败。
- 同一 ops module 增加显式 `--rollback-dry-run` / `--rollback`，两者都要求原始 execute fingerprint。rollback 只选取 `list_history()` 中匹配 fingerprint/actor/operation 的完整 before/after metadata history，并在首写前批量确认 current active relation 等于 recorded after image；任一 drift 全部零写入失败。
- rollback 复用现有 `update_relation_metadata_for_case_id(... replace_special_metadata=True)` canonical UoW 原地精确恢复完整 `special_metadata` preimage，使用固定 rollback actor/operation/fingerprint-bound idempotency并生成 durable history/outbox；不得 cancel/recreate relation，members/status/mode/lifecycle/created fields 不变，只有正常 update 的 updated_at/history 前进，成功或幂等重放后 rollback dry-run target 为 0。
- `replace_special_metadata` 在 pair service 与 command service 上默认 false，所有旧 caller 的 metadata merge 合同不变；只有 repair rollback 显式 true，command request fingerprint 必须包含该 flag。这是现有边界的最小扩展，不是新 service/helper/API/DTO。
- `finops-deploy-control` 只增加上述同一 module 的四个固定透传模式，不增加 release rollback 子命令。
- Workbench month/all schema 从 v5 升 v6，使旧 generation/cache 不能冒充 fresh；使用现有 active-generation 原子 rehydrate。

### D-06：最小 UI、验证、性能和生产边界

- 前端现有 API mapper 与 `RelationGroupGrid` 已支持 `missing_row_types` 和“待补 OA/发票”；不修改 production TSX，只补 mapper/render 回归。
- 不新增 API、DTO、表、migration、worker、read model、运行时 service/repository/helper 或依赖。
- 自动任务只跑单元、service、API、read-model、前端与 E2E 测试；不得直接运行 repair CLI 连接真实数据库。
- 生产 dry-run/execute/rollback/rehydrate 只能在 `checkpoint:human-action` 中通过受控 deploy-control 命令执行。发布先上传但不激活 exact release，在 previous release 建立同一 test-owned 可逆基线；激活后以 final dry-run fingerprint 重新审批，execute 后要求 target=0 再 rehydrate。
- 生产证据必须包含 exact release、captured previous release、备份/restore point、approval ticket、正式 readiness 的 exact runtime release 与 queue/worker blockers=0、identity Audit、三个 admin Page Audit/System Audit、同场景 baseline 比较和四个 safety ceilings。post-execute 失败先做 fingerprint-bound metadata rollback，再激活 previous release 与 rehydrate；drift hard stop。
- 性能只断言可观测事实：rule provider 每次确认至多一次、bank provider 调用数不增加、legacy rule save 无 relation 全表扫描；生产延迟通过已有受控 SLO 工具验证，不虚构 p99 或未确认命令参数。

## 模块边界与 I/O

| 边界 | 输入 | 输出 | 不变量 |
| --- | --- | --- | --- |
| Turnover request boundary | selected bank ids、expected versions、actor、idempotency、affected months | 现有 confirm response/freshness targets | HTTP shape、权限、stale 和幂等合同不变 |
| Turnover write adapter | request-scoped selected rows + 一次 canonical rules payload | frozen requirement metadata + active relation | 最终 bank members 必须全部已选择；零额外 bank list I/O |
| Workbench relation owner | typed members、relation mode、frozen metadata | active relation/history/outbox | active 只表示 ownership |
| Workbench grouping/projection | canonical facts + active relations | paired/unpaired + completion | zone 只读 frozen metadata，不回查当前 settings |
| Legacy no-OA settings | legacy selection mutation | no-OA 自身状态/refresh | 不枚举或改写 turnover relations |
| Repair operator | active relation + fresh tags + canonical rules + original execute fingerprint + matched history | audited forward repair 或原地 exact metadata rollback + durable history/outbox | legacy-invalid active turnover only；original-plan rebuild；首写前 drift guard；ownership/lifecycle 不变；无 direct SQL |
| Workbench worker | v6 schema + durable refresh scope | new active generation | 原子发布；building/failed/旧 v5 不可作为 fresh |

## 范围

### 包含

- 在线根因修复、真实 policy snapshot、selected-bank 完整性校验。
- legacy no-OA turnover requirement 同步链删除。
- 对应业务/service/API/read-model/frontend/E2E/regression 测试。
- 历史 active turnover relation repair、Workbench v6、受控 rehydrate 与生产 checkpoint。
- 仅修正真正过时的长期产品/模块事实。

### 不包含

- 新增或改变前端业务组件、HTTP contract、数据库 schema、read model/worker registry。
- 改变 batch-accounting、ETC、普通 Workbench relation 的业务要求。
- 用当前规则追溯改写所有历史 relation 的运行时同步。
- 使用截图中的真实业务数据作为生产 smoke fixture。
- 自动执行生产 repair、deploy、rehydrate 或直接 SQL/readiness 修改。

## Docs impact assessment

确定更新：

- `docs/product-specs/bank-turnover-and-no-oa.md` 中仍把 active relation 等同 paired 的旧口径。
- `docs/modules/turnover-ledger/` 中写死 requirement 或“规则保存同步历史关系”的旧描述、边界、状态机、测试矩阵和实施记录。

按实际差异最小更新：

- `docs/modules/reconciliation-workbench/` 的测试/实施记录仅记录 completion 分区与生产验证。
- `docs/modules/bank-flow-rule-batches/` 的实施记录仅记录旧同步链删除。
- `docs/modules/read-models/` 的测试/实施记录仅记录 Workbench v6/rehydrate。
- `docs/modules/workbench-relations/` 当前边界若已经正确陈述 active ownership、frozen requirements 与 incomplete unpaired，则不修改；只有执行时发现冲突事实才先回报扩展范围。

不机械更新：

- 已经明确 `paired=complete active relation`、规则保存不追溯、active generation 原子发布的正确文档。
- API contracts、worker registry/manifest/systemd env，因为本阶段不改变这些合同。

## 验收

1. bank-only turnover relation 在 OA required 时同 case unpaired，并返回 missing OA。
2. 补 OA 后同 case paired；双 false policy 下 bank-only 可以直接 paired。
3. relation metadata 来自真实 tags/rules/version；多标签 OR、unknown/missing fail closed。
4. 合并关系出现未选择 bank member 时 fail closed，不发生额外 bank list I/O。
5. no-OA rule save 不再枚举/更新 turnover relations，旧符号运行时零引用。
6. 历史 legacy-invalid turnover relations 可被现有 repair ops 安全识别和幂等修复；同一原始 fingerprint 可由 fresh targets + exact histories 重建 original plan，并原地恢复完整 metadata preimage，drift 时零写入，partial execute/重放可恢复且 rollback 后 target=0；relation ownership/lifecycle/created fields 不变。
7. v5 generation/cache 失效，v6 rehydrate 原子发布；exact release/previous release、正式 readiness、Audit、同场景 E2E/SLO 和 post-execute rollback 顺序通过受控生产门。
8. 七类测试和其它 relation/page 回归通过；无新增运行时架构。
