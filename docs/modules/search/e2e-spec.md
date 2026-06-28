# Search E2E Spec

`search` 是资源/API 模块，不是独立前端页面。当前 Spec-first 合同以 direct API payload 和跨模块回归为主。

`/api/search` 目前没有独立前端页面或用户可点击的全局搜索入口。Search 的用户影响通过业务页面写入、API/runtime 测试覆盖；Search read-model worker 已删除。

| Spec ID | 用户目标 | 优先级 | 验收合同 |
| --- | --- | --- | --- |
| `SEARCH-E2E-001` | 跨模块搜索读取必须返回 direct business payload | P1 | `/api/search` 直接返回 `SearchService.search(...)` payload，不返回 `read_model_status`、`refresh_enqueued`、scope key 或 `read_model_unavailable`；legacy SQL index missing/stale/source-version mismatch 不能阻断页面读取；不得恢复 Search read-model worker。 |

如果后续新增全局搜索 UI，本文件必须先补 Spec ID，再新增 Browser E2E。
