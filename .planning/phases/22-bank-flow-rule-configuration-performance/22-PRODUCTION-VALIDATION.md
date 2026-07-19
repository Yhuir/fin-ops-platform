# 第 2 项生产发布与验收

## 发布身份

- Git SHA：`182c29be4d6b1f9fd91001d88600fddd411bf2ef`。
- Release：`main-182c29be-20260720015418`。
- 标准入口：`./scripts/deploy-oa.sh`，退出码 0。
- migration 0111：生产应用成功，耗时 42ms。
- `fin-ops.service`、RabbitMQ dispatcher 与 22 个 runtime workers 全部 active，并使用该 release 的 `src` 工作目录；worker workdir mismatch 为 0。

## 生产读取性能

20 次采样，另有 2 次 warmup：

| Probe | p50 | p95 | p99 | 门槛 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| 页面壳 | 122.051ms | 139.570ms | 150.837ms | 1000ms | pass |
| GET tag-rules | 171.907ms | 258.567ms | 289.098ms | 1000ms | pass |
| Page Audit | 282.269ms | 370.022ms | 441.628ms | 1000ms | pass |

60/60 响应成功；无 non-fresh、refresh enqueue 或 HTTP error。

## 生产 no-op 写性能

- 使用生产当前 43 条规则、`expected_version=11` 执行同值 PUT。
- 共发出 21 次安全 no-op：20 次纳入性能统计；首轮测量脚本在完成第 1 次请求后因本地 awk 格式化错误停止，该请求同样未改变最终 version。
- 20 次测量全部 HTTP 200，response version 均为 11；最终 GET version 仍为 11。
- p50 `211.120ms`，p95 `275.186ms`，max `431.232ms`，全部低于 `<500ms` 门槛。
- 结合真实 PostgreSQL integration/microbenchmark 证据，no-op 不写 settings/audit/dirty scope；生产前后 version 不变且 Page Audit queue 保持 drained。

## Audit 与隔离

no-op PUT 后逐页验证：

| 页面 | integrity | freshness | queue | issues |
| --- | --- | --- | --- | ---: |
| 流水规则批量处理 | pass | fresh | drained | 0 |
| 关联台 | pass | fresh | drained | 0 |
| 银行明细 | pass | fresh | drained | 0 |
| 外部往来款管理 | pass | fresh | drained | 0 |

四页均为 `proof_availability=ready`、`page-audit-contract.v25`。这证明规则 no-op 没有制造 bank-flow、Workbench relation、bank detail 或 turnover dirty/outbox 污染。

## 结论

第 2 项“流水规则配置子链路”满足设计、实施、性能、Audit、隔离、旧链删除和生产发布门禁，可以关闭并进入第 3 项“批量处理子链路”。
