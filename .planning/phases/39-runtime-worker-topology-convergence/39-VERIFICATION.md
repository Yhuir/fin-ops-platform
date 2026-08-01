---
phase: 39-runtime-worker-topology-convergence
status: passed
verified_at: 2026-08-01
release: main-a2d03430-20260801133923
git_commit: a2d034307da16a3c17d7ed0fb7b5620a90422f49
---

# Phase 39 验证记录

## 本地结论

本地实现、静态边界、后端、前端、生产构建、Chromium E2E、docs、lint 和 infra 合同门禁全部通过。Search/no-OA 派生 runtime 的正向入口已删除；六 worker/两 read model 单一事实源由 registry、manifest、RabbitMQ、deploy、App Health 和架构守卫共同约束。

## 生产结论

Phase 39 已通过生产验证，无剩余发布 blocker。

| 验证项 | 结果 |
|---|---|
| 提交与发布 | `a2d034307da16a3c17d7ed0fb7b5620a90422f49` 已推送 `origin/main`；active release 为 `main-a2d03430-20260801133923` |
| 回滚锚点 | previous release `main-d18edd00-20260801072547` 保留；release gate 未触发 rollback |
| 时序门禁 | pre、T+0、T+60、T+300 全部 PASS，queue stable after 300 seconds |
| Worker | 精确 6 个 required instance active/available，`required_worker_not_ready=0`、`unknown_worker_count=0` |
| 旧 unit | no-OA、Search 三实例、Workbench secondary 全部 `inactive/disabled` |
| 队列 | pending/publishing outbox、dirty scope、failed/dead-letter 全部为 0 |
| 合同 | domain contract audit、page canonical audit、runtime sync closure、worker inventory 全部 PASS |
| 核心 HTTP | 32 个 API、640 个测量样本、0 失败，最大 p95 `751.858ms` |
| no-OA canonical list | 当前月 p50/p95/p99 `893.811/983.787/1015.582ms`，20/20 HTTP 200，p95 `<1s` |
| 当前 bank-flow 列表 | 未提交/已提交 p95 `64.097/32.779ms`，40/40 HTTP 200 |
| 内部转账链 | Workbench fresh；35 个 bank-flow internal-transfer group，零无效 group；抽样详情为 submitted/2 rows/全 internal_transfer，详情 p95 `52.295ms` |
| HTTP/DB 资源 | HTTP active/peak `1/4`，各类拒绝为 0；PostgreSQL pool size/max/available/waiting `4/10/3/0` |

## 性能边界与解释

- 本地 Mac 从公网运行 Python 探针时因本机 CA 链缺失出现 `CERTIFICATE_VERIFY_FAILED`，请求未到达应用，该数据未被当作性能证据。最终证据使用生产机 `127.0.0.1:18001` 认证内环采样，token 仅经 SSH stdin 传递。
- legacy no-OA `month=all` 跨全历史查询 p95 约 `2.59s`；它无当前页面消费者，不属于首屏 SLO。精确月 scope 已达标，因此未引入 cache、projection 或退役 worker 来优化无消费者路径。
- 生产验证全部只读；没有创建或修改真实财务业务关系。写后 SLO 继续由已有发布门禁、近期审计与独立受控 write-smoke 政策负责。
