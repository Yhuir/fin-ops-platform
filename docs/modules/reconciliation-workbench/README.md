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

- 前端：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroupGrid.tsx`、`RelationGroupCell.tsx`、`WorkbenchExceptionDrawer.tsx`
- API：`web/src/features/workbench/api.ts`、`backend/src/fin_ops_platform/app/routes_workbench.py`
- 分组：`backend/src/fin_ops_platform/services/workbench_relation_grouping.py`
- OA/发票异常：`backend/src/fin_ops_platform/services/workbench_amount_check_service.py`、`workbench_amount_mismatch_exception_service.py`
- 匹配：`backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`
- Matching I/O：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py`
- 正式关系写入：`backend/src/fin_ops_platform/services/workbench_relation_command_service.py`、`workbench_uow.py`
- SQL projection/read model：`backend/src/fin_ops_platform/services/workbench_sql_projection.py`、`postgres_repositories/read_models.py`
- Worker：`backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`、`workbench_read_model_refresh.py`
- 固定契约版本：`backend/src/fin_ops_platform/services/workbench_read_model_version.py`

## OA/发票异常合同

- 日常报销按 OA 子付款项与全部显式绑定发票比较；支付申请按关系组 OA/发票总额比较。金额完整且不相等时生成 `金额不一致`；子付款项有上传附件但零已解析绑定发票时生成 `OA发票附件缺失`。每个比较单元只投影一个 chip，不创建第三种关系状态或展示级发票事实。
- active/ignored 决定复用既有 exception case repository，但只认独立 `oa_invoice_amount_mismatch` scenario；历史 WEX/row-ignore 记录仅保留审计，不得进入 generation、异常桶、计数、主区可见性或 source freshness。
- 页面只保留统一 `WorkbenchExceptionDrawer`：进行中展示 active OA/发票异常，已忽略展示 ignored OA/发票异常。每个关系组默认只显示三栏成员数与总金额，按需展开完整三栏，忽略/撤回忽略直接作用于该关系组；入口文案固定为 `异常 n | 已忽略 m`，旧确认 modal、legacy WEX/row-ignore 抽屉入口、`IgnoredItemsModal` 和 `ProcessedExceptionsModal` 均不得恢复。

## 三栏纵向展示合同

- OA、银行流水、发票栏默认各自跨越完整关联组高度；同栏有 `N` 条可见记录时由 CSS Flex 等分可用高度，单条记录占满整栏。
- 单一日常报销父 OA 展开为多个付款项时，只有父 OA 归属、没有费用子项归属的银行流水继续作为整单证据跨越摘要与全部付款项高度，不得被压进父 OA 摘要行。
- 单条银行流水/发票与 OA 或费用子项金额按分精确相等且双方唯一时共享行轨，不再要求整栏完整覆盖。显式 `sourceOaId` / `sourceExpenseItemId` 优先；API 映射必须优先 canonical `source_oa_id` / `source_oa_row_id`，历史 `derived_from_oa_id` 只作兜底，不能覆盖 canonical ownership。显式费用子项 ownership 不以金额相等为前提。缺少显式来源时，只允许在同一完整 source group、方向已知且金额双方都唯一时做展示级精确金额兜底。
- 同一费用子项下的所有显式绑定附件发票共享一个复合行轨；费用子项占满该轨高度，发票在轨内等分。即使合计金额不等，也保持同行并由异常 chip 表达差异。筛选后缺少任一组成发票时不建立部分复合同行。
- 其他父 OA 级一对多/多对一、重复来源、重复金额、零/非法金额、方向未知或冲突，以及无显式费用子项归属的 2～6 条金额合计都不建立同行；已分段栏中的这些记录进入独立残余展示带，完全没有精确配对的栏继续按 group-level 占满整组高度。金额兜底不写 relation、不改变 membership、selection 或 action identity。
- 多项目报销继续显示父 OA 摘要和费用子项；满足单条精确条件或上述显式费用子项复合条件的附件发票逐项同行，其余附件留在残余展示带。缺失附件发票的展示位只显示 `OA发票附件缺失`，不得再叠加历史 `未识别附件` 来源标签。发票比较金额统一使用价税合计，银行流水使用当前方向金额。
- 布局判断只消费已加载 DTO，是 `O(OA + bank + invoice)` 的 Map/Set 纯计算，不增加 HTTP、数据库、cache、worker、React state/effect、DOM 测量或依赖。

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
