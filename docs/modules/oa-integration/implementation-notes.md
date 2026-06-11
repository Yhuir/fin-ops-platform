# OA 集成 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 集成首轮测试闭环状态为 `documented-risk`：本地测试已覆盖主要 contract、失败分支和跨模块 dirty scope，但真实 OA 登录、OA 草稿页面、OA Mongo 字段变体、同域 iframe/cookie 和生产 worker drain 必须由 staging/生产前 smoke 补证。
- OA Mongo 仍按外部只读源处理；本系统只能建立映射、缓存和投影，不写 OA 原始库。
- 目标 OA 申请人凭据只允许 admin 维护，response/log/audit 不得回显 password；创建 OA 草稿前必须先通过目标申请人登录拿 token。
- 进项 OA 反提和 ETC OA 草稿的本地撤销/删除只处理本系统状态，不删除或撤销真实 OA 草稿/流程。

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

## 2026-06-11 - OA 集成测试闭环首轮

- 目标：完成 `oa-integration` 的影响面、七类测试矩阵、状态机、依赖地图和模块验证，补齐高价值测试缺口。
- 影响范围：OA session、Mongo adapter、OA projection sync worker、OA pending payments、OA manual import、OA applicant credentials、目标 OA 申请人登录、进项 OA 反提、ETC OA 草稿、OA role sync、部署同域路径。
- 关键决策：不把真实 OA/Mongo/staging 风险伪装为本地已闭环；本地只保护 contract、状态机和失败处理，真实外部系统行为进入 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md`、`docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `tests/test_target_oa_applicant_token_provider.py` 中 HTTP error、网络不可达、无效 JSON、缺 token 回归，确保目标 OA 登录失败不会伪装成功且不泄露 password。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_oa_adapter tests.test_worker_oa_sync tests.test_oa_identity_service tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_input_invoice_usage_api tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_oa_projection_sql_runtime tests.test_oa_manual_import_service tests.test_oa_manual_import_api tests.test_oa_role_sync_service tests.test_deploy_oa_script tests.test_deploy_oa_nginx_config -v`
  - `cd web && npm test -- --run src/test/SessionApi.test.ts src/test/SessionGate.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/SettingsOaManualSearchImportTable.test.tsx src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx src/test/EtcOaNavigation.test.ts`
  - `bash scripts/verify.sh docs`
- 未测风险：真实 OA 登录/RSA/openssl、目标申请人账号状态、OA 草稿页面、真实 OA Mongo 历史字段/附件/性能、同域 cookie/iframe/Nginx 下载、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 后续事项：发布前按 `tests.md` 的关键 smoke flows 做 staging/生产前验证；继续主控闭环到 `data-safety-reset`。
