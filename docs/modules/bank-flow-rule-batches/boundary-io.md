# Bank Transaction Paired Policy / 流水规则批量处理模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：close，页面读取已迁移为 PostgreSQL canonical direct query。
- 页面 `/bank-flow-rule-batches` 只调用 `/api/bank-flow-rule-batches/*`。
- route 只做鉴权、参数解析和 HTTP 映射；`BankFlowRuleBatchApplicationService` 组合业务 payload；`BankFlowRuleBatchCanonicalQueryRepository` 持有 SQL。
- 页面列表、summary、分页、详情和写后回读不读取 `read_model.bank_flow_rule_batch_rows`，不读取 Workbench page projection，也不从 no-OA table/service/read model fallback。
- 页面 read model 已退役；未提交 canonical draft 由独立后台 owner 写入 `app.bank_flow_rule_batches/events`，不登记 read-model scope/readiness/manifest。

## 职责边界

### 负责

- 流水规则批量处理页面、筛选、分页、详情和 Bank Transaction Paired Policy 抽屉。
- 维护 `app_settings.bank_flow_rule_batch_tag_rules.requirements_by_tag_code`。
- 只展示 active tag 且 `requires_oa=false`、`requires_invoice=false` 的未提交批次。
- 读取已提交/已撤回批次及 `app.bank_flow_rule_batch_events` 历史。
- 通过 relation command 创建、撤回或 reset `relation_mode=bank_flow_rule_batch` 的正式关系。
- 提交时冻结标签、requirement metadata、资格版本和行级分类 snapshot。

### 不负责

- 不新增、编辑或删除银行标签、分类和银行流水事实。
- 不直接写 `app.workbench_pair_relations`。
- 不读取 Workbench 页面 read model 或 relation projection 作为 ownership 事实。
- 不把旧 `selected_tag_codes`、no-OA batch/table/service/read model 作为兼容输入。
- 不在页面请求热路径访问 OA/Mongo/MySQL、对象存储、Redis、RabbitMQ、worker 或 queue。

## 直接与上下游输入 I/O

| 输入 | 事实源 | 合同 |
| --- | --- | --- |
| 页面查询 | `GET /api/bank-flow-rule-batches` | `month`、`type`、`status`、`bucket`、`account_key`、`page`、`page_size`；非法值 fail fast。后端服务端过滤、固定排序和分页，`page_size` 上限 200。 |
| 批次事实 | `app.bank_flow_rule_batches` | 读取非 superseded 批次、成员、金额、版本和冻结 `normalized_payload`；submitted/withdrawn 历史不被当前标签改名或归档改写。 |
| 批次事件 | `app.bank_flow_rule_batch_events` | 详情按 batch id 一次集合查询，保持 submitted/withdrawn/audit history。 |
| 银行流水 | `app.bank_transactions` | 详情按 batch member ids 一次集合查询；未提交资格校验只接受 non-deleted 当前行。 |
| 当前分类 | `app.bank_transaction_category_confirmations`、`app.bank_transaction_categories` | confirmation 优先于 manual category；只影响未提交资格与未提交详情标签。 |
| 标签与 paired policy | `app.app_settings` | active tags 与 `requirements_by_tag_code` 同一次 canonical snapshot 读取；缺规则默认需要 OA 和发票。 |
| 正式关系 | `app.workbench_pair_relations` | 只接受 `status='active'`。active relation 决定占用和 submitted 可撤回；禁止使用 `workbench_relation` projection。 |
| 规则写入 | `GET/PUT /api/bank-flow-rule-batches/tag-rules` | PUT 使用 `expected_version` CAS；未知、停用、重复标签 fail fast；语义 no-op 不递增版本。 |
| 批量提交 | `submit-selection` / `submit` | 非空、去重、同月/账户/标签、资格与 active relation 占用重查；relation command、幂等/CAS、审计和 batch delta writer 原子提交。 |
| 撤回/reset | `withdraw` / `reset-submitted` | 保持一次 relation command/bulk cancel 与一次 changed-batch delta 保存；不直接改表，不同步 rebuild。 |
| 权限/session | session / permissions | 读、规则写、提交、撤回和 reset 分别 fail closed。 |

## 输出 I/O

| 输出 | 合同 |
| --- | --- |
| 列表 | 只返回 `summary`、`batches`、`pagination`。不返回 `read_model_status`、`read_model_version`、stale reason、source version、refresh enqueue 或 operation-barrier target。 |
| Summary | 对完整 summary filter 范围做 SQL 聚合，不能从当前页推算；包含各状态 batch count、row count、金额和冻结历史标签。 |
| 详情 | 返回 batch、银行 rows、tag/direction counts、行级分类与 events。linked 提示可携带机器用 `relation_case_ids`，页面只展示业务提示和 OA/发票数量。 |
| 规则保存 | 返回规则版本、资格变化和信息性的 `affected_months` / `affected_scope_keys`；不返回页面 refresh target。 |
| 写命令 receipt | 保留 batch、relation command 结果、affected months、幂等/CAS/冲突合同；删除 read-model/freshness/operation-barrier envelope。 |
| 写后页面状态 | submit-selection、submit、withdraw、reset 和规则保存成功后，各执行一次当前列表 GET；不先本地伪造最终批次，不 polling。 |
| 关联台 | relation metadata 保持 `source=bank_flow_rule_batch`、`relation_mode=bank_flow_rule_batch`、`source_batch_id`、`flow_rule_tag_code/version`、冻结 `requires_oa/requires_invoice`、`source_row_count` 和 `collapsed_bank_rows`。银行行数 `>3` 使用 bank-flow summary。 |

