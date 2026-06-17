# 测试与验证

本文件是开发验证入口。测试闭环的全局状态见 `testing-closure-state.md`，跨页面/API/read model/worker 依赖地图见 `testing-closure-dependency-map.md`，Spec-first Browser e2e 审计规则见 `spec-first-e2e-audit.md`，审计队列见 `spec-first-e2e-inventory.md`，nightly CI 规则见 `nightly-ci.md`。

## 验证层级

- 本地目标验证：修改某个模块时，优先运行 `docs/modules/<module>/tests.md` 中列出的模块命令。
- 统一本地验证：运行 `bash scripts/verify.sh all`，覆盖后端、前端 Vitest/build、deterministic Playwright browser smoke 和文档检查。
- Nightly CI：每天自动运行后端全量 unittest、前端 Vitest、前端 build、Playwright browser smoke 和文档检查。
- 发布前验证：涉及生产数据、read model、worker、OA、Redis/RabbitMQ/PostgreSQL runtime 或部署资产时，按模块文档和运维文档补充 dry-run、staging 或生产只读 smoke。

## 统一验证入口

```bash
bash scripts/verify.sh all
```

可选目标：

```bash
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
```

## 后端

基础检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

全量单元测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 前端

```bash
cd web
npm test
npm run build
npm run e2e:smoke
```

## Browser e2e / Playwright

默认 browser e2e 使用 Playwright Chromium、Vite dev server 和 deterministic API mocks，目标是用真实浏览器保护 shell、导航、会话 gate、权限 gate、App Status/AppHealth，以及高 fan-out 页面之间的核心业务链路。目前 smoke 覆盖 app shell / AppHealth 权限门禁、compact/mobile drawer、embedded OA shell、`read_export_only/full_access/admin` 全页面角色矩阵和高风险写入口权限门禁，并覆盖 `关联台 confirm -> bank details relation tags`、`关联台 confirm -> pending invoices invoice status`、`batch accounting submit/withdraw -> workbench_relation barrier -> bucket recovery`、`turnover ledger manual closure confirm/withdraw -> turnover/workbench barriers -> closure recovery`、`bank import preview/confirm -> workbench refresh -> bank details imported row`、`invoice import input/output preview/confirm -> workbench refresh`、`ETC invoice ready task zip preview/confirm -> background import job`、`tax offset recalculate/save -> certified import preview/confirm -> tax page refresh`、`settings data reset impact/password/job polling -> settings reload`、`output invoice collection status/reminder save -> rows refresh -> formal receipt create/history`、`input invoice OA reverse selected subset -> OA draft -> submitted history`、`ETC ticket imported business batch -> OA draft -> manual submitted bucket`、`OA pending payments rows/filter/sort -> OA/bank/invoice/rules drawers`、`no-OA selected row submit -> freshness barrier -> submitted withdraw -> history`、`cost statistics project drilldown -> transaction detail -> export row-limit feedback` 的跨页面/跨读模型同步。

新增或重写 Playwright 前先按 `spec-first-e2e-audit.md` 建立或更新模块 `e2e-spec.md` 和 `e2e-coverage.md`。Playwright 的验收标准来自业务 Spec；代码只用于定位 route、selector、API mock 和运行细节。

```bash
cd web
npm run e2e:smoke
```

这类测试应优先覆盖用户可见业务流、导航、弹窗、下载、iframe、焦点、滚动、大表格、网络恢复和跨页面同步。真实 PostgreSQL/RabbitMQ/Redis/systemd worker/OA Mongo/对象存储不属于默认本地 mock e2e，应通过 staging、只读生产 smoke 或显式 runtime gate 补充。

## 文档变更检查

文档结构调整后至少执行：

```bash
find docs -maxdepth 3 -type f -name '*.md' | sort
rg -n "docs/product/|OA 集成当前 app 技术方案" README.md docs backend web deploy -g '*.md'
```

如果只是文档重排，不要求运行业务测试；但必须检查路径和索引不会继续指向已移动位置。

## 测试闭环维护规则

- 每次修改或新增功能前，先识别目标模块并读取 `docs/modules/<module>/tests.md`。
- 如果改动可能影响旧功能，先补 characterization/regression test，再改实现。
- 如果修复 bug，必须新增或更新一个能复现该 bug 的 regression test，并记录到模块 `tests.md` 的历史 bug 回归库。
- 如果改动涉及 read model、dirty scope、worker、API response shape、权限、导出或跨页刷新，必须在对应模块 `tests.md` 中更新影响面和未测风险。
- 不允许用 skip、删除测试、放松断言或隐藏错误来通过验证。
