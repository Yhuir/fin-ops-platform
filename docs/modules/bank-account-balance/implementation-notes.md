# Bank Account Balance 实施记录

## 2026-09-08 - 余额证据状态与完整合计

- 目标：账户余额与银行列表/导出共用完整组判定，去掉银行流水号或随机 ID 对真实末余额的决定作用；既有账户 identity、metadata 一致性、币种归一和日期范围笔数保持原合同。
- 决策：保留 `BANK_ACCOUNT_CANONICAL_SOURCE_CTES` 的账户事实，以共享 `BANK_TRANSACTION_ORDERING_CTES` 仅判定最新/最后非空目标组的终点；完整候选日期先检查缺时间歧义，闭合组需要锚点时才访问历史。最新组可靠返回 confirmed；全部缺余额才检查最近有余额历史组，可靠时 last_known；冲突不继续向前回溯。列表复用 classifier 已有 account_key，币种归一共享，不额外计算 hash。
- 金额/来源：confirmed/last_known 返回原始终点余额；无法证明末笔身份时 ID 为 null。unresolved/missing 金额和来源为空，不造零。多币种账户先判 unresolved，展示 currency=null；单币种全历史无余额再判 missing，最新日期缺时间歧义不会把它改成余额冲突。
- 汇总：按底层币种集合判定完整性；每币种全部应计账户 confirmed 才输出完整总额，CNY 不完整为 `total_balance=null`。last_known 计入可显示余额数量但不计入完整合计，真实零保持零值字符串。
- 边界：没有新 schema、写入、hash/账户 key、cache、worker 或 migration。共享分类消费者不引入排序字段/查询；本轮不做多币种子账户 UI 或历史连续性重建。
- 验证：真实 PostgreSQL 29 项已有一轮通过；前端最后竞态修复后的银行专项、build 和相关浏览器测试通过，轮次/数量见银行明细测试矩阵。后续 SQL 重跑、执行计划与剩余风险统一记录在[修复计划](../../dev/bank-same-time-ordering-repair-plan.md)。本地验证中，未发布，固定查询数不是性能验收结论。
- 清理：全仓调用扫描后删除旧 `BankDetailsService.list_accounts/_latest_balance_transaction`、core `list_bank_transaction_accounts`、state-store wrapper 和独占测试 fake；有效余额/笔数/无余额/metadata 断言已迁入 29 项真实 PostgreSQL 测试。账户 metadata 的 label_consistent 选择继续保留。

## 2026-07-27 - Bank Details accounts direct canonical read

- 决策：`/api/bank-details/accounts` 改由 page-specific canonical query repository 直接读取 `app.bank_transactions` 与 canonical account mappings，不再读取 `read_model.bank_account_balances`。
- 复用：把旧 projection 的账户聚合 SQL提取为 `BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL`，避免 direct query 复制余额算法。
- 性能边界：账户级 SQL 聚合 + 范围 count，固定查询次数；不在 Python/浏览器累计，不新增 cache、worker、materialized view 或依赖。
- 共享清理：旧 repository/refresh/worker/manifest/backfill/deploy/App Status 资源由主控在所有消费者迁移后统一删除，本分支保持不动。

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 Search local support 进入 `production-evidence-deferred` 后，选择下一个非 Go read model pilot。
- 决策：选择 `bank_account_balance`，下一条边界为 `read-models:bank-account-balance-repository-port-extraction`。
- 理由：它是剩余已知 read model 候选，服务 Bank Details accounts，参与银行导入 write-operation SLO，并且必须与 `bank_detail` rows 保持余额金额/readiness 独立。
- 首切范围：新增窄 `BankAccountBalanceReadModelRepositoryPort`，只暴露 manifest 登记的 `bank_account_balance_scope_summary(...)`、`list_bank_account_balances(...)` 和 `save_bank_account_balances(...)`，并让 projection save 与 accounts SQL read path 使用该 port。
- 非目标：不改余额计算、account identity、API shape、worker event、queue schema、权限、审计、frontend behavior、Go/Fiber 或 Go Worker。
- 状态：`bank_account_balance` 是 `implementation-gap-open`；本记录不是 module closure。

## 2026-06-24 - repository port extraction

- 目标：建立账户余额窄 repository port，避免 projection save 和 accounts SQL read path 继续依赖 broad 或 Bank Detail read port surface。
- 改动：新增 `BankAccountBalanceReadModelRepositoryPort`；`PostgresStateStore.bank_account_balance_sql_read_repository` 返回该 port；`BankAccountBalanceProjectionBuilder` 保存 projection rows 走该 port；`BankDetailsApplicationService.accounts_payload(...)` 优先通过显式 account-balance port 读取；manifest repository owner 更新为 `BankAccountBalanceReadModelRepositoryPort`。
- 保留兼容：`BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` 暂时保留为未注入显式 account-balance port 时的 compatibility fallback，后续 audit 决定删除或加固。
- 保持不变：余额计算、account identity、latest balance 选择、currency normalization、API shape、worker event、queue schema、权限、审计和前端行为。
- 下一步：执行 `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`，审计 app-owned refresh/derived lifecycle helper、all-only scope contract、operation barrier 和 remaining compat fallback。

## 2026-06-24 - refresh/freshness/operation-barrier audit

