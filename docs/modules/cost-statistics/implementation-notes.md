# 成本统计实施决策

## 2026-07-26：改为直接 canonical read

- 保留现有 API、视图、标签规则和导出业务合同。
- 删除 Cost 专属 read model、投影、worker、scope、source version、runtime service 与生命周期入口。
- 每个请求从一个 PostgreSQL `REPEATABLE READ READ ONLY` 快照读取统一事实源。
- 业务计算集中在无 I/O 的 `CostStatisticsPolicy`；repository 只负责读取，route 只负责 HTTP。
- Audit 改为直接 canonical proof，Cost 不再出现在 App Status read-model/worker 诊断中。
- migration `0126` 终止遗留 Cost runtime 行并删除旧 Cost read-model 表。

这是本模块当前唯一读链。历史的 parent/shard、freshness gate、dependency defer、conditional publish 和 Redis cache 设计已经被本决策取代，不再作为实现依据。

## 2026-07-28：局部加载与 canonical scope 下推

- 删除后续 explorer 请求中的 `setLoadedExplorer(null)` 全页清空链路；保留已加载的上游栏位，按 `surface / children / rows` 只替换受影响区域。
- 页头统计仅在本次页面会话的首次 explorer 请求计算；后续请求使用 `include_statistics=false`，页头沿用同一 canonical 响应得到的统计值。
- repository 只在后续非 `all` 请求下推 `txn_month` 范围；成本视图以命中银行流水筛 active relation 后扩展全部 relation 成员，避免破坏跨月份配对。
- `time / bank_tag` 后续请求不读取 OA 与配对关系。所有路径仍在单个 `REPEATABLE READ READ ONLY` 快照内直接读取 canonical tables，没有 read model、cache、worker 或 fallback。
- 按标签桌面列宽为 `20% / 20% / 60%`；支出在上、收入在下，零金额只隐藏金额数值。

## 2026-07-28：日常报销付款明细级成本分配

- repository 和 API 保持不变；现有 canonical OA payload 已包含稳定 `expense_item_id`、项目、费用类型、内容和金额，不新增表、read model、worker 或查询。
- 支付申请继续作为一个 OA 分配单元；日常报销在 `CostStatisticsPolicy` 内展开为 `expense_items` 分配单元。
- 单流水仅在全部单元 ID 有效唯一、金额为正且合计按分等于流水金额时拆分。其它情况不做比例、顺序或子集推断，流水金额只计一次。
- 歧义场景仅保留所有单元完全一致的共同项目/费用维度，否则使用 `未归集项目` / `未分类`；删除成本统计运行时的 `多项目` / `多费用类型` 合成口径。
- project、bank、expense_type、详情与导出共享同一组分配行；`transaction_count` 继续按银行流水去重，详情 `linked_oa_count` 按 OA 去重而不是按付款明细计数。
- canonical repository 直接从同一 snapshot 的 `app.oa_applications.normalized_payload` 映射成本 policy 所需父单/付款明细字段，避免 OA repository 构造完整 record 并递归复制成本页面不消费的附件与发票树；不减少成本归因字段，也不新增查询或缓存。
