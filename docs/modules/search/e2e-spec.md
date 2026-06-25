# Search E2E Spec

`search` 是 read model API/索引模块，不是独立前端页面。当前 Spec-first 合同以 API/runtime/read model freshness 为主。

`/api/search` 目前没有独立前端页面或用户可点击的全局搜索入口。Search 的用户影响通过业务页面写入、relation fan-out、API/runtime 测试和 read model worker 测试覆盖。

| Spec ID | 用户目标 | 优先级 | 验收合同 |
| --- | --- | --- | --- |
| `SEARCH-E2E-001` | 跨模块搜索读取必须使用 fresh search read model | P1 | `/api/search` 在 SQL payload missing、stale 或 source-version mismatch 时返回 non-fresh status 并入队 refresh；不能同步 live scan 后伪装 fresh；relation/import fan-out 后 search worker 必须能重建对应 month shard。 |

如果后续新增全局搜索 UI，本文件必须先补 Spec ID，再新增 Browser E2E。
