# 税金抵扣 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 税金抵扣认证状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 和认证导入事实共同决定，页面不私有定义认证状态。
- `tax_offset` read model 只物化月份 scope `YYYY-MM`；`all` refresh 只用于 fan-out 月份 shard，不写普通 tax offset payload。
- 税金抵扣计划保存必须校验 `read_model_scope_key`、`source_versions` 和 `idempotency_key`；source mismatch 返回 conflict，不能基于旧 read model 保存。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖税额试算、已认证导入、权限、计划保存、SQL read model、Redis cache、worker fan-out、lifecycle fan-out、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

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

## 2026-06-11 - 税金抵扣测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `tax-offset` 模块轮次，确认新功能改动不会绕过发票认证、税额试算、认证导入、read model freshness、计划保存或页面交互回归保护。
- 影响范围：`docs/modules/tax-offset/README.md`、`docs/modules/tax-offset/tests.md`、`docs/modules/tax-offset/state-machine.md`、`docs/modules/tax-offset/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖税额试算、真实导入发票、OA 附件发票、已认证导入解析/确认/去重、权限、计划保存幂等和 source version conflict、SQL read model、Redis cache、worker all fan-out、lifecycle fan-out、App Status 和前端 loading/import/save/filter/drawer/job polling 交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_tax_offset_service.py`、`tests/test_tax_certified_import_service.py`、`tests/test_tax_offset_read_model_service.py`、`tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`tests/test_tax_offset_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_postgres_state_store.py`、`tests/test_postgres_migrations.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service tests.test_tax_certified_import_service tests.test_tax_offset_read_model_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api tests.test_import_job_queue -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_postgres_state_store tests.test_postgres_migrations -v`；`cd web && npm test -- --run src/test/TaxOffsetPage.test.tsx src/test/TaxApi.test.ts src/test/AppStatusIndicator.test.tsx`。
- 未测风险：未连接真实税局认证 XLSX 大样本、真实 OA 附件发票缓存或真实 ETC 生产数据；未跑真实 RabbitMQ/Redis/systemd cost-tax worker drain；未做超大表格性能和真实网络中断恢复 smoke。
- 后续事项：下一轮处理 `pending-invoices`，重点审计规则、人工发票、attach existing、income status 与 invoice lifecycle fan-out。
