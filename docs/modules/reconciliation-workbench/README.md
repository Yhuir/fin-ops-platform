# 关联台模块维护入口

- Module key：`reconciliation-workbench`
- 类型：页面模块
- Route：`/`
- Page key：`reconciliation-workbench`

## 修改前必读

- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 当前业务边界

关联台是 canonical OA、银行流水和发票事实与 active 正式关系的读写工作台。页面只有 `paired` 和 `unpaired` 两个关系区：满足冻结 OA/发票要求的 active relation 进入 `paired`；未满足要求的 active relation 保持同 case 分组进入 `unpaired` 并显示缺失类型；无 active owner 的 canonical facts 各自作为单行进入 `unpaired`。

页面不拥有自动候选、matching decision 或第三种关系状态。确定性引擎满足安全规则时直接通过正式关系命令边界创建 active relation；不满足时不写关系，事实仍保持可见的未配对单行。

关系来源（人工、历史或系统）只进入审计 provenance，不参与页面分区。历史 case id 的字符串前缀不能覆盖当前 active relation 状态。

## 运行链

```text
canonical fact repositories
  -> PostgresWorkbenchFormalRelationFactRepository
  -> WorkbenchFreeMatchingEngine (pure, no I/O)
  -> WorkbenchMatchingOrchestrator
  -> WorkbenchRelationCommandService + relation UoW
  -> app.workbench_pair_relations/history + durable outbox
  -> workbench/workbench_relation workers
  -> active generation
  -> WorkbenchRelationGroupingService
  -> paired / unpaired API
  -> ReconciliationWorkbenchPage
```

`workbench` 保留 active-generation 原子发布模型。页面、route 和 cache 不得绕过 freshness/status/enqueue 边界，也不得从旧 snapshot、旧 candidate/decision 表或 row metadata 恢复关系。

## 代码入口

- 前端：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroupGrid.tsx`、`RelationGroupCell.tsx`
- API：`web/src/features/workbench/api.ts`、`backend/src/fin_ops_platform/app/routes_workbench.py`
- 分组：`backend/src/fin_ops_platform/services/workbench_relation_grouping.py`
- 匹配：`backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`
- Matching I/O：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py`
- 正式关系写入：`backend/src/fin_ops_platform/services/workbench_relation_command_service.py`、`workbench_uow.py`
- SQL projection/read model：`backend/src/fin_ops_platform/services/workbench_sql_projection.py`、`postgres_repositories/read_models.py`
- Worker：`backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`、`workbench_read_model_refresh.py`
- 固定契约版本：`backend/src/fin_ops_platform/services/workbench_read_model_version.py`

## 三栏纵向展示合同

- OA、银行流水、发票栏默认各自跨越完整关联组高度；同栏有 `N` 条可见记录时由 CSS Flex 等分可用高度，单条记录占满整栏。
- 只有已有 `sourceOaId` / `sourceExpenseItemId` 对当前可见目标形成完整、唯一、无缺口的一一对应时，该栏才与 OA 或费用子项共享行轨。部分来源、一对多、多对一、重复来源或未链接记录一律保持 group-level，不制造空白来源槽位。
- 前端不再按金额相等或 2～6 条金额组合推断视觉对齐；正式 relation alignment metadata 仍由后端事实源提供。布局判断只消费已加载 DTO，是 `O(OA + bank + invoice)` 纯计算，不增加 HTTP、数据库、cache、worker、React state/effect 或 DOM 测量 I/O。
- 多项目报销继续显示父 OA 摘要和费用子项；只有全部目标子项与发票形成完整一一对应时发票才按子项同行，部分附件发票独立占满发票栏。银行流水不进入虚拟费用子项槽位。

## 不变量

- `paired = complete active relation members`。
- `unpaired = incomplete active relation members + unowned canonical facts`。
- 两区不相交且完整覆盖 canonical facts。
- 无 active owner 的未配对事实永远是 singleton；未闭环 active relation 只能按其 canonical case 分组，旧 `case_id` 和候选 metadata 不能合并无 owner 事实。
- 一个 canonical member 最多属于一个 active relation。
- 未知 zone、group type、relation mode、重复 identity、缺失 active member 或跨 case 占用冲突均 fail fast。

## 维护文档

- `boundary-io.md`：模块边界、I/O、依赖方向、迁移与删除条件。
- `state-machine.md`：页面、正式关系与 read model 状态。
- `tests.md`：七类测试、命令和生产核验。
- `implementation-notes.md`：历史实施记录，不是当前业务事实源。
