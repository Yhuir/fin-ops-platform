# 开发与验证

## 本地环境

Python 依赖来自 [requirements.txt](../backend/requirements.txt)，前端依赖和命令来自 [package.json](../web/package.json)。CI 使用 Python 3.11、Node 20。安装：

```bash
python3 scripts/python_dependencies.py install
cd web && npm ci
```

本地后端环境放 `.runtime/fin_ops_platform/local-postgres.env`，不入库。配置专用开发 PostgreSQL DSN、PostgreSQL storage/read backend、对象存储与必要 OA 连接；可设置 `FIN_OPS_PYTHON_BIN`。不把生产环境当可重置的开发库。

```bash
./scripts/check-local-runtime.sh --dependencies-only
./scripts/start-backend.sh
# 另一终端
./scripts/start-web.sh
# 后端启动后
./scripts/check-local-runtime.sh --require-backend
```

后端默认 `127.0.0.1:18001`，由 Gunicorn + WSGI adapter 启动。迁移凭据与 runtime 分离，本地迁移文件为 `.runtime/fin_ops_platform/local-postgres-migrator.env`。设置专用 `FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL` 后运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres apply`；先确认 DSN 与命令实际选用同一个目标库，不向终端打印凭据。

PyMongo 使用 App 内安全补丁构建，见[驱动说明](../backend/vendor/pymongo/README.md)。
安装需要 C 编译器和 `patch`；安装包在 `.runtime/python-wheels/`，不提交二进制文件。

## 验证入口

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
git diff --check
```

`all` 额外包含依赖漏洞检查；使用 [nightly CI](../.github/workflows/nightly-ci.yml) 已有入口，不重复建立另一套流程。`frontend` 运行 Vitest 与 TypeScript/Vite build；`e2e` 运行真实 Chromium + deterministic API fixtures，证明前端交互，不替代真实数据库链路。`docs` 只检查当前导航与相对链接，不冻结文案或强制阶段文件。

单个后端测试：`PYTHONPATH=backend/src:tests python3 -m unittest tests.<module> -v`。单个前端测试在 `web/` 执行 `npx vitest run <file>`；浏览器执行 `npx playwright test e2e/<file> --project=chromium`。模块说明列出关键入口，其它覆盖通过对应代码/测试名称定位。

## 隔离 PostgreSQL 测试

需要真实数据库的测试显式使用 `FIN_OPS_TEST_DATABASE_URL`，现金相关测试还使用 `FIN_OPS_CASH_TEST_DATABASE_URL`。库名必须明确为可丢弃测试库（如 `fin_ops_cash_test_*`）；会清 schema 的套件不能并行共享同一库。

空集群准备迁移所需角色 `fin_ops_app_runtime`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_migrator`、`fin_ops_readonly`、`fin_ops_app`，本地 fixture 可用 NOLOGIN。常规用例应用完整当前迁移；历史结构反例在 cleanup 恢复完整结构，禁止只重建局部 schema 留下错误迁移记录。

运行测试进程前清除 runtime DSN（`FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_POSTGRES_READ_DATABASE_URL`、`DATABASE_URL` 等）并只注入测试 DSN。不要加载生产 token/env。无 PostgreSQL runtime 配置时 clean app check 验证启动被明确拒绝。缺环境导致的 skip 必须单列，不能报告成真实数据库验证通过。

## 测试责任与产物

按改动评估七类：业务规则、service/持久化、API、异步任务、前端交互、跨模块端到端、既有行为回归。只增加适用且能发现真实失败的用例；覆盖失败、权限、重复提交、并发/版本冲突与边界，而非只断言 HTTP 200。测试不能依赖真实业务导出物。

可逆操作影响矩阵位于 [测试 fixture](../tests/fixtures/write-operation-impact-matrix.json)。性能、截图和 trace 放 ignored `outputs/`、Playwright/Vitest 产物目录，不写进长期文档。Workbench receipt-to-DOM 测量保留其现有样本与生产 smoke 合同，输出 `outputs/workbench-direct-commit-visibility-p99.json`。

API 具体字段以 route、DTO/type 和 API 合同测试为准，业务含义见对应模块说明。金额/日期/身份不能靠猜测或前端替代计算。修改共享规则需要回归其直接消费者，不能因“旧文件名”删掉仍保护当前行为的测试。
