# 外部往来款管理模块边界与 I/O

日期：2026-08-18

## 模块化状态

- 状态：closed（direct canonical read 候选，待本次生产验证）
- 当前边界可信度：high
- 目标边界：页面每次访问或手动刷新都在一个 PostgreSQL `REPEATABLE READ READ ONLY` 快照内直接读取 canonical facts；写操作只提交 canonical facts，不触发页面 read model、worker 或跨页 fan-out。
- 设计原则：一个 query owner、一个数据库快照、一个页面 DTO；不增加协调器、版本门、缓存或后台轮询。

## 职责边界

### 负责

- 外部往来款列表、分组、统计、筛选、导出和 relation detail。
- 外部往来款标签准入、补充信息、确认闭环和撤回闭环的业务合同。
- 把 canonical 银行流水、有效分类、统一配对关系、Turnover 自有关系和 extras 组合成页面 DTO。

### 不负责

- 不拥有银行流水和银行分类事实。
- 不直接写 `app.workbench_pair_relations`；确认/撤回必须通过 `WorkbenchRelationCommandService`。
- 不读取 `read_model.turnover_ledger_rows` / `read_model.turnover_ledger_scopes`。
- 不创建或消费 `turnover_ledger.read_model.refresh`，不依赖 Runtime Worker/App Status freshness。
- 不自动刷新其他页面或其他浏览器 tab。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面 GET / 筛选 / 分页 / 导出 | `TurnoverLedgerPage.tsx`、`features/turnoverLedger/api.ts` | 列表按服务端页读取，页面固定发送 `page_size=50` 并消费 `pagination.page/page_size/total`；切 family 回到第 1 页，翻页只替换当前页，超过最后一页时回退到服务端有效末页。route 只校验 HTTP/权限并委托 `TurnoverLedgerQueryService`；不得回退 local builder、旧 read model 或 queue |
| Canonical 页面快照 | `TurnoverLedgerQueryService` | 通过 `turnover_ledger_canonical_snapshot(...)` 开启单个只读 repeatable-read transaction；同次请求中的流水、分类、设置、关系和 extras 必须来自该快照 |
| 银行流水 | `app.bank_transactions` / import fact repository | 只读取有效事实；ID 同时支持 storage UUID 与公开 legacy id 的既有规范 |
| 有效分类和标签准入 | `app.bank_transaction_categories`、`app.bank_transaction_category_confirmations`、`app.app_settings` | 复用 Bank Details canonical classifier 的 set-based SQL 与 `AppSettingsService` 的无 I/O 选择映射；同一快照只返回当前选中 tag codes 的流水，query service 不复制匹配规则 |
| 统一配对关系 | `app.workbench_pair_relations` | 仅按本页实际银行 row ids 做 bounded overlap 查询；active relation 是关联台与外部往来款共同事实源 |
| Turnover 自有关系和 extras | `app.turnover_relations`、`app.turnover_ledger_extras` | 保留通用 suggested/confirmed relation 与页面补充字段的现有业务语义 |
| 关系详情抽屉 | `GET /api/turnover-ledger/relations/{id}` | 同一个 canonical snapshot 返回 relation、页面 row、JSON-safe bank rows、audit 和 extra；抽屉不得再并行请求独立 extra GET。动态 suggested relation 即使尚未持久化也必须由当前 canonical bank rows 重建后解析，不能因为列表先生成、详情后读取而 404 |
| 页面 Audit | admin-only page audit API | 与页面一样直接审计 canonical facts；检查 relation member shape、银行成员存在性、active case 唯一性和手工 Turnover relation 成员存在性，不读取投影/dirty/outbox |
| 闭环流水选择校验 | 页面 grouped `flow_rows[*].selection_version` + 当前 `bank_row_ids` | 正式页面只提交 `turnover_bank_row_selection:<legacy/source id>`；写 UoW 在同一事务内按精确 IDs 一次重读 canonical 银行事实、有效分类、当前规则版本和往来语义，并复用页面 GET 的分类映射与行映射。旧 category-only 版本键直接拒绝，不再拼接 import DTO 与独立 source proof |
| 确认/撤回/标签/extra 写操作 | `TurnoverLedgerWriteFacade` / UoW / adapters | 只提交 canonical relation/category/settings/extra/event/audit；标签 effective category 变化与既有 active 普通 relation requirement/history 使用同一 UoW transaction，外层提交后才发布 changed-case 进程镜像；成功响应不携带页面 freshness target，不产生跨页 fan-out |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 页面 rows/groups/summary/statistics | 前端页面 | 直接由当前 canonical snapshot 计算；当前页只提交与 `{family,page}` 一致的最新请求响应，旧请求即使晚返回也不得覆盖新页。页面 grouped DTO 保留 `summary_row` 与 `flow_rows`，不传输未被页面消费的 `allocation_lots` / `lot_rows`；API 不返回 `read_model_status`、`source_versions`、`refresh_enqueued` 或 refresh scope |
| 流水日期与借款天数 | 前端详情抽屉 | 日期统一按 `Asia/Shanghai` 展示为 `YYYY-MM-DD HH:mm:ss`，不显示 ISO 时区后缀。本金流水输出对应 FIFO lot 的 `loan_days`：未结清按业务今天计算，已结清按该本金 lot 的结清日计算；结算流水不重复显示借款天数 |
| `flow_rows[*].selection_version` | 正式闭环提交 | 由银行事实 `updated_at`、有效分类版本/规则版本和往来 role/action/family 共同生成；缺失任何必要语义时不输出，前端禁止提交。它是当前选择快照的 CAS token，不是新的 read model generation |
| 导出 grouped payload | XLSX export owner | 复用同一 canonical query，但明确包含 normalized `allocation_lots` / `lot_rows`，保证导出财务字段不因页面瘦身而丢失。 |
| 统一配对与结算状态 | 外部往来款页面 | 每个 active canonical case 必须独立校验完整且唯一的 bank members、同一业务语义、现金差额和 `principal-settlement` 余额。非零 active case 输出 `cash_pair_linked=true` / `paired_unsettled=true` 及待还/待收余额；只有现金差额和业务余额都为零才输出 `cash_closure_linked=true`。relation mode/source 不得替代计算证明 |
| 写操作结果 | 当前页面 | 按钮立即进入提交中/disabled；成功后按当前 family/current page 只发一次正常 GET，不回退第一页或本地拼接数组。GET 失败提示“写入已成功、页面重载失败”，不得把成功写入改写为失败 |
| 关联台可见性 | 关联台 | 关联台在自己下一次访问/手动刷新时读取同一 `app.workbench_pair_relations`；外部往来款写路径不触发关联台读取 |
| 导出 | 用户下载 | 复用同一 query owner、权限和筛选；不得另建投影读链 |

