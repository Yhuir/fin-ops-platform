# 批量账务 Spec-first E2E Coverage

本文件把 `e2e-spec.md` 的批量账务 Browser 合同映射到自动化覆盖。

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `BATCH-E2E-001` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx`、`tests/test_batch_accounting_api.py` | Browser 覆盖页面 ready、未提交/已提交 bucket、银行 rail、OA 表、小样本 fresh payload，以及首屏 `GET /api/batch-accounting` 暂时 503 后错误态不显示普通空态、用户点击刷新恢复银行/OA rows；组件/API 覆盖 `bank_page_size=200` / `oa_page_size=200`、独立分页、page-size 上限、summary total 和 transient load failure refresh。 |
| `BATCH-E2E-002` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx`、`tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py` | Browser 覆盖选择银行流水与两条 OA、差额 0、提交、成功反馈、零 operation barrier、当前页 normal GET、已提交 bucket 和成功后无可见错误残留；后端覆盖 canonical relation、空 targets、idempotency/version、rollback 和 current invoice rows。 |
| `BATCH-E2E-003` | `covered` | `web/src/test/BatchAccountingPage.test.tsx`、`tests/test_batch_accounting_api.py` | 组件/后端覆盖金额不一致差额说明必填、空白说明拒绝、金额一致忽略说明、差额关系提交和 history 保留。Browser 主链路不重复覆盖低价值分支。 |
| `BATCH-E2E-004` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx`、`tests/test_batch_accounting_api.py` | Browser 覆盖已提交 bucket、撤回 dialog、原因输入、withdraw endpoint、零 barrier、normal GET 后已提交计数归零、未提交 bucket 恢复和零可见错误；后端覆盖非 batch relation 拒绝、撤回原因、cancel current relation、history、零 queue I/O 和旧 snapshot restore 删除。 |
| `BATCH-E2E-005` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`web/src/test/BatchAccountingPage.test.tsx` | Browser 覆盖 `read_model_status=stale` 时显示 warning/reason/scope、保留当前可用银行/OA rows、不显示普通空态、选择后 submit 按 canonical write safety 语义保持可用且测试本身零 mutation；后端/API 覆盖 missing/stale 透传、facade/gateway 入队、GET 只读、不执行 legacy repair；组件覆盖 warning/reason/scope 和刷新未入队提示。 |
| `BATCH-E2E-006` | `covered` | `tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_workbench_v2_api.py` | 后端覆盖 submit/withdraw 委托 relation command service，缺 command service fail-fast，无 direct pair write fallback，失败 rollback 不半写；静态 guard 覆盖 legacy repair 入口已删除且不得回归。 |
| `BATCH-E2E-007` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`web/e2e/workbench-relation-fanout.spec.ts`、`web/src/test/domainEvents.test.ts`、`tests/test_platform_runtime_boundary_guards.py`、workbench relation tests | Browser 覆盖 submit/withdraw 后当前页 GET 和轻量事件；relation tests/guards 覆盖零写后 fan-out、另一个可见消费者独立 GET、隐藏页面延迟至 visible。 |
| `BATCH-E2E-008` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx`、后端 auth/API tests | Role matrix 覆盖页面读取、read-export 下选择 OA 后 submit disabled、已提交 bucket 撤回关联 disabled，以及 submit/withdraw durable mutation 零调用；组件/API 覆盖权限/session 错误。批量账务如新增独立按钮权限，需追加更细按钮矩阵。 |
| `BATCH-E2E-009` | `covered` | `web/e2e/batch-accounting-flow.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx` | Browser 覆盖 1180px 窄桌面下银行 rail header、标题、说明、年份输入、分页控件不溢出且无隐藏浏览器错误；组件/CSS contract 覆盖更多布局细节。真实超大年份仍归 staging 风险。 |
| `BATCH-E2E-010` | `external-risk` | `bash scripts/verify.sh infra-smoke` staging gate、runtime worker/read model tests、write-operation SLO audit profiles | 本地 contract 已覆盖 registry、durable queue、dirty scope、worker handler、scope policy 和 App Status；真实 PostgreSQL/RabbitMQ/Redis/systemd workbench-relation/search/cost worker drain、生产历史数据和真实网络恢复必须在 staging/runtime smoke 验证。 |

## Operation latency baseline

本轮已为 `web/e2e/batch-accounting-flow.spec.ts` 接入 Playwright `operation-latency-*.json` 附件。当前记录的操作覆盖：页面打开、首屏加载失败后的刷新重试、stale 诊断下选择 OA、未提交 bucket 选择两条 OA、提交批量账务 relation、零 barrier 的当前页 GET、切换已提交 bucket、打开撤回弹窗、填写撤回原因、确认撤回、撤回后的 normal reload，以及切回未提交 bucket。

## 下一轮补测建议

1. staging 运行真实基础设施 smoke：submit/withdraw 后 workbench relation、search、cost 和下游页面 read model drain 到 fresh。
2. 用真实历史数据评估是否仍存在 legacy case id collision；如存在，必须走 owner 批准的独立迁移/repair runbook，不能重新接回 batch-accounting 页面模块。
3. 补真实大年份、高行数、超长 OA 描述和长备注的浏览器性能/视觉 smoke。