## 一致性与查询预算

- 一次列表请求中的 tag policy、total、page rows 和 summary aggregates 位于同一显式 `REPEATABLE READ / READ ONLY` transaction。
- 列表固定 2 次 SELECT：settings，以及一次组合 total/page rows/summary 的集合查询；批次数、分页深度和每批行数不增加查询次数。
- 详情固定 4 次 SELECT：settings、batch、批量 bank rows/active relation aggregates、events。
- 查询不得先加载全量 rows 再在 Python 或浏览器过滤分页；不得逐 batch、逐 row 或逐 relation N+1。
- 未提交 batch 必须同时满足：标签当前双 false、所有成员仍存在且分类一致、成员未与任一 active relation overlap。
- submitted 的可撤回性只由同一 canonical batch 的 active relation 决定。
- 内部转账维持一收一支、不同账户、48 小时窗口；金额只计单边。
- 页面查询不新增 cache、materialized view、queue、fallback 或双读。canonical draft owner 是写侧领域任务，不参与 GET；只有 EXPLAIN 证明确有需要时才统一新增索引 migration。

## 持久化和写边界

Canonical facts：

- `app.bank_flow_rule_batches`
- `app.bank_flow_rule_batch_events`
- `app.bank_transactions`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_confirmations`
- `app.workbench_pair_relations`
- `app.app_settings` 中的 `bank_flow_rule_batch_tag_rules`

在线 mutation 必须继续使用：

- `WorkbenchRelationCommandService`
- `save_bank_flow_rule_batch_mutation(...)`
- `save_bank_flow_rule_batch_items(...)`
- 显式 `changed_batch_ids`

提交/撤回/reset 不得改回 month-scope replace、全量 runtime refresh、Workbench snapshot 写入、no-OA persistence 或 read-model fan-out。已提交/历史的冻结 payload 与事件是审计事实；当前规则变化不追溯修改。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend page | `web/src/pages/BankFlowRuleBatchPage.tsx` |
| Frontend feature | `web/src/features/bankFlowRuleBatches/api.ts`、`types.ts`、`policy.ts`、`viewModel.ts`、`components.tsx` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py` |
| Backend service | `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py` |
| Canonical query repository | `backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py` |
| Canonical draft owner | `backend/src/fin_ops_platform/services/bank_flow_rule_batch_canonical_draft_owner.py`、`bank_flow_rule_batch_canonical_draft_producer.py` |
| PostgreSQL assembly | `backend/src/fin_ops_platform/services/postgres_state_store.py`、`backend/src/fin_ops_platform/app/server.py` 的最小依赖接线 |
| Mutation persistence | `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` 的既有 bank-flow delta writer |
| Tests | `tests/test_bank_flow_rule_batch*.py`、`web/src/test/BankFlowRuleBatch*.test.*`、相关 relation/no-OA regressions |

## 依赖方向

- 允许：页面 -> 专属 API -> route -> application service -> canonical query repository。
- 允许：application service -> relation command / mutation persistence / settings audit owner。
- 禁止：页面或 route -> SQL。
- 禁止：query repository -> worker、queue、cache、外部系统或 Workbench projection。
- 禁止：bank-flow -> no-OA service/read model/table fallback。
- 禁止：service 直接读 HTTP cookie/header 或 repository SQL 外溢到 service。

## Canonical draft 后台合同

- 事件：`bank_flow_rule_batch.canonical_draft.refresh`；scope type 为 `bank_flow_rule_batch_draft`，不是 read-model scope。
- 四类触发：银行事实变化、有效标签规则变化、设置重置、显式 repair/replay。标签规则变化必须使用 canonical repository 算出的精确月份，不得 fallback `all`。
- handler 对同一 scope 重放必须幂等；只 replace/upsert `app.bank_flow_rule_batches` 与 `app.bank_flow_rule_batch_events`，不得写 `read_model.bank_flow_rule_batch_rows`、readiness 或 dirty scope。
- 页面 GET 只读 canonical repository，绝不触发该事件。
- 旧 no-OA read model/worker 仍属于独立 legacy 域，不随本模块退役。

## 测试与验证

- 业务核心：paired policy、冻结历史、内部转账金额、占用、CAS/幂等。
- Service/repository：同 snapshot、固定查询数、canonical-only SQL、active relation、delta writer。
- API：权限、非法参数、空集、筛选、分页、summary、详情和旧字段缺失。
- Read-model cleanup：页面不读 projection、不 enqueue、不 polling。
- Frontend：loading/empty/error、交互、一次写后 GET。
- E2E：提交 -> canonical relation/batch -> 当前页 GET -> 关联台。
- Regression：no-OA legacy、bank-details、Workbench、成本、外部往来款、权限/审计。

详见 `tests.md`。

## Canonical facts ownership

- Owned facts：`app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`app_settings.bank_flow_rule_batch_tag_rules`。
- Shared facts：银行流水/标签/分类归 `bank-details`；正式 relation 归
  `workbench-relations`；关联台 canonical query 归 `reconciliation-workbench`。
- Allowed writes：`BankFlowRuleBatchApplicationService`、relation command、明确 UoW/delta writer。
- Allowed reads：`BankFlowRuleBatchCanonicalQueryRepository`、规则 read service。
- Forbidden：shared broad snapshot、read-model projection、no-OA fallback、调用方直接改 batch/relation 状态。
