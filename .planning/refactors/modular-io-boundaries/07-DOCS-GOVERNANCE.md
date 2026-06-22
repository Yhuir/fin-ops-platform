# 文档治理规则

**用途:** 说明本目录与长期文档的关系，避免规划文档和事实源冲突。

## 事实源优先级

当前事实源顺序：

1. `AGENTS.md`
2. `README.md`
3. `ARCHITECTURE.md`
4. `docs/index.md`
5. `docs/app-architecture/`
6. `docs/modules/`
7. `docs/product-specs/`
8. `docs/dev/`
9. `docs/operations/`
10. `.planning/`

`.planning/refactors/modular-io-boundaries/` 是工作区，不是长期事实源。

## 什么时候只更新本目录

以下情况只更新本目录：

- 重构需求分析。
- 代码审计摘要。
- 试点选择。
- 迁移计划草案。
- prompt 模板。
- 风险登记。
- 状态机进度。

## 什么时候必须同步长期文档

以下情况必须同步 `docs/`：

- 业务口径变化: 更新 `docs/product-specs/`。
- 页面/API/运行时变化: 更新 `docs/app-architecture/` 或 `docs/dev/`。
- 模块事实、状态机、测试矩阵变化: 更新 `docs/modules/<module>/`。
- read model/worker/queue 变化: 更新 `docs/modules/read-models/`、`docs/modules/runtime-workers/`、`docs/operations/`。
- 权限/审计变化: 更新 `docs/modules/permissions-and-audit/`。
- 部署/运维变化: 更新 `docs/operations/` 和 `deploy/oa/README.md`。

## prompt 管理

允许：

- 在本目录 `prompts/` 保存可复用模板。
- 模板中声明必须读取的文件、输出格式、禁止范围和验收标准。

禁止：

- 把未经提炼的原始对话复制到长期文档。
- 把一次性 prompt 当成事实源。
- 在 `docs/modules/<module>/implementation-notes.md` 保存完整 prompt。
- 把 SSH 密码、数据库密码、token、cookie、生产 DSN 或其它 secret 写进 `.planning/`、`docs/`、脚本、测试或 commit message。

## 模块 IO 合同沉淀规则

试点阶段：

- IO 合同可以先在 `.planning/refactors/modular-io-boundaries/analysis/` 草拟。

实现阶段：

- 合同中成为长期事实的内容必须同步到 `docs/modules/<module>/README.md`、`state-machine.md`、`tests.md` 或新增模块文档。

完成阶段：

- `.planning/` 保留执行摘要、风险和状态。
- `docs/` 保存当前事实。

## docs impact 模板

每次实现 summary 必须包含：

```text
Docs impact:
- docs/modules/<module>/README.md: updated / not applicable
- docs/modules/<module>/state-machine.md: updated / not applicable
- docs/modules/<module>/tests.md: updated / not applicable
- docs/app-architecture/*: updated / not applicable
- docs/dev/*: updated / not applicable
- docs/operations/*: updated / not applicable
- Reason if not applicable:
Environment validation:
- Local PGSQL_URL available: yes/no
- Staging DB available: yes/no
- Production read-only validation: done/pending/not applicable
- Production controlled-write validation: done/pending/not applicable
- Secret handling: no secrets recorded
```
