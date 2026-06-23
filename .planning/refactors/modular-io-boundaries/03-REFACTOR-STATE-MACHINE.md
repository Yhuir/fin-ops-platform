# 模块化 IO 重构状态机

**用途:** 约束全局重构和单模块重构的推进顺序，避免跳过合同、测试或回归闸门。

## 全局状态机

```text
AnalysisOnly
  -> ArchitectureContractReady
  -> PilotSelected
  -> PilotContracted
  -> PilotMigrating
  -> PilotVerified
  -> ProductionValidationPending
  -> AutonomousContinue
  -> TemplateRevised
  -> ModuleRollout
  -> GlobalClosure
```

### AnalysisOnly

当前状态。本阶段只做分析、需求、文档骨架和模板，不改业务代码。

进入条件：

- 用户明确要求先不开始重构实现。
- `.planning/refactors/modular-io-boundaries/` 已创建。

退出条件：

- 需求文档、当前状态审计、IO 合同模板、状态机、路线图、影响测试闸门和试点选择文档完成。

### ArchitectureContractReady

模块化 IO 合同和重构规则已清晰，可用于选择试点。

进入条件：

- `00-REQUIREMENTS.md` 完成。
- `02-MODULE-IO-CONTRACT-TEMPLATE.md` 完成。
- `05-IMPACT-AND-TEST-GATES.md` 完成。

退出条件：

- 试点模块已按 `06-PILOT-SELECTION.md` 选定。

### PilotSelected

只选模块，不开始实现。

进入条件：

- 明确首个试点模块。
- 试点模块的业务风险、代码热点、测试入口和文档入口已登记。

退出条件：

- 试点模块已有完整 IO 合同草案。

### PilotContracted

试点模块合同完成，但尚未迁移代码。

进入条件：

- 完成目标模块 IO 合同。
- 完成影响分析。
- 完成测试合同。
- 明确 legacy path 保留/迁移/删除策略。

退出条件：

- 试点 phase 计划完成并被批准开始实现。

### PilotMigrating

试点模块小步迁移中。

进入条件：

- 有明确实现计划。
- 有测试先行或测试补齐任务。
- 变更范围只覆盖试点模块和必要共享边界。

退出条件：

- 代码迁移完成。
- 所有适用测试和验证命令已运行。
- docs impact 已处理。

### PilotVerified

试点模块完成验收。

进入条件：

- 模块测试、API contract、read model/worker、前端交互、回归测试通过或剩余风险明确。
- 模块文档同步。
- 未引入未登记跨模块影响。
- legacy path 删除/隔离证据完成，旧代码不会污染新链路。
- read model force refresh、freshness proof 和跨页面重读边界已验证或明确不适用。

退出条件：

- 根据试点经验修订模板。

### ProductionValidationPending

本地、fake/stub、contract、前端和静态验证已经完成，但由于没有本地 `PGSQL_URL` 或 staging 数据库，真实 PostgreSQL/read model/worker/OA 链路尚未生产验证。

进入条件：

- 所有可本地运行的测试已通过。
- 真实环境验证项已列出。
- 生产验证 runbook 已注明只读或受控写入。

退出条件：

- 生产只读验证完成，或受控写入验证在审批/备份/回滚方案下完成。
- 未执行项有明确风险接受记录。

自动推进规则：

