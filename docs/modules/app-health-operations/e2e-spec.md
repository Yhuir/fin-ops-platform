# 系统状态 Spec-first E2E Spec

本文件定义 `/operations/app-health` 页面在真实浏览器中的业务验收合同。测试必须保护 admin-only 运维 dashboard、App Status 全局事实、read model/worker/queue 可见性、权限 gate、健康 API/polling/ready contract 和真实基础设施风险边界，而不是保护当前组件实现细节。

## 模块目标

系统状态页面是只读运行事实 plane。它展示后端 `app_status`、runtime monitoring、read model readiness、dirty scopes、outbox、background jobs、dependencies、alerts 和 dashboard metrics。前端不能用当前 route、表格 loading 或组件本地状态推导 green/yellow/red；有界轮询只负责刷新 UI，不替代 durable facts。

## 用户角色

- `admin`：可进入 `/operations/app-health` 并读取只读 dashboard。
- `full_access` / `read_export_only`：可使用业务页面和全局状态提示，但不能读取 admin-only operations dashboard。
- forbidden/expired session：不能进入受保护 shell 或调用 dashboard API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `APP-HEALTH-E2E-001` | admin shell 和 dashboard ready | P0 | admin 进入 `/operations/app-health` 后显示主导航、系统状态 active link、`AppHealth 运维状态` 标题、数据/请求/后台指标区和刷新按钮，并调用 dashboard API。 |
| `APP-HEALTH-E2E-002` | dashboard admin-only gate | P0 | `read_export_only` 用户进入 route 时显示无管理员权限提示，不渲染 dashboard 数据区，也不调用 `/api/operations/app-health-dashboard`。 |
| `APP-HEALTH-E2E-003` | forbidden/expired session gate | P0 | forbidden session 显示无权访问，expired session 显示 OA 会话失效；两者都不渲染 dashboard，也不调用 protected dashboard API。 |
| `APP-HEALTH-E2E-004` | Browser runtime error safety | P0 | admin/read-only/forbidden/expired 四条浏览器路径均不得出现隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog。 |
| `APP-HEALTH-E2E-005` | App Status overview 优先级 | P0 | 后端必须按 session、background jobs、readiness、dirty scopes、outbox、worker heartbeat、dependencies 和 alerts 推导 green/yellow/red；malformed/runtime unavailable/missing readiness 不能默认 green。 |
| `APP-HEALTH-E2E-006` | read model/worker/queue dashboard 事实 | P0 | dashboard/API 必须展示 read model readiness、dirty scopes/outbox、required worker、RabbitMQ/API metrics 和 bounded slow endpoints；左上角 App Status hover 必须展示 read model、worker、queue 整体摘要；unknown 显示 `--`，不能默认为 0。 |
| `APP-HEALTH-E2E-007` | health/ready/HTTP SLO gate | P0 | `/health/ready` payload 必须轻量 bounded；authenticated HTTP probes 拿到 HTML fallback 或零样本必须失败，health-ready probe 和 API SLO 是 runtime closure 必经检查。 |
| `APP-HEALTH-E2E-008` | registry completeness | P0 | 新增页面、read model、worker、job type 或 dependency 必须同步 registry 和测试；缺 registry 不能让状态 plane 漏报。 |
| `APP-HEALTH-E2E-009` | dashboard stale/error behavior | P1 | dashboard refresh 失败时保留上一份 payload 并显示 stale/warning，不把失败状态显示为 fresh；App Status icon 不因 route 切换改变状态。 |
| `APP-HEALTH-E2E-010` | 真实基础设施 runtime closure | P1 | 真实 PostgreSQL/RabbitMQ/Redis/systemd/Nginx/OA iframe 环境下，worker heartbeat、queue backlog、read model readiness、polling API、ready payload、大库 metrics 和 write-operation SLO 都必须有真实证据；该项必须在 staging/runtime smoke 验证。 |
| `APP-HEALTH-E2E-011` | admin 只读 Audit 响应合同 | P0 | admin 点击进项发票使用 Audit 后只发送 GET；结构化 `audit_status` 全部通过时显示 pass 和 `Blocking samples`，不得继续显示旧的精确问题数文案，也不得产生 refresh/mutation 请求。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker heartbeat、queue backlog、DLQ、readiness convergence 和 write-operation SLO。
- 真实 Nginx/OA iframe 下 polling API 的认证、超时、fallback 与跨域行为。
- 真实大库 dashboard metrics、`pg_stat_statements`、short TTL cache 和 API performance 长尾。
- 真实生产 `/health/ready`、authenticated HTTP probe 和 controlled write-operation E2E。
