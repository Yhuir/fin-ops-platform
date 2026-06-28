# Canonical Facts 实施记录

## 2026-06-26 初始边界补充

目标：

- 明确“统一事实源”在本仓库中指 PostgreSQL canonical facts + 各业务 owner 模块，不是 read model。
- 新增 canonical facts owner matrix 和全局 I/O 规则。
- 将该规则接入 `docs/architecture/module-boundaries/` 与 `docs/modules/` 索引。

决策：

- `canonical-facts` 是资源治理模块，不新增运行时代码模块或 `UnifiedFactSource` service。
- `read-models` 继续只负责派生投影、freshness、refresh 和 operation barrier。
- 各业务事实仍归属现有业务模块，后续逐模块在对应 `boundary-io.md` 落细。

本轮未做：

- 未移动 repository、service 或 migration。
- 未新增数据库 schema。
- 未删除 legacy path。
- 未新增测试，因为没有运行时代码行为变化。

风险：

- owner matrix 是基于 migrations、长期文档和当前 service/repository 命名形成的初表；后续代码重构必须逐调用点验证。
- shared repository 和兼容路径仍可能让 owner 边界不够清晰，需按模块小步收口。
