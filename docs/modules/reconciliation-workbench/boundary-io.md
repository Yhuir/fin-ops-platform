# 关联台模块边界与 I/O

日期：2026-07-14

## 职责

### 负责

- 查询 active generation，并把 canonical facts 精确划分为 `paired` / `unpaired`。
- 提供分页、搜索、详情、选择、正式配对、撤回和异常处理页面交互。
- 暴露 freshness/status/source versions，阻止 stale 数据伪装 fresh。
- 在 relation mutation 成功后等待明确的 operation barrier targets，再读取新投影。

### 不负责

- 不把 OA、银行流水、发票复制成新的统一写模型。
- 不持久化自动候选、matching decision 或 `open/proposed` 关系状态。
- 不根据金额、旧 `case_id`、UI metadata 或来源前缀在 route/前端本地推断关系。
- 不直接写 relation SQL、dirty scope SQL 或 outbox SQL。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| canonical rows | OA / bank / invoice repositories | 每行必须有稳定 `id`、`type`、`object_identity_key`；重复 typed identity fail fast |
| OA projection rows | PostgreSQL OA projection repository | 读取边界把持久化历史值 `section=open` 和缺失值归一化为 `unpaired`；只有 `paired|unpaired` 可进入 Workbench core，未知值 fail fast |
| active relations | workbench-relations | 只接受 `status=active` 的正式关系；row ids 必须存在且不可跨 case 重叠 |
| row overrides / exception cases | workbench control repositories | 仅对没有 active formal relation ownership 的 row 生效；优先级为 formal relation > override > exception，projection 与 Page Audit 必须共用该合同 |
| list query | Workbench API | `month`、zone=`paired|unpaired`、分页、搜索、排序、generation/source versions |
| row/group detail | Workbench read repository | 必须固定到同一 active generation；miss 不得合成占位行或回退旧 snapshot |
| confirm/withdraw command | Workbench action route | canonical row ids、actor、tenant、idempotency、expected versions、preview identity |
| matching scope | durable matching dirty queue | 合法 `YYYY-MM`；repository 读取 ±365 日组合窗口，显式引用可补载全部保留历史 |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| `paired.groups` | 前端 | 每组恰好对应一条 active formal relation，`group_type=relation` |
| `unpaired.groups` | 前端 | 每组恰好一个未被 active relation 占用的 canonical fact，`group_type=unpaired` |
| summary | 前端/App Health | `paired_count`、`unpaired_count`、OA/流水/发票事实数与 exception count |
| formal relation write result | caller | before/after、version、affected months、audit、outbox ids、barrier targets |
| matching summary | worker/App Health | planned/created/extended/preserved/ambiguous/resource-limited/unsafe counts；不输出候选 rows |
| read model generation | Workbench query | 新 generation 完整写入并校验后原子激活；building/failed 不可读为 fresh |

## 依赖方向

- route 只做 HTTP DTO/错误映射和依赖组装。
- `WorkbenchFreeMatchingEngine` 是纯函数边界，不读数据库、不写队列、不记录网络 I/O。
- `PostgresWorkbenchFormalRelationFactRepository` 是 matching 输入的唯一 SQL owner。
- `WorkbenchMatchingOrchestrator` 只编排 repository -> matcher -> 单次 relation UoW。
- `WorkbenchRelationCommandService` 拥有正式关系状态转换；repository/UoW 拥有 SQL、事务和 durable outbox。
- `WorkbenchRelationGroupingService` 只消费 canonical rows + active relations；display decorations 不得改变 membership 或 zone。
- 前端只消费 API，不读取 relation provenance 推断分区。

## Read model 与 worker

