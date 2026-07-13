# 2026-07-13 - 关联台银行流水数量不是 910

## Symptom

- 银行明细 canonical source fact 为 910 条。
- 关联台 `month=all` 的两栏稳定计数为：paired 464、open 344，合计 808。
- `/api/workbench/summary` 同时返回 `bank_count=964`，与页面分区计数不一致。

## Root Cause

稳定数量可以精确闭合：

```text
910 canonical bank transactions
- 37 OA 待付款独占 claim（39 条 claim 中 2 条同时有 active Workbench relation，仍可见）
- 65 被 Workbench open list 查询错误隐藏的 decision rows
= 808 页面可见银行流水
```

65 条隐藏流水属于 61 个 `case:decision:*` case，银行明细 relation consumer 将它们标为 `linked`。抽样读取 10 个 group detail，10/10 位于 `open`、`group_type=candidate`，0/10 位于 paired。`PostgresReadModelRepository.get_workbench_groups_page(...)` 对 open 区无条件追加 `g.group_id not like 'case:decision:%%'`，把这些真实存在的 active-generation group 从列表 API 排除。

`/api/workbench/summary?month=all` 的 964 不是全局 distinct bank count。`_get_workbench_all_summary_from_active_month_shards()` 直接相加 19 个 active month shard summary；跨月 relation/member 会在多个月分片重复计数。全局 groups API 随后执行 owner arbitration、折叠和 decision-group 排除，所以 summary 964、canonical 910、页面 808 是三种不同口径。

## Production Evidence

- `GET /api/operations/app-health/page-audit?page=bank-details`：`source_fact_count=910`、`read_model_row_count=910`。
- `GET /api/workbench/groups?month=all&zone=paired...`：`row_counts.bank=464`。
- `GET /api/workbench/groups?month=all&zone=open...`：`row_counts.bank=344`。
- 全量只读 ID 对账：910 个 bank-detail ID；重建 Workbench collapsed/case owner 后可见 808；差集 102。
- OA 待付款候选 API：`linked_in_progress=39`；其中 37 在 Workbench 差集，2 条因同时存在 active Workbench relation 仍可见。
- 剩余差集 65 条全部是 `case:decision:*`、`relation_status=linked`；月份分布：2026-01 8、2026-02 4、2026-03 7、2026-04 20、2026-05 11、2026-06 15。
- 隐藏 65 条覆盖 61 个 case；抽样 10 个 group detail 全部能从 open detail API 读取，证明不是 canonical 缺失、导入丢失、分页遗漏或前端本地过滤。

## Runtime Observation

- 15:14 与 15:30 左右的 OA sync 会 fan-out 多个月份 Workbench refresh；刷新期间 all query-composed 计数曾短暂下降，收敛后恢复为 808。
- 收敛快照曾显示 `read_model_status=fresh`、`consistency_status=fresh`、dirty scope 为空；下一轮 OA sync 又进入 refreshing。
- `worker_lag_seconds` 仍约 10.5 天，但 Workbench 月分片能在约 6 分钟内实际收敛；该 heartbeat 指标异常不是稳定 808 的直接原因，需单独运维排查。

## Eliminated

- 不是银行流水导入缺失：canonical 与 bank-detail read model 都是 910。
- 不是前端分页或首屏只加载部分数据：页面标题使用后端 `row_counts.bank`。
- 不是 ignored rows：`/api/workbench/ignored?month=all` 返回 0。
- 不是 read model generation consistency failure：生产 `consistency_status=fresh`。
- Bank Details Audit 的 2 条 `linked_oa_tag_mismatch` 是独立 relation-tag 问题，不改变 910/808 计数。

## Diagnosis-only Fix Direction

1. open groups 查询不能按 `case:decision:*` 名称一刀切；必须只隐藏未正式化 decision，保留 canonical active relation owner，即按 relation fact/status/ownership 判断。
2. `month=all` summary 应复用 query-composed global owner/distinct 口径，或停止把 shard-sum `bank_count` 暴露为全局银行流水数。
3. Page Audit 应增加 `canonical eligible bank set == public groups API represented bank set` 检查，覆盖 collapsed rows、OA pending claims 和 active decision-case rows。
4. 单独核对 Workbench worker heartbeat/lag 和周期 OA sync fan-out 的中间态可见性。

本次仅诊断，没有执行 refresh、repair、SQL 写入或代码修改。
