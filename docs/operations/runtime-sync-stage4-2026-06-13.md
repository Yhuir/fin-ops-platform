# Runtime 同步 Stage 4 - 全页面 HTTP SLO 覆盖入口

本阶段目标是把 Stage 3 的 direct-scope read model 证据扩展到登录态页面和首屏 API。Stage 3 已证明 App Status
critical read model 可以通过真实 durable queue/RabbitMQ worker 在 5 秒内收敛，但这仍不等于用户打开每个页面都能在
5 秒内得到真实 fresh 体验。

本阶段没有引入 Kafka、PgBouncer、分区或新的缓存层。当前证据显示队列 broker 不是主要瓶颈：Stage 3 生产
RabbitMQ depth/unacked/DLQ 为 0，consumer 数正常，dispatcher idle wait 已降到 0.5 秒。Kafka 适合高吞吐事件流和
长期回放，不适合用来修复当前“页面首屏 API 慢、写操作链路未验收、部分 SQL/read model 未覆盖”的问题；引入 Kafka
还会增加 exactly-once/idempotency、运维、监控和回滚复杂度。除非后续基线证明 RabbitMQ wakeup 或队列吞吐成为
5 秒 SLO 的主瓶颈，否则不作为闭环必需组件。

## 本地变更

- `http_slo_probe` 默认页面 probe 从只覆盖 `/fin-ops/` 扩展为覆盖所有主要页面 shell：
  关联台、银行明细、待找发票、进项使用、OA 待付款、销项收款、税金抵扣、成本统计、免 OA、批量账务、往来款、ETC、
  导入、设置和 App Health。
- 默认 API probe 扩展到主要首屏/辅助接口：
  工作台 summary/groups/settings、银行明细账户/流水/规则、待找发票 rows/filter-options/rules、进项发票使用
  rows/filter-options/rules、OA 待付款 rows/filter-options、销项收款 rows/filter-options/rules、税金抵扣、
  成本统计、免 OA、批量账务、往来款、ETC、导入 facts、后台任务和搜索。
- `pending-invoices/filter-options` 是历史慢接口，默认 probe 必须覆盖，不能靠只测 rows 或首页绕过。
- 页面 probe 名称改为稳定页面名，例如 `page_shell_pending_invoices`，便于报告、告警和阶段复盘直接定位页面。
- `docs/operations/monitoring.md` 同步更新默认覆盖面和最终验收边界。

本地验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_http_slo_probe.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_http_slo_probe.py tests/test_read_model_slo_smoke.py -q
python3 -m py_compile backend/src/fin_ops_platform/tools/http_slo_probe.py
bash scripts/verify.sh docs
git diff --check
```

结果：`tests/test_http_slo_probe.py` 6 passed，HTTP/read model smoke 工具相关测试 11 passed，语法、docs 和 diff check 通过。

## 生产 public shell smoke

本阶段额外运行了一轮无认证 public page shell smoke，只验证页面路由和静态 shell 首包：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --allow-unauthenticated \
  --replace-default-probes \
  --iterations 3 \
  --warmup 1 \
  --target-ms 5000 \
  --output /tmp/finops-http-page-shell-smoke-20260613115439.json
```

结果：17/17 page shell probe 通过，最大 p95 为 185.197ms。该结果不能作为最终登录态页面/API SLO 证据，因为它不覆盖
认证后的 API、权限、read model freshness、cache gate 或写操作后的页面收敛。

## 生产验收命令

最终登录态 HTTP SLO 必须使用真实管理员 token、bearer token 或 cookie：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --iterations 20 \
  --warmup 2 \
  --target-ms 1000 \
  --output /tmp/finops-http-slo-$(date +%Y%m%d%H%M%S).json
```

没有认证参数时，工具返回 `auth_missing`，不能作为生产页面 SLO 证据。`--allow-unauthenticated` 只能做 public
page shell smoke，不能证明登录态 API、权限、fresh gate 或用户真实页面体验。

## 判定标准

Stage 4 通过需要同时满足：

- 每个默认 page shell probe p95 `< 1000ms`，且无 4xx/5xx。
- 每个默认首屏 API probe p95 `< 1000ms`，且无 4xx/5xx。
- read model API 如果返回 `202`，必须有可解释的 `read_model_status/cache_status/refresh_enqueued`，且后续
  enqueue-to-fresh 由 read model smoke 或写操作链路证明 `< 5000ms`。
- `pending-invoices/filter-options`、搜索、工作台 groups、导入 facts 等历史或潜在慢接口不能排除在默认采样外。
- 采样后必须复核 `/health/ready`、dirty scope、outbox、RabbitMQ queue/DLQ 和 App Status current-effective blocker，
  避免页面 HTTP 快但后端实际未收敛。

## 仍未闭环的部分

当前仍不能宣布“全 app 每个页面 5 秒内真实已同步”：

- 尚未取得生产管理员 token/cookie，本阶段没有登录态 HTTP p95 生产数据。
- 真实写操作链路仍需单独验收：关联配对、撤回、银行导入确认、发票导入确认、设置/规则变更、OA 同步影响链路。
- Stage 3 的 direct-scope smoke 证明的是 worker/readiness 能收敛，不证明每个 writer 都正确生成 durable dirty
  source_version 和 outbox scope。
- 前端“秒开 fresh snapshot，后台增量追赶”仍需确认所有操作按钮都以权限、版本、read model status 和 audit 为准；
  页面可以先显示最近 fresh snapshot，但会改变业务状态的操作不能绕过权限、审计、版本冲突和后端真实 freshness。

## 下一阶段

1. 取得管理员 token/cookie 后运行生产 HTTP SLO probe，保存 JSON，并把每个失败/超时 probe 归类为权限、网络、SQL、
   read model stale、cache miss 或前端路由问题。
2. 对超出 1 秒的 API 使用 `/health.api_performance`、`pg_stat_statements` 和
   `EXPLAIN (ANALYZE, BUFFERS)` 定位；优先索引/SQL/read model payload 优化，不先引入 Kafka。
3. 建立写操作链路 smoke：每个操作必须记录 writer 事务、dirty source_version、outbox event、worker completion、
   readiness fresh、页面/API fresh 和 audit record。
4. 若所有 HTTP probe 均通过但写链路不通过，优先修 writer scope contract 或 ReadModelRefreshGateway 调用点。
5. 只有当 HTTP、read model smoke、写操作链路和 App Status 均通过，才能把目标状态从“Stage 4 coverage ready”
   改为“全 app 完美闭环”。
