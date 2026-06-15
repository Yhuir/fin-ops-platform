# 银行明细 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 银行明细本轮不新增代码测试；现有测试已经覆盖 P0 的自动标签规则、候选确认、人工补分类、read model freshness、账户余额独立 read model、relation tag 投影、API contract 和前端交互。缺口主要是模块文档未矩阵化，以及真实基础设施/真实历史数据 smoke。
- 账户余额 read model 与银行明细 rows read model 必须保持独立。标签规则保存、重应用、关键字/分类/日期筛选不能用 stale account payload 覆盖已有 fresh balance。
- 银行明细前端 domain event 只负责刷新提示和 refetch；跨页面一致性的事实源仍是后端 dirty scope、outbox、worker 和 read model freshness。
- 银行明细对 no-OA、turnover ledger、pending/search、cost/tax、workbench relation 的 fan-out 在本模块记录上游影响；具体下游页面的 UI/业务流回归由各模块轮次继续补齐。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-15 - 自动标签规则恢复入口与历史外部往来语义补齐

- 目标：阻断工作台大 settings 保存入口污染 `bank_transaction_tags`，并让银行明细自动标签文件恢复可以从 Excel 与 app 历史恢复规则、复用旧 code、补齐历史外部往来语义。
- 影响范围：`AppSettingsService`、银行自动标签 HTTP 入口、Workbench settings 前端 API、`BankTransactionCategoryService`、`BankDetailSqlProjectionBuilder`、bank-details/turnover-ledger 测试矩阵。
- 关键决策：`/api/workbench/settings` 不再允许保存 `bank_transaction_tags`；唯一写入口保留银行明细“自动标签规则”。文件替换优先按 app 历史复用已有 code，支持 `.xlsx` 标题行解析；对生产中已损坏为 label-only 的历史外部往来 custom code、`external_turnover` code，以及已按 app 历史重命名/重配的 editable system code，按现有规则/外部往来语义 helper 恢复 rules/action，避免恢复时归档仍被下游引用的旧 code。旧确认记录缺 action 时，bank detail SQL projection 从当前 tag definition 补齐语义。生产恢复使用 `fin_ops_platform.tools.restore_bank_auto_tag_rules`，默认 dry-run；写入必须同时提供 `--apply --confirm-write`，并通过银行明细 application service 触发保存、审计和 read model 刷新。
- 文档影响：更新 `docs/dev/api-contracts.md`、settings/bank-details/turnover-ledger 模块测试文档。
- 测试覆盖：新增/更新 app settings 写边界、bank auto tag file replacement、xlsx parser、legacy external turnover recovery、bank detail projection enrichment、生产恢复工具 dry-run/write guard、前端 Workbench settings payload 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankDetailSqlProjectionBuilderTests -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool -v`。
- 未测风险：本地未写生产；真实生产仍需备份、应用恢复、刷新 `bank_detail`/`turnover_ledger`/`workbench_relation`/`workbench` read models 后，验证目标三笔流水在关联台 open 区形成 active bank-only 关系组。
- 后续事项：生产写入前必须输出写入 key/table、版本变化、回滚方案、refresh scope 和验收 SQL/API/UI 步骤，并取得明确授权。

## 2026-06-14 - Bank detail stale source guard

- 目标：修复真实关联台 confirm/withdraw 连续写入时，旧 `bank_detail` source_version 事件仍完整 rebuild，导致新版本 bank detail 和下游 pending invoice 写后 SLO 超过 5s。
- 影响范围：`BankDetailReadModelRefreshService`，不改变银行明细 API、分类业务、Redis/RabbitMQ/dirty scope 事实源。
- 关键决策：复用 runtime queue 的 `read_model_refresh_is_current(...)` 判定，在 handler 开始前和 rebuild 后跳过被更新版本覆盖的事件；旧事件只 ack skipped，不 complete dirty scope，不发布旧 readiness。
- 文档影响：同步 runtime-workers 实施记录和测试矩阵。
- 测试覆盖：`BankDetailReadModelRefreshServiceTests` 新增 stale source_version 两条回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests -q`。
- 未测风险：本地测试不证明生产 RabbitMQ consumer 和真实历史数据的 5s SLO；需发布后用 approved confirm/withdraw E2E 验证。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 bank-details 模块轮次，审计银行明细页面/API/service/read model/worker/domain event 和现有测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；未改变产品业务口径或运行时代码。
- 关键决策：本轮判定现有 P0/P1 测试入口足够覆盖自动标签、候选确认、manual assignment、账户余额 read model、bank detail freshness、导出和前端交互；不为覆盖率新增重复测试。真实 Postgres/RabbitMQ/Redis worker drain、历史生产数据和浏览器视觉/性能 smoke 归入 `documented-risk`。
- 文档影响：补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令、业务/UI/read model/worker 状态机。
- 测试覆盖：沿用现有 bank details 后端和前端测试；本轮未新增代码测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_transaction_auto_category_service tests.test_bank_transaction_category_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bankdetail_write_uow_contract -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bankdetail_backfill_cli -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_transaction_identity_service -v`；`cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx`。
- 未测风险：不运行真实生产库 worker drain、真实导入到下游多页面完整 smoke、浏览器视觉/大数据性能验证。
- 后续事项：下一模块继续处理 `input-invoice-usage`。
