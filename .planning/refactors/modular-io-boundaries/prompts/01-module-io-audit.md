# Prompt 模板: 单模块 IO 审计

使用方式：

```text
使用 GSD 对 <module-key> 做模块化 IO 审计。只做分析和文档，不改业务代码。

必须读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/app-architecture/README.md
- docs/app-architecture/runtime-and-ownership.md
- docs/modules/README.md
- docs/modules/<module-key>/README.md
- docs/modules/<module-key>/state-machine.md
- docs/modules/<module-key>/tests.md
- docs/modules/<module-key>/e2e-spec.md
- docs/modules/<module-key>/e2e-coverage.md
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md

任务：
1. 检查当前 git status，不回滚用户变更。
2. 用 CodeGraph 和静态扫描找出模块 entry points。
3. 列出 frontend page/components/features/api/types/domain events。
4. 列出 backend routes/services/repositories/read models/workers。
5. 列出 input/output/state/event/read model/permission/test contracts。
6. 列出 legacy route/service/repository/read model/frontend API，并标记删除、隔离或 compat-only 条件。
7. 列出 force refresh 入口、affected scopes、freshness proof、operation barrier 和跨页面依赖。
8. 列出 read model partition key、scope key、incremental projection trigger、full rebuild fallback 和 parent/aggregate 规则。
9. 如果模块在 Go candidate list 中，列出 candidate key、性能证据缺口、shadow run 可行性、Python-vs-Go equivalence 和 rollback 条件；不能直接实现 Go。
10. 找出当前实现与目标 IO 合同的 gap，特别标记旧链路污染新链路的风险。
11. 明确没有本地 PGSQL_URL 和 staging 数据库时，本模块哪些验证只能用 fake/stub，哪些必须生产只读或受控写入验证。
12. 只写入 .planning/refactors/modular-io-boundaries/analysis/<module-key>-io-audit.md。

禁止：
- 不改业务代码。
- 不迁移文件。
- 不更新长期 docs，除非用户另行授权。
- 不猜未知字段或 response shape。
- 不要求用户把 SSH 密码、数据库密码、token、cookie 或生产 DSN 粘贴到聊天中。
- 不把任何 secret 写进文档、脚本、测试或命令。

输出：
- 当前状态摘要。
- 完整 IO 合同草案。
- gap list。
- 风险登记。
- 推荐测试补齐清单。
- legacy 退役/隔离清单。
- read model force refresh/freshness proof 清单。
- partitioned scoped incremental projection 清单。
- Go candidate admission 清单或 not applicable。
- 环境限制和生产验证分层。
- 是否适合作为试点。
```
