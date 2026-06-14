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
