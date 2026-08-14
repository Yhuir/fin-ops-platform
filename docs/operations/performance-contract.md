# 生产性能合同

日期：2026-08-13

## 目标与边界

本合同约束用户可观察的首屏、核心读 API、写后可见性和导入持久化，不以新增 worker、read model、
Redis cache 或搜索 projection 掩盖慢查询。PostgreSQL 继续拥有 canonical facts；页面 query repository
拥有筛选、排序、分页和聚合；service 只编排业务 DTO。

生产只允许认证、有界、只读采样。百万级合成数据、`EXPLAIN ANALYZE`、批量写入和 destructive fixture
只能在数据库名包含 `test` 的隔离 PostgreSQL 执行；生产数据量小于目标规模时，不得把当前生产 p95
宣称为百万级证明。

## Blocking SLO

| 合同 | 阈值 | 证据 |
| --- | --- | --- |
| 页面首屏与核心读 API | 每个 probe p95 `<= 1000ms`，p99 `<= 2000ms`，错误 `0` | authenticated `http_slo_probe` |
| 写提交到消费者可见 | browser-inclusive p99 `<= 3000ms`，失败 `0` | isolated prod-equivalent Playwright same-clock T1 receipt → T2 canonical read → T3 DOM（至少 100 个样本） |
| PostgreSQL 连接获取 | p95 `<= 50ms`，无 backpressure rejection | `/health`、`/metrics` 与 HTTP probe 同窗样本 |
| 有界并发 | `N_normal=max(4,C_normal)`；`N_peak=max(8,C_peak)` | 命名 14 天容量证据或已批准 capacity contract；每 tier 固定 iterations、错误和 peak requests |
| 响应体 | 记录压缩传输 bytes p50/p95/p99；增长超过前一 release 25% 必须解释 | HTTP probe `response_bytes` |
| 导入持久化 | batch rows 按 bounded multi-value chunk 写入，禁止逐行数据库 round-trip | repository test、import integration/audit |

精确金额、total、summary、statistics、facets 和排序稳定性是正确性合同，
不得为了满足延迟阈值静默降级。确实不需要精确 total 的新页面可以独立采用 `hasMore`，但不能改变
既有财务页面 API。

首屏探针必须对应用户可见的 blocking 请求。成本统计首屏固定测量
`include_statistics=false` 的 scoped explorer；随后非阻塞全局 statistics 单独采样。待找发票 rows 与
filter options 分开采样；rows 不得重新内嵌高基数 options。银行明细、待找发票和往来款页面 DTO
不得传输浏览器未消费的规则执行字段、legacy 重复字段或导出专用 allocation lots。

## 数据规模带

| 级别 | 银行流水 | 发票 | OA | 关系 | 用途 |
| --- | ---: | ---: | ---: | ---: | --- |
| 当前生产 | 发布时从只读 baseline 记录实际值 | 同左 | 同左 | 同左 | 真实用户延迟与资源门禁 |
| 目标规模 | 1,000,000 | 500,000 | 1,000,000 | 500,000 | 隔离 PostgreSQL query-plan/benchmark |

目标规模 benchmark 至少覆盖 Workbench initial/groups、银行列表、待找发票、进项使用、销项收款、
成本统计和往来款。没有隔离数据源时，发布可以依据当前生产 SLO 决定，但报告必须把目标规模标记为
`not_measured`，不能写成通过。

`sync_slo_baseline.evidence_bands.current_production` 记录当前生产只读基线；
`evidence_bands.target_scale` 只有隔离目标规模数据库的独立 benchmark 才能改为 measured。默认报告固定为
`not_measured` 并列出四类目标行数，禁止用当前生产小样本或一次最快结果补写为通过。

## Workbench 容量与可见性证据

`C_normal` 和 `C_peak` 不是固定常量。首选最近 14 个完整自然日、能够区分 authenticated
visible client/session 的命名 access evidence，以 rolling 60-second unique visible clients 的匿名聚合计算
`C_normal=p95`、`C_peak=max`。证据必须记录 `source`、`source_version`、`source_proof`、自然日窗口和
`method=rolling_60s_unique_visible_clients` 和完整 `20,160` 个 minute buckets，不得保留 client/session 原始标识。若 access evidence 不能满足
该身份口径，只能使用带 `source`、`contract_version`、`approved_by` 的已批准 capacity contract。
两种证据都不可用时，结论固定为 `NOT_MEASURED`、`release_blocked=true`；`4/8` 只能作为压测下限，
不得冒充生产并发事实。

两个 tier 都必须覆盖 authenticated Workbench combined initial、paired/unpaired groups 和 filter-options，证明每个 blocking probe p95 `<=1000ms`、p99 `<=2000ms`、error `0`，并在同一窗口检查 HTTP active/peak requests、PostgreSQL pool/acquire/SQL、DB CPU/IO/temp spill 及 required worker 无饱和，同时证明 Workbench page event/cache/projection I/O 为零。派生 target 超过当前 probe 的有界 worker 上限 `8` 时不得静默截断，
必须阻断并由批准的容量执行方案承接。

commit-to-visible 证据由现有 Playwright/Node 单一 `performance.now()` 时钟记录整数微秒：T1 在 mutation 2xx receipt 解析完成后开始，T2 为写成功后的正常 canonical GET 已包含精确 relation/decision identity，T3 为唯一 DOM identity 可见。报告只包含 `canonical_read_us`、`browser_render_us` 与 `receipt_to_dom_us`，且前两段之和
严格等于 T1→T3 总耗时；窗口内没有 page refresh-status、generation 或 worker wait。隔离 prod-equivalent run 至少 100 个 test-owned、可逆样本才计算 p99；生产 run
恰好一个已批准样本，仅作为 smoke 合并进既有报告，不能覆盖隔离样本或重新声称 p99。

## 执行入口

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sync_slo_baseline --json

scripts/with-production-admin-token.sh \
  env PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --iterations 20 \
  --warmup 2 \
  --concurrency 4 \
  --target-ms 1000
```

`http_slo_probe` 默认串行，worker 硬上限为 `8`。报告记录命名环境、证据窗、
`request_count/error_count/error_counts` 以及 duration/压缩 response bytes 的 p50/p95/p99；错误分布只保留
分类字符串，不保存响应业务 payload、认证 header、token 或 cookie。

优化顺序固定为：测量并拆分 HTTP/DB/payload 成本；检查 `EXPLAIN`；改 SQL/算法；有证据才加索引；
前后 benchmark；最后才评估缓存或异步。任何重大查询修改都必须先通过业务 fixture 等价、API contract、
跨页面回归，再比较性能。

## 发布判定

- T0 与 T+30 验证 exact release、4 个 required workers、0 个 read model、通用 outbox 与领域队列
  收敛、System Audit 和核心 API SLO；发布后持续监控沿用同一合同，不恢复 projection 或 freshness worker。
- 单次最快样本、public shell、未认证 401/403、HTML fallback、零样本或旧 release 指标都不能作为通过。
- rollback 锚点保留上一 release；若正确性、错误率、p95/p99、连接获取或 queue 任一项退化，停止扩量并
  回滚，不用缓存/fallback 隐藏失败。