- 这是软状态，不阻塞继续处理其它模块。
- 若无 staging/`PGSQL_URL` 是唯一缺口，记录 `production-evidence-deferred` 后进入 `AutonomousContinue`。
- 只有需要生产写入、secret 或特权操作时才进入 hard stop。
- 自动推进开始和每个 slice 提交前必须执行 planning-state reconciliation check：若 `.planning/ROADMAP.md`、`.planning/refactors/README.md`、本目录 `README.md`、`00-REQUIREMENTS.md`、`04-IMPLEMENTATION-ROADMAP.md`、`autonomous/STATE.md`、`MODULE-QUEUE.md`、`JOURNAL.md`、`NEXT-PROMPT.md` 的状态口径互相矛盾，先完成 `planning:state-reconciliation-and-roadmap-alignment` 文档状态同步 slice，再继续代码或模块实现。
- 完成度报告必须标注来源，至少区分 root page-analysis roadmap、modular IO phase roadmap 和 modular IO autonomous queue；禁止用一个未标注来源的百分比代表“整个重构计划”。
- `autonomous/MODULE-QUEUE.md` 的 `Status` 是 slice 状态，不是模块完成状态。`analysis-closed`、`contract-guard-closed`、`static-guard-closed`、`regression-guard-closed`、`route-guard-closed`、`inventory-guard-closed`、`implementation-closed` 和 `planning-closed` 只表示该窄 slice 已关闭，不能作为 `Closed` 模块状态或全局闭环证据。
- 模块实现闭环必须单独看 `Module Closure` 和 `04-IMPLEMENTATION-ROADMAP.md` 的完成标准。只要存在 `implementation-pending` 或 `implementation-gap-open`，自动流程必须优先推进实现/验证/legacy 隔离相关边界，而不能跳到 Go hot-path admission。
- Go hot-path candidate 只有在相关模块 IO contract、legacy retirement/quarantine、freshness proof、测试、性能证据、shadow run 和 rollback gate 均满足后，才能从 `blocked-by-prerequisite` 进入 `pending`。
- 每个自动推进 slice 在进入 commit 前必须经过状态机更新闸门：先判断是否改变全局 workflow state/transition/guard 或模块状态定义；若改变，必须同步本文件或对应 `docs/modules/<module>/state-machine.md`；若未改变，必须在 analysis 文件中记录 reviewed files、definition unchanged 原因和只更新 progress/accounting 的证据。
- `autonomous/NEXT-PROMPT.md` 只是续跑入口，不是完整状态机。任何 closed/deferred/blocked/failed slice 都必须同步更新 `autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md` 和对应 analysis 文件。

### AutonomousContinue

当前模块已达到本地/contract/fake/stub 可验证闭环，生产证据缺口已记录，自动运行可以继续下一个模块。

进入条件：

- 模块有 commit/push 或明确无需代码改动。
- 测试和 docs impact 已记录。
- 缺少的生产证据不要求生产写入、不要求 secret、不要求 root。

退出条件：

- 选择下一个 pending 模块。

### TemplateRevised

试点反馈已回流模板。

进入条件：

- 合同模板、测试闸门、prompt 模板根据试点修订。

退出条件：

- 选择第二批模块。

### ModuleRollout

按批次推广到其它模块。

进入条件：

- 试点已验证。
- 每批模块数量受控。

退出条件：

- 所有目标模块达到单模块完成定义。

### GlobalClosure

全局重构闭环完成。

进入条件：

- 所有目标模块有 IO 合同。
- legacy route/service/repository/read model/frontend API 路径已删除，或被隔离为有 owner、调用者清单、删除条件和测试保护的 `compat-only`。
- 旧链路不能写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status。
- 所有跨页面 read model 具备受控 force refresh 合同和 freshness proof。
- 所有页面/domain read model 的 partitioned scoped + scoped incremental 目标策略已登记，Workbench active generation 例外已明确。
- Go candidate 已按 `11-GO-HOT-PATH-CARVE-OUT.md` 完成准入、延期或关闭记录；没有未经批准的 Go/Fiber 自动迁移。
- `server.py` 和大 repository 的剩余职责有长期 owner。
- 回归测试和 docs 已闭环。

## 单模块状态机

```text
NotStarted
  -> Auditing
  -> ContractDrafted
  -> GapMapped
  -> PlanReady
  -> Migrating
  -> Verifying
  -> Verified
  -> ProductionValidationPending
  -> AutonomousContinue
  -> Closed
```

### NotStarted

尚未分析。

禁止：

- 直接拆文件。
- 直接迁移调用点。

### Auditing

读取模块文档、代码入口和测试入口。

必须产出：

- 当前 entry point 清单。
- read model/worker/operation barrier 清单。
- force refresh 入口和 freshness proof 清单。
- partition key、scope key、incremental projection 和 full rebuild fallback 清单。
- legacy route/service/repository/read model/frontend API 清单。
- 如涉及 Go candidate，列出 candidate key、性能证据、shadow run 可行性和 rollback 条件。
- 权限/审计清单。
- 跨模块影响清单。

### ContractDrafted

完成 IO 合同草案。

必须产出：

- 输入/输出/状态/事件/read model/权限/测试合同。
- Legacy 退役与隔离合同。
- Read model force refresh 合同。
- Partitioned scoped incremental projection 合同。
- 如进入 Go candidate，Go / Fiber / Go Worker carve-out 合同；否则标记 not applicable。
- public/internal surface。
- allowed/forbidden dependency。

### GapMapped

