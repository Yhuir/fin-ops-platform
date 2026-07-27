# 关联台正式关系模块维护入口

- Module key：`workbench-relations`
- 类型：资源模块
- Route：N/A

## 当前事实源

`app.workbench_pair_relations` 是 OA、银行流水和发票跨页面正式关系的 canonical write model，`app.workbench_pair_relation_history` 是不可丢失的审计历史。`workbench_relation` 是下游 scoped distribution read model。

正式关系不按人工、历史或系统来源拆分业务状态。来源只记录 provenance；当前有效性只由 `status=active` 决定。

自动匹配没有候选/decision 持久状态。确定性引擎只生成 `FormalRelationPlan`，并通过 `WorkbenchRelationCommandService` + relation UoW 直接写 active 正式关系；不安全、不唯一或资源受限时不写任何关系。

## 核心边界

- `WorkbenchPairRelationService`：纯领域规则，负责 row 独占、replace/cancel/withdraw/history 计算。
- `WorkbenchPairRelationService.apply_snapshot_delta(...)`：只把已持久化的 changed cases 增量同步到进程内镜像；不读取、复制或重建无关 relation/history。
- `WorkbenchRelationCommandService`：所有 relation mutation 的统一 command 边界；confirm overlap 只读取 active relations，command save 只输出 changed relations 与本次新 history events。
- `PostgresWorkbenchRelationRepository`：正式关系/history SQL owner；active case/row overlap 校验使用不加载 history 的窄读取，在线 command history 只追加；全量 history replacement 只留给 migration/repair。
- `WorkbenchRelationUow`：relation、history、idempotency、audit/refresh outbox 的事务边界。
- `WorkbenchRelationReadFacade`：下游 linked/unlinked 查询与 freshness 边界。
- `WorkbenchRelationSqlProjection`：active relation -> `workbench_relation` distribution。

## 调用方

- 关联台人工确认/撤回与系统确定性自动正式化。
- pending invoice attach/manual invoice。
- no-OA batch/internal transfer。
- turnover manual closure。
- batch accounting。
- ETC batch/link/repair。
- input invoice OA reverse。
- Workbench exception 的正式闭环动作。

上述调用方只能通过 command service/UoW 写关系，不得直接改 `app.workbench_pair_relations`，也不得用 read model 或页面状态反向写 canonical relation。

## 下游语义

- active relation member：`linked`。
- 无 active relation：`unlinked`。
- 不输出 `candidate`，也不读取已删除的 candidate/decision 表。
- 关联台页面专属 canonical repository 直接读取 `app.workbench_pair_relations.status='active'`：冻结要求已满足时显示为 `paired`，未满足时保持同 case 显示为 `unpaired`，无 active owner 的 canonical facts 显示为 singleton `unpaired`。
- 关联台页面不消费 `workbench_relation` distribution 或 Workbench active generation；其他下游仍按各自合同消费 linked/unlinked projection。

## 页面写入安全

- confirm/withdraw preview 从关联台 canonical query repository 有界读取所选 rows，只用于展示与 `preview_id`。
- submit 不接收 `expected_read_model_version`；relation UoW 在同一事务内重新验证 canonical identities/types、active relation member ownership、expected business versions 和幂等 fingerprint。
- preview 后对象消失、类型改变、成员被其它 active case 占用或版本冲突均返回 `409`，不得信任旧 preview DTO 继续写入。

## 文档

- `boundary-io.md`：owner、I/O、依赖、relation modes 与删除条件。
- `state-machine.md`：关系生命周期、并发和撤回。
- `tests.md`：七类测试与验证。
- `implementation-notes.md`：历史实施记录，不是当前合同。
