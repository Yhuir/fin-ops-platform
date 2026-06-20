# 数据安全与重置 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- data reset 是跨模块危险操作，不归入单一 Settings 页面测试；每次改动都必须按数据事实、文件/object storage、read model/worker、App Health、权限和旧页面影响面审计。
- `protected_targets` 是可执行契约，不只是文档说明；新增或改变目标必须补 service/API 回归。
- data reset 必须先通过管理员 session 和当前 OA 密码校验；密码不得进入 job payload、result、error、App Health 或前端持久 state。
- 并发 data reset job 必须互斥。同一 owner 有 active job 时，新的 job create 返回 `409 settings_data_reset_job_running` 并返回当前 job，前端用于恢复进度。
- 本地自动化覆盖 reset 规则、API/job contract、UI 交互、App Health attention 和 legacy app Mongo export。真实 PostgreSQL PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain 和大生产库收敛归入 `documented-risk`，由 staging/nightly/smoke 补。

## 历史记录

## 2026-06-20 - reset 后多页面 fresh Browser contract

- 目标：补齐 data reset Browser 主流程只停留在 Settings 成功反馈的缺口，让同一真实 Chromium flow 继续验证受影响页面会重新读取 fresh read model。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、deterministic API mock、`e2e-coverage.md`、`tests.md`、全局 testing/inventory/closure state。
- 关键决策：只加固测试和 mock，不改产品逻辑；mock 在 reset job 完成后记录 completed action，`reset_bank_transactions` 使银行明细交易列表返回 fresh empty，用来表达“旧银行流水不能继续显示为 fresh”。
- 测试覆盖：Browser flow 在 job 202、polling、settings reload 后进入银行明细，断言 `bank_detail` rows `read_model_status=fresh` 且旧流水为空；再进入待找发票，断言 `pending_invoice` rows `fresh` 且业务行可见。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium` 通过 2 tests。
- 未测风险：真实 PostgreSQL PITR、对象存储恢复、Redis/RabbitMQ/systemd worker drain、大库 reset 后全页面最终 fresh 和真实 OA Mongo/附件仍需 staging/production gate。

## 2026-06-11 - 首轮 data-safety-reset 测试闭环

- 目标：审计数据重置、备份/导出、protected targets、state store 清理、read model dirty/worker/App Health、OA 密码校验和前端交互测试闭环。
- 影响范围：`SettingsDataResetService`、`server.py` data reset routes、`BackgroundJobService`、Settings/Workbench UI、App Health/App Status、legacy app Mongo export、read model/worker runtime 状态。
- 关键决策：补并发 job API 回归，防止 active reset 期间重复创建危险后台任务；真实基础设施和备份恢复风险记录为 documented-risk。
- 文档影响：补齐 `README.md`、`tests.md`、`state-machine.md`，并更新全局依赖地图和测试闭环状态。
- 测试覆盖：新增 `test_reset_job_api_rejects_concurrent_job_without_echoing_password`，覆盖 API contract、background job 并发互斥、旧功能回归和敏感字段不泄露。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service.SettingsDataResetServiceTests.test_reset_job_api_rejects_concurrent_job_without_echoing_password -v`
  - 本轮模块验证命令见 `docs/modules/data-safety-reset/tests.md` 和 `docs/dev/testing-closure-state.md`。
- 未测风险：真实 PostgreSQL/PITR/staging restore、对象存储备份恢复、真实 Redis/RabbitMQ/systemd worker drain、真实大库 reset 后多页面最终 fresh、真实 OA Mongo/草稿/附件。
- 后续事项：发布前执行 staging data reset smoke；deploy 模块继续审计 nightly/deploy smoke 与生产入口。
