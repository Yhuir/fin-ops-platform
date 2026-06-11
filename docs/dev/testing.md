# 测试与验证

本文件是开发验证入口。测试闭环的全局状态见 `testing-closure-state.md`，跨页面/API/read model/worker 依赖地图见 `testing-closure-dependency-map.md`，nightly CI 规则见 `nightly-ci.md`。

## 验证层级

- 本地目标验证：修改某个模块时，优先运行 `docs/modules/<module>/tests.md` 中列出的模块命令。
- 统一本地验证：运行 `bash scripts/verify.sh all`。
- Nightly CI：每天自动运行后端全量 unittest、前端 Vitest、前端 build 和文档检查。
- 发布前验证：涉及生产数据、read model、worker、OA、Redis/RabbitMQ/PostgreSQL runtime 或部署资产时，按模块文档和运维文档补充 dry-run、staging 或生产只读 smoke。

## 统一验证入口

```bash
bash scripts/verify.sh all
```

可选目标：

```bash
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
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
```

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