- 目标：在实现前审计账户余额 refresh enqueue、derived lifecycle、runtime import-state fan-out、scope policy、operation barrier 和 compat fallback。
- 结论：`Application._enqueue_bank_account_balance_read_model_refresh(...)` 仍是最高优先级本地 implementation gap；它虽然走 `ReadModelRefreshGateway`，但模块 IO 边界仍在 app 层。
- 相关缺口：`Application._derived_lifecycle_bank_account_balance_executor(...)` 仍直接组装 invalidated scope 和 enqueued job；runtime import-state fan-out 仍使用 generic `_enqueue_scopes("bank_account_balance", ["all"])`；scope policy 接受 month/all 但 worker/storage 只接受 `all`；dedicated operation barrier regression 和 Bank Detail fallback quarantine 仍待补齐。
- 决策：下一条边界为 `read-models:bank-account-balance-refresh-producer-extraction`。先抽 `BankAccountBalanceReadModelRefreshProducer`，保持 `bank_account_balance:all` all-only 语义，再处理 derived lifecycle、scope contract、operation barrier 和 fallback。

## 2026-06-24 - refresh producer extraction

- 目标：将 `bank_account_balance` 非事务 refresh enqueue 从 app/runtime generic helper 收敛到显式 producer。
- 改动：新增 `BankAccountBalanceReadModelRefreshProducer`；Application import-state、Bank Details service injection、runtime import-state fan-out、runtime derived lifecycle fan-out 和 backfill enqueue 均改用 producer。
- 边界决策：producer 永远 normalize 为 `["all"]`，保持当前 worker/storage all-only contract，不引入 month/account projection scope。
- 保持不变：余额计算、account identity、latest balance、API shape、worker event、queue schema、权限、审计和前端行为。
- 下一步：`read-models:bank-account-balance-derived-lifecycle-executor-extraction`，把 Application 中的 derived lifecycle response assembly 移入 dedicated executor。

## 2026-06-24 - derived lifecycle executor extraction

- 目标：把账户余额 derived lifecycle response assembly 移出 Application。
- 改动：新增 `BankAccountBalanceDerivedLifecycleExecutor`；derived lifecycle registry 改为 `self._bank_account_balance_derived_lifecycle_executor().execute`；旧 `_derived_lifecycle_bank_account_balance_executor(...)` 删除。
- 保持不变：`deleted_counts={"bank_account_balance_read_models": 0}`、`invalidated_scopes=["all"]`、enqueue 成功时返回 `bank_account_balance.read_model.refresh`。
- 下一步：`read-models:bank-account-balance-all-only-scope-contract`，收敛 gateway scope policy 与 worker/storage all-only contract 的不一致。

## 2026-06-24 - all-only scope contract

- 目标：让账户余额 gateway scope policy 与 worker/storage all-only contract 一致。
- 改动：`DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY["bank_account_balance"]` 改为 all-only policy；`ReadModelRefreshGateway` 现在在 durable enqueue 前拒绝 `2026-03`、`account:*`、`active:*` 等非 `all` scope。
- 保持不变：producer 仍 normalize 为 `["all"]`；不引入 month/account projection shard；API、worker event、queue schema、余额计算、权限、审计和前端行为不变。
- 下一步：`read-models:bank-account-balance-operation-barrier-regression`，补齐 `bank_account_balance:all` operation barrier 回归。

## 2026-06-24 - operation barrier regression

- 目标：补齐 `bank_account_balance:all` 写后读同步 barrier 回归，避免 accounts 页面在账户余额 read model 仍 pending/refreshing 时被误判 synced。
- 改动：新增 `OperationFreshnessBarrierService` 测试，覆盖 dirty/readiness refreshing、outbox pending 和 unrelated read model outbox 不阻塞账户余额目标。
- 保持不变：未改生产服务代码；API、worker event、queue schema、余额计算、权限、审计和前端行为不变。
- 下一步：`read-models:bank-account-balance-bank-detail-fallback-quarantine`，处理 Bank Detail port 的 account-balance compatibility fallback。

## 2026-06-24 - Bank Detail fallback quarantine

- 目标：移除 Bank Details accounts 通过 Bank Detail read model port 读取 account-balance payload 的过渡 fallback。
- 改动：`BankDetailsApplicationService._accounts_from_sql_read_model(...)` 只使用 `bank_account_balance_read_model_repository`；`BankDetailReadModelRepositoryPort` 删除 `list_bank_account_balances(...)`；新增 static guard 防止 fallback 回归。
- 保持不变：缺少 account-balance SQL repository/table 时仍返回 refreshing 并 enqueue `bank_account_balance:all`；API shape、worker event、queue schema、余额计算、权限、审计和前端行为不变。
- 下一步：`read-models:bank-account-balance-local-implementation-closure-audit`，确认是否只剩 production evidence defer。

## 2026-06-24 - local implementation closure audit

- 目标：复核账户余额 read model 在 repository port、projection save、refresh producer、derived lifecycle executor、all-only scope policy、worker handler、operation barrier 和 legacy fallback removal 后是否仍有本地 implementation gap。
- 结论：未发现剩余本地 implementation gap；local support 转为 `production-evidence-deferred`，但不标记 full module closed。
- 已 accounted：`BankAccountBalanceReadModelRepositoryPort`、`BankAccountBalanceReadModelRefreshProducer`、`BankAccountBalanceDerivedLifecycleExecutor`、`BankAccountBalanceReadModelRefreshService` all-only worker contract、runtime/backfill producer fan-out、`ReadModelRefreshGateway` all-only scope policy、operation barrier regressions 和 Bank Detail fallback guard。
- 剩余：真实 PostgreSQL migration/table/readiness、worker drain、App Status runtime snapshot、high-row performance 和 Browser smoke evidence。
- 下一步：进入 Go hot-path performance baseline/admission reconciliation；不直接开始 Go/Fiber/Go Worker 实现。
