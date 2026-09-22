# 导入失败任务处理闭环

日期：2026-09-22。状态：代码与测试已实现，按正式发布流程交付；不使用 GSD。

## 范围与边界

现有 App Health 增加有界任务列表和按需详情；管理员命令归属导入模块，健康 GET 和 Audit 保持只读。个人 owner 权限不放宽。复用 PostgreSQL job/version/result_payload、预览生命周期和 append-only 审计，无迁移、备份、新 worker/read model。

确认已知只表示已读；管理员结束处理保存独立 disposition，不伪造成功。失败结束保留 failed 和错误；待复核放弃复用 session/file/batch discard，同事务取消任务、记录 disposition 与审计。不得对执行中任务执行该操作。所有重试/重新预览/确认拒绝明确结束的任务，成功任务后续意图保持原合同。

## 执行与验收

1. 核实任务来源与错误；详情分开历史错误和当前文件/批次证据，未知不推断。
2. 管理员分页列表/详情/结束命令；版本冲突、幂等重放、事务审计。
3. UI 详情、继续导入或结束入口；提交成功后回读，旧响应不能覆盖；网络结果不明先核实。
4. 当前任务状态脱离整页旧缓存；保持轮询频率和库存缓存；移除旧20条样本与重复查询。
5. 核对个人导入、银行/发票/ETC、其他后台任务和操作历史；覆盖七类测试、并发、回滚、分页、缓存和失败路径。
6. lint、前后端测试/build、关键 E2E、docs；commit/push main，正式脚本部署；线上版本、任务链路和性能实测。

实际业务是否继续不能自动猜测；生产任务只按明确证据和授权处理。主数据库不得删除；任务临时测试数据和文件结束后精确清理。

## 文档影响

更新导入、App Health、权限审计与操作历史的 I/O、状态及测试说明；不修改财务事实口径。最终记录验证命令、性能、发布版本及未决业务处理。

## 已实现的 I/O 和清理

- 管理员接口：`GET /api/imports/jobs`、`GET /api/imports/jobs/{uuid}`、`POST /api/imports/jobs/{uuid}/dispose`。命令输入为任务版本、动作、原因、可选说明；输出为持久化处理记录和版本，不更改原失败结果。
- 导入 service 负责状态和审计，repository 负责 SQL/事务；App Health 仅承载入口与读数。沿用既有文件/ETC 生命周期，不复制导入实现。
- 删除 `dashboard_import_jobs`、dashboard 内旧 import_jobs DTO 和样本组件；统一任务查询，不保留并行旧路径。
- 版本冲突、并发重试与结束、重复提交、响应丢失都显式处理。读取失败保留错误并阻止未知结果再次提交，不自动伪造完成。
- 保留所有财务事实、正式导入记录和普通 owner 权限；无新增表、迁移、worker、依赖或任务备份。

## 测试责任和验证入口

七类测试本次均适用，没有以不适用跳过类别：

| 类别 | 实际覆盖 |
| --- | --- |
| 业务核心 | 失败/待复核可处理状态、已结束不可恢复、原因与版本校验、幂等和并发 |
| Service | PostgreSQL 任务、文件、批次、ETC、审计原子提交与审计故障回滚 |
| API 合同 | admin/owner 隔离、分页、详情、处理结果、参数错误和操作历史证据 |
| 后台任务/缓存 | 已处理任务不再入待处理计数，缓存库存不缓存当前 runtime 状态，既有队列重试回归 |
| 前端交互 | 加载与错误、按需详情、版本提交、重复点击、丢失响应回读、旧响应不得覆盖 |
| 端到端 | 实际 PostgreSQL API 闭环；浏览器任务详情→处理→刷新；银行/发票/ETC 原导入流程 |
| 既有回归 | 后端全量、前端全量、关键导入 E2E、权限清单、现金隔离库及旧页面合同 |

本地验证结果：后端全量 4,500 个测试通过（使用独占测试库，无跳过）；前端全量 109 个测试文件、1,469 个测试通过；导入相关浏览器 23 个用例通过。最后一次前端细节修改后，相关组件 11 个用例和处理闭环浏览器用例重新通过。生产构建、lint、docs 与 diff 检查通过。

验证命令：

```sh
bash scripts/verify.sh lint
# 两个 DSN 仅指向本任务临时 PostgreSQL 的 fin_ops_cash_test_disposition。
FIN_OPS_TEST_DATABASE_URL=<isolated-test-dsn> FIN_OPS_CASH_TEST_DATABASE_URL=<isolated-test-dsn> bash scripts/verify.sh backend
npm test --prefix web -- --run
npm run build --prefix web
cd web && npx playwright test e2e/import-job-disposition.spec.ts e2e/imports-bank-transactions-flow.spec.ts e2e/imports-invoices-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts
bash scripts/verify.sh docs
git diff --check
```

生产交付使用 `scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh`，沿用既有 Pre/T0/T30 验证。发布后核对实际 release、4 个 worker、管理员任务查询/详情、未登录拒绝访问、只读浏览器 smoke 和接口耗时。完整提交号、发布证据和公网性能样本在本次交付报告中提供，不把合成测试描述为真实业务写入验证。

## 再审阅结论

模块边界清晰，无通用调度框架或额外严格门禁；列表/文件分页，详情按需请求；旧样本链路已移除。自动恢复只处理可验证的技术状态，不能自动判断“是否仍需导入”。真实失败任务只有在原文件状态和业务意图明确后才能结束处理，不能为消除提醒冒充成功。性能通过实测报告，不承诺所有网络条件下的绝对耗时，也不承诺未来所有故障永不发生。临时测试集群和本任务日志在验证结束后精确清理，主数据库和平台备份不属于清理对象。
