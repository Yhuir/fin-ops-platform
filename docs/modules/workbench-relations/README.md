# 关联台正式关系模块维护入口

- Module key：`workbench-relations`
- 类型：资源模块
- Route：N/A

## 当前事实源

`app.workbench_pair_relations` 是 OA、银行流水和发票跨页面正式关系的 canonical write model，`app.workbench_pair_relation_history` 是不可丢失的审计历史。`workbench_relation` 是下游 scoped distribution read model。

正式关系不按人工、历史或系统来源拆分业务状态。来源只记录 provenance；当前有效性只由 `status=active` 决定。

自动匹配没有候选/decision 持久状态。确定性引擎只生成 `FormalRelationPlan`，并通过 `WorkbenchRelationCommandService` + relation UoW 直接写 active 正式关系；不安全、不唯一或资源受限时不写任何关系。

人工确认与自动匹配采用不同准入责任：人工确认允许任意至少 2 个不同 canonical 成员，只有既有 `amount_check.requires_note=true` 时才要求 `note` 审计说明；金额/方向检查和完整性仍影响备注门禁或关联台分区，但不再作为通用 active relation 创建门槛。银行成员的 `internal_transfer` 分类也不选择另一条人工写链：mixed 或全 `internal_transfer` 选择统一以 `manual_confirmed` 进入标准 command/UoW。唯一窄例外是 OA 与完整 canonical external-turnover 零差额闭环同时确认：业务 facade 复用现有 Turnover validator 后仍通过同一个 command/UoW 写 `turnover_manual_closure` evidence/history，不建立第二写链。自动匹配仍执行既有 exact-sum、强证据、唯一性与资源保护规则。

## 核心边界

- `WorkbenchPairRelationService`：纯领域规则，负责 row 独占、replace/cancel/withdraw/history 计算。
- `WorkbenchPairRelationService.apply_snapshot_delta(...)`：只把已持久化的 changed cases 增量同步到进程内镜像；不读取、复制或重建无关 relation/history。
- `WorkbenchRelationCommandService`：所有 relation mutation 的统一 command 边界；confirm overlap 只读取 active relations，command save 只输出 changed relations 与本次新 history events。
- relation withdraw：已配对或未配对 active case 都只接受与当前 active relation 完整成员集合精确相等的预览/提交，并以 expected versions 与拓扑 preview fingerprint 防止陈旧提交；恢复上一稳定拓扑前在同一关系事务中锁定并重验当前/恢复 case、canonical typed members 与唯一 active owner。任一证明漂移即 fail closed，无稳定 predecessor 才释放为 unlinked singleton。
- `PostgresWorkbenchRelationRepository`：正式关系/history SQL owner；active case/row overlap 校验使用不加载 history 的窄读取，在线 command history 只追加；全量 history replacement 只留给 migration/repair。
- `WorkbenchRelationUow`：relation、history、idempotency、audit/refresh outbox 的事务边界。
- `WorkbenchRelationReadFacade`：下游 linked/unlinked 查询与 freshness 边界。
- `WorkbenchRelationSqlProjection`：active relation -> `workbench_relation` distribution。

## 调用方

- 关联台人工确认/撤回与系统确定性自动正式化。
- pending invoice attach/manual invoice。
- 独立 no-OA batch 及其 owner 管理的内部往来批次。
- turnover manual closure。
- batch accounting。
- ETC batch/link/repair。
- input invoice OA reverse。
- Workbench exception 的正式闭环动作。

上述调用方只能通过 command service/UoW 写关系，不得直接改 `app.workbench_pair_relations`，也不得用 read model 或页面状态反向写 canonical relation。关联台人工 `confirm-link` 与独立 no-OA batch 是两个入口；前者不得因成员银行分类而转调后者。

## 下游语义

- active relation member：`linked`。
- 无 active relation：`unlinked`。
- 不输出 `candidate`，也不读取已删除的 candidate/decision 表。
- 关联台页面把冻结完成要求已满足的 linked active relation 显示为 `paired`；未满足的 linked relation 保持同 case 显示为 `unpaired`，无 active owner 的 canonical facts 显示为 singleton `unpaired`。其他下游仍只消费 linked/unlinked ownership，不消费关联台 zone。

## 文档

- `boundary-io.md`：owner、I/O、依赖、relation modes 与删除条件。
- `state-machine.md`：关系生命周期、并发和撤回。
- `tests.md`：七类测试与验证。
- `implementation-notes.md`：历史实施记录，不是当前合同。
