# Nightly CI 与测试闭环

Nightly CI 是 solo 开发流程里的自动化验证门禁。它不替代本地目标测试，也不证明生产完全无风险；它负责每天自动暴露全量后端、前端和构建层面的回归。

## 目标

- 每天运行干净 app 状态检查、后端全量 unittest、前端 Vitest 和前端 build。
- 发现新功能破坏旧功能时尽早失败。
- 给 `docs/modules/<module>/tests.md` 提供稳定的 nightly 覆盖入口。
- 防止依赖本地记忆手动运行验证。

## 触发方式

当前仓库使用 GitHub Actions 工作流：

- `workflow_dispatch`：手动触发。
- `schedule`：每天夜间自动运行。
- `push` 到 `main`：主干更新后运行一次基础验证。

如果远端仓库未启用 GitHub Actions，保留 `.github/workflows/nightly-ci.yml` 作为目标配置，并在 `docs/dev/testing-closure-state.md` 标记 CI 平台状态。

## 运行命令

Nightly workflow 调用统一入口：

```bash
bash scripts/verify.sh all
```

该命令包括：

```bash
FIN_OPS_DATA_DIR="$(mktemp -d)" PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test -- --run
cd web && npm run build
```

`scripts/verify.sh backend` 和 `scripts/verify.sh all` 默认使用临时 `FIN_OPS_DATA_DIR` 做 clean app check，不读取开发机 `.runtime/fin_ops_platform/app_mongo_config.json` 或其他本地残留状态。这个检查证明当前代码可以从干净状态启动，但不证明开发机或生产当前 runtime 数据可用。

需要显式检查当前配置的 runtime 状态时使用：

```bash
bash scripts/verify.sh runtime-check
```

`runtime-check` 会读取当前环境变量和 `.runtime/fin_ops_platform/*_config.json`。如果本地仍保留旧 app Mongo 配置，它可能暴露历史 pickle、迁移残留或 PostgreSQL runtime 配置问题；这类问题应按 runtime 数据问题处理，不应阻塞 nightly clean-state 回归入口。

文档结构验证可单独运行：

```bash
bash scripts/verify.sh docs
```

## 失败处理规则

- 不允许通过 skip、删除测试、放松断言或隐藏错误来让 nightly 变绿。
- 失败必须归类：
  - 真实 bug：补 regression test 并修复。
  - 测试不稳定：修测试隔离、时钟、mock 或异步等待。
  - 外部环境缺失：记录为 `documented-risk`，并说明需要的 secret、服务或 staging 条件。
  - 契约变化：先更新对应模块 `tests.md` 和长期事实源，再更新测试。
- 修复后至少运行失败命令和相关模块验证命令。

## 与模块测试矩阵的关系

每个 `docs/modules/<module>/tests.md` 必须有 `Nightly CI 覆盖` 小节，说明：

- nightly 是否覆盖该模块。
- 覆盖来自后端 unittest、前端 Vitest、build 还是文档检查。
- 哪些风险仍需本地目标测试、staging、生产 dry-run 或人工验证。

## 发布前验证

Nightly CI 不替代发布前验证。涉及生产数据、read model、worker、OA 外部系统、Redis/RabbitMQ/PostgreSQL runtime 或部署资产时，发布前仍需按模块文档和运维文档执行：

- 目标模块验证命令。
- read model / worker dry-run。
- staging 或生产只读 smoke。
- `./scripts/deploy-oa.sh` 相关发布流程。

## 仍需人工或 staging 覆盖的风险

- 真实 OA 登录、OA 草稿、OA Mongo 数据异常。
- 生产 PostgreSQL 历史脏数据、半迁移状态、重复记录或缺字段。
- Redis/RabbitMQ 真连接和网络抖动。
- 大数据量 SQL 性能退化。
- 浏览器视觉遮挡、移动端布局和真实下载文件检查。