当前实现与合同差异已登记。

必须产出：

- Gap list。
- 每个 gap 的风险、影响模块、测试需求。
- 迁移顺序建议。

### PlanReady

实现计划已准备好，但还没改代码。

必须产出：

- 小步迁移任务。
- 测试先行任务。
- 回滚策略。
- docs impact。

### Migrating

正在按计划修改代码。

限制：

- 一次只迁移一个明确边界。
- 不做无关清理。
- 不改变业务行为。
- 不保留未登记旧写入路径。
- 不让新链路调用旧模块 internal-only surface。

### Verifying

运行测试和验证。

必须执行：

- 模块内测试。
- 受影响共享边界测试。
- 前端交互测试或说明不适用。
- 回归测试。
- legacy contamination 测试或调用图/import 检查。
- read model force refresh、freshness 和跨页面同步测试。
- partitioned scoped incremental projection 测试或合同替代证明。
- 如进入 Go candidate，Python-vs-Go equivalence、shadow run、防双写和 rollback 测试。
- 环境限制检查；没有 `PGSQL_URL`/staging 时列出真实 DB/worker 待验证项。

### Verified

代码和文档已通过验收。

必须满足：

- 测试结果记录。
- 剩余风险记录。
- 长期文档更新或 docs 不适用说明。
- 旧链路删除或 `compat-only` 隔离结果记录。
- Read Model 强制刷新合同和 freshness proof 记录。
- Partitioned scoped incremental projection 结果记录。
- 如进入 Go candidate，Go admission、shadow run、equivalence、rollback 和 production evidence 结果记录。
- 如没有真实 DB/worker/staging 验证，必须转入 `ProductionValidationPending`，不能直接 `Closed`。

### Closed

模块重构闭环完成。

条件：

- legacy path 删除或保留理由明确。
- 旧路径不能污染新链路的证据明确。
- 跨页面 read model freshness 和 force refresh 验证明确。
- read model partition/scope/incremental projection 验证明晰。
- Go candidate 关闭、延期或不适用状态明确。
- 后续风险登记到 risk register。

说明：

- `Closed` 表示代码、合同、测试、文档和可用验证均闭环。
- 没有 staging/`PGSQL_URL` 时，自动运行可以使用 `AutonomousContinue` 继续推进，但不能把缺失的真实生产 DB/worker 证据伪装成已完成。

## 禁止状态跳跃

- `NotStarted` 不能直接进入 `Migrating`。
- `Auditing` 不能跳过 `ContractDrafted`。
- `PlanReady` 不能没有测试合同。
- `Verifying` 不能没有 docs impact。
- `Verified` 不能有未解释的失败测试。
- `Verified` 不能保留未登记、可写入新事实源的 legacy path。
- `Verified` 不能缺少适用的 read model force refresh/freshness proof。
- `Verified` 不能缺少适用的 partitioned scoped incremental projection 合同。
- `Verified` 不能包含未通过 candidate gates 的 Go/Fiber/Go Worker 实现。
- 没有真实 DB/worker/staging 验证时，`Verified` 不能直接进入 `Closed`。

## Go Hot Path Candidate 状态

Go/Fiber/Go Worker 是候选门控分支，不是所有模块的默认迁移路径。

```text
NotCandidate
  -> CandidateListed
  -> GoAdmissionReview
  -> GoShadowReady
  -> GoMigrating
  -> GoVerified
  -> GoClosed
```

允许延期：

```text
CandidateListed -> GoCandidateDeferred
GoAdmissionReview -> GoCandidateDeferred
GoMigrating -> GoRolledBack
```

准入条件：

- candidate 在 `11-GO-HOT-PATH-CARVE-OUT.md` 中。
- 性能证据存在。
- IO contract、legacy isolation、freshness proof、rollback 和 shadow run 条件齐全。

禁止：

- 候选列表之外自动 Go 化。
- 未通过 admission gates 直接进入 `GoMigrating`。
- Fiber handler 承载长时间后台任务。
- Python worker 和 Go worker 同时 authoritative ack 或 publish 同一 scope。

## 回滚状态

```text
Migrating -> RolledBack
Verifying -> RolledBack
```

触发条件：

- 测试发现跨模块回归。
- 发现合同错误或遗漏关键事实源。
- 实现扩大到未批准业务范围。

回滚后必须：

- 记录触发原因。
- 更新 gap list。
- 修订计划后再进入 `PlanReady`。
