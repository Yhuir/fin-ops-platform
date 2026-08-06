# 生产性能合同

日期：2026-08-01

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
| 写提交到消费者可见 | p99 `<= 3000ms`，失败 `0` | 已审批的 checkpoint write-operation smoke |
| PostgreSQL 连接获取 | p95 `<= 50ms`，无 backpressure rejection | `/health`、`/metrics` 与 HTTP probe 同窗样本 |
| 有界并发 | concurrency `4` 为发布门禁；高峰准备 concurrency `8` | 每个 probe 固定 iterations、错误和 peak requests |
| 响应体 | 记录压缩传输 bytes p50/p95/p99；增长超过前一 release 25% 必须解释 | HTTP probe `response_bytes` |
| 导入持久化 | batch rows 按 bounded multi-value chunk 写入，禁止逐行数据库 round-trip | repository test、import integration/audit |

精确金额、total、summary、statistics、facets、active generation/version 和排序稳定性是正确性合同，
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

- T0、T+60、T+300 均验证 exact release、6 required workers、2 retained read models、queue/dirty scope
  收敛、System Audit 和核心 API SLO。
- 单次最快样本、public shell、未认证 401/403、HTML fallback、零样本或旧 release 指标都不能作为通过。
- rollback 锚点保留上一 release；若正确性、错误率、p95/p99、连接获取或 queue 任一项退化，停止扩量并
  回滚，不用缓存/fallback 隐藏失败。