- `workbench` 使用 active-generation scoped publish；月分片发布必须原子。
- `month=all` 查询组合 active 月分片，并在分页前做唯一 canonical owner 仲裁。
- schema/version 由 `workbench_read_model_version.py` 统一提供，groups page cache 必须复用同一 projection schema；旧 generation 或旧 Redis page payload 不得冒充 fresh。
- collapsed-summary 是展示形态而不是第三种关系状态：repository 必须分别物化 `summary_row` 与全部 `collapsed_rows`；未配对 ETC summary 仍是一个 canonical singleton owner，旧 candidate/decision `case_id` 或 relation mode 不得泄漏为关系归属。
- matching scope、workbench scope 和 workbench_relation scope 都以 PostgreSQL durable queue/state 为事实源；Redis 只缓存 fresh payload，RabbitMQ 只做可选唤醒。
- Release A 上线后先执行一次全量 Workbench rehydrate，使旧 `open`/candidate/decision generation 被新的 paired/unpaired generation 原子替换；不得原地修改旧 active generation。Release B 的 0104 只在 A 的零访问和数据安全证据通过后执行。

## 旧链路删除合同

Release A 已删除运行时链路且禁止恢复；旧表物理存储只为短期回滚窗口保留，并由 Release B 删除：

- `workbench_candidate_matches` 与 `workbench_reconciliation_decisions` 的 repository/service/store/cleanup 和全部运行时访问。
- candidate grouping、special candidate rule、decision engine/models 和 candidate repair CLI。
- `automatic_decision` / `automatic_match` 作为 relation mode 或页面 group type。
- in-memory matching dirty-scope fallback 作为生产状态源。
- `CandidateGroupGrid` / `CandidateGroupCell` 组件和候选取消写入口。
- 仅凭 `case:decision:*`、row `case_id` 或旧 section 判断显示归属。

保留但隔离的同名概念必须属于其他业务域，例如银行自动标签候选、待找发票搜索结果或异常分类 evidence；它们不能进入 Workbench relation membership。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroup*.tsx`、`web/src/features/workbench/*` |
| Backend API | `backend/src/fin_ops_platform/app/routes_workbench.py`、`server.py` 的依赖组装 |
| Core | `workbench_relation_grouping.py`、`workbench_free_matching_engine.py` |
| Service/UoW | `workbench_matching_orchestrator.py`、`workbench_relation_command_service.py`、`workbench_uow.py` |
| Repository | `postgres_repositories/workbench_formal_relation.py`、`workbench_relation.py`、`read_models.py` |
| Worker | `workbench_matching_dirty_scope_worker.py`、`workbench_read_model_refresh.py`、runtime worker registry |
| Tests | `tests/test_workbench_*.py`、`web/src/test/RelationGroupGrid.test.tsx`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |

`WorkbenchRelationGroupingService` 只接收 canonical rows 与 active formal relations，并输出页面 `paired/unpaired` 精确分区；`WorkbenchRelationPreviewGroupingService` 只接收写操作预览所需的 formal relations、selected rows 和显式 ungrouped mode，并输出预览 groups。二者都是无 I/O 的纯投影边界；route/server 只负责组装依赖，不能重新实现 membership、隐藏未分组行或读取 repository/HTTP 状态。

正式关系是关系 ownership 的唯一事实源。projection builder 必须在读取 override/exception 前先从已经加载的 active relations 计算 member row ids，并从 control I/O 集合排除这些成员；不能先把旧 candidate/exception ownership 写入正式成员，再依靠字段覆盖或 Audit 豁免掩盖冲突。未配对 row 仍按 active override > active exception 投影，两个查询继续由既有 repository SQL 边界批量完成。

## 数据恢复与回滚

- 发布前备份 relation facts、history、active generation metadata 和 queue 状态；candidate/decision 表是派生旧状态，不进入业务备份恢复源。
- Release B 的 migration 0104 只做 forward drop 和旧 app-setting 清理，不改 canonical facts；Release A 不携带 0104。
- 发布后运行 `scripts/rehydrate-workbench-read-models.py`，等待 matching/workbench/workbench_relation scopes fresh，再运行页面 Audit。
- 回滚应用版本不得重新创建旧 candidate/decision 表；若必须回退展示代码，只能继续读取 active formal relations 和 paired/unpaired generation。
- 修复验收必须证明 520 关系进入 paired、13 张合计 1709.49 的发票各自 unpaired、canonical count 未减少、active relation/history 未损坏。
