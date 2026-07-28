# 关联台逐栏折叠与搜索结果直显修复

## 完成内容

- ETC 仅折叠发票栏；group detail 按 `collapsed_row_counts.<pane>` 逐栏校验，OA、银行正常行不再被错误地拿去和发票折叠数比较。
- 流水规则批次仅在银行流水超过 3 条时折叠；普通关系和 legacy no-OA 关系全部直接显示。
- 删除普通分组三行 preview、`no_oa_bank_batch_summary` 和“隐藏内容命中”旧合同。
- 折叠成员命中搜索时，闭合态最多显示 3 条真实命中行；不自动展开、不自动预取详情。
- Workbench schema 升级为 v10，阻止旧 generation/cache 继续提供旧显示合同。
- 没有新增 API、表、索引、worker、缓存、fallback 或依赖；OA 待付款核对仍走独立 canonical API 直读链路。

## 本地验证

- 后端 grouping/runtime/no-OA/search 合同：228 passed。
- 后端 Workbench API/query/route/projection 回归：134 passed。
- 前端 API/RelationGroupGrid：82 passed。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `npm run build`：通过；仅保留既有第三方 CSS/chunk size warning。
- `git diff --check` 与旧合同全仓扫描：通过。

## 测试分类

- 业务核心单测：覆盖折叠阈值、no-OA 直显、搜索真实命中。
- Service/read-model：覆盖 grouping、projection 持久化、schema v10 与旧 generation 拒绝。
- API contract：覆盖逐栏 group detail 完整性。
- Read model/cache/background：覆盖 active-generation schema；没有新增 worker/cache 行为。
- 前端交互：覆盖直显、折叠、展开失败重试、搜索闭合态预览。
- 跨模块集成：覆盖 no-OA 与 bank-flow 提交后 Workbench 展示。
- 既有功能回归：覆盖 Workbench routes/query/search/withdraw。

权限合同、关系写入状态机和数据库 schema 未改变，因此没有新增权限测试、migration 测试或可逆写生产场景；生产阶段只执行只读页面 Audit、payload 合同和性能验证。