## 持久化与运行时

- 页面事实源：
  - `app.bank_transactions`
  - `app.bank_transaction_categories`
  - `app.app_settings`
  - `app.workbench_pair_relations`
  - `app.turnover_relations`
  - `app.turnover_ledger_extras`
- Query owner：`TurnoverLedgerQueryService`
- Snapshot repository boundary：`postgres_repositories/turnover_ledger_snapshot.py`；页面 GET 复用 `PostgresBankDetailsCanonicalQueryRepository.effective_category_rows(...)`，闭环写前按精确 IDs 复用 `turnover_bank_row_selection_rows(...)`；二者共享分类 SQL 与 Turnover mapper，但不读取 Bank Details 页面 DTO。
- Relation enrichment：`turnover_ledger_relation_context.py`
- Worker/read model：不适用。
- Redis/RabbitMQ：不适用。
- 历史 migration 创建的 `read_model.turnover_ledger_rows` / `read_model.turnover_ledger_scopes` 暂不在同一发布中 drop；它们不再有 runtime reader、writer、worker、registry、manifest 或 API surface，不能影响页面结果。后续如删除物理表，必须单独走可回滚 migration。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/TurnoverLedgerPage.tsx`、`web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| HTTP route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` |
| Query/read | `turnover_ledger_query_service.py`、`turnover_ledger_service.py`、`turnover_ledger_relation_context.py`、`bank_details_canonical_query.py` 的共享分类 SQL、`postgres_repositories/turnover_ledger_snapshot.py` |
| Write | `turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py`、`workbench_relation_command_service.py` |
| Other business services | `turnover_relation_service.py`、`turnover_ledger_extra_service.py`、`turnover_ledger_export_service.py` |
| Tests | `tests/test_turnover_ledger_*.py`、`web/src/test/TurnoverLedger*.test.*` |

## 依赖方向

- 允许：route → query service → canonical state/repository ports → page service。
- 允许：route → write facade/UoW → owned writer ports / Workbench relation command。
- 必须：批量银行标签写复用 `BankCategoryRelationClosureService`，不得绕过为仅写 category 的旧 writer 路径。
- 禁止：query service → read model gateway/queue/worker/readiness。
- 禁止：write facade → page GET、跨页 refresh producer 或 read model SQL。
- 禁止：前端把 App Status、visibility/focus 或旧 freshness metadata 当作页面数据源。

## 旧代码删除状态

以下旧生产链路已删除：

- `turnover_ledger_read_model_repository.py`
- `turnover_ledger_sql_projection.py`
- `turnover_ledger_read_model_refresh.py`
- `turnover_ledger_read_model_refresh_producer.py`
- `turnover_ledger_source_versions.py`
- 页面 GET 的全量银行流水加载、全量分类 snapshot 和 Python 自动规则重算；当前请求只接收 SQL 已判定为选中往来标签的 canonical rows
- composite PostgreSQL repository 中 Turnover projection 的 list/freshness/save/delta/generation/CAS SQL 和 helper
- worker handler/registry/env、read-model manifest/scope policy、App Status registry、RabbitMQ dispatcher event
- 前端 stale/refreshing polling 和 API freshness DTO
- 写 API 的 `turnover_ledger_invalidated` 兼容字段
- 闭环写前通过 `Application._turnover_bank_transaction_rows_by_ids(...)` 读取旧 ImportService 全量 DTO，再与 `turnover_bank_row_selection_proofs(...)` 独立拼接版本证据的双读链；生产闭环只保留同一事务、同一 canonical query/mapping 的精确选择读取
- extra 抽屉并行读取 `relation detail + relation extra`、extra PUT 后通过 `row_provider` 再读页面行、request boundary 通过 `current_extra_reader` 在事务外做版本判断的旧链；当前只保留一次 relation detail GET，extra PUT 返回已保存 extra，版本判断在写 UoW 同一事务内读取并锁定 extra 行

历史 migration 和历史实施记录不构成 runtime 链路，也不能作为当前架构依据。

## 测试与验证

- Business core：`tests/test_turnover_ledger_service.py`
- Service/read boundary：`tests/test_turnover_ledger_query_service.py`
- PostgreSQL canonical snapshot：`tests/test_turnover_ledger_postgres_integration.py`
- 精确选择 SQL/GET→POST CAS 一致性：`tests/test_bank_details_canonical_query.py`、`tests/test_turnover_ledger_postgres_integration.py`
- API/write regression：`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py`
- Audit/architecture：`tests/test_audit_page_canonical_data_tool.py`、`tests/test_platform_runtime_boundary_guards.py`
- Frontend：`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`；Playwright：`web/e2e/turnover-ledger-flow.spec.ts`，以 121 组数据证明第 2/3 页和第 121 组可达。
- 生产：使用 test-owned 可恢复 fixture 验证 confirm → 两页面手动刷新一致 → withdraw 恢复；同时验证 Audit、零 Turnover refresh outbox/dirty scope、接口耗时和 worker registry 无 Turnover 实例。

## 验收条件

- 每次页面访问/手动刷新返回当前 snapshot 的分页数据和配对关系；`total > 50/100` 时所有页均可达，不得只固定读取第一页。
- 外部往来款和关联台对同一 active case、成员和撤回状态一致。
- 不同 active case 的余额不跨 case 抵消；无 active relation 的零余额流水不显示闭环；`closed_amount` 固定为兼容值 `0.00`。
- 旧 Turnover read model 中即使有残留错误行，也不能改变页面响应。
- 任一写操作后没有 `turnover_ledger.read_model.refresh`、Turnover dirty scope 或无关页面 I/O。
- 页面 GET 失败可由普通刷新重试，不依赖人工清队列或版本修复。
