# 部署 状态机

> 修改 `部署` 相关 CI、发布、运行时、read model 或 worker 状态前必须读取本文件。

## CI / 验证状态

| 状态 | 事实源 | 说明 |
| --- | --- | --- |
| `local_verify_pending` | 开发者本地 | 改动后尚未运行目标验证 |
| `local_verify_failed` | `scripts/verify.sh` 或模块命令退出非 0 | 不允许标记模块闭环；必须修复或记录 documented-risk |
| `local_verify_succeeded` | 本地命令退出 0 | 只能证明本地自动化范围 |
| `nightly_queued` | GitHub Actions schedule/workflow_dispatch/push | 远端 CI 已排队，不代表通过 |
| `nightly_running` | GitHub Actions job | 正在安装依赖和运行 `bash scripts/verify.sh all` |
| `nightly_failed` | GitHub Actions job failed | 必须分类为真实 bug、测试不稳定、外部环境缺失或契约变化 |
| `nightly_succeeded` | GitHub Actions job succeeded | 证明后端 unittest、前端 Vitest/build、Playwright browser smoke、docs 在远端环境通过 |

## Release 状态

| 状态 | 事实源 | 说明 |
| --- | --- | --- |
| `package_pending` | `scripts/deploy_oa.py` | 还未构建/打包 release |
| `package_built` | 本地 `web/dist` + release tar + `RELEASE.json` | 包含 backend、web/dist、scripts、deploy/oa |
| `upload_pending` | SSH remote script | 还未写入 `/opt/fin-ops/releases/<release>` |
| `release_uploaded` | 远端 release dir | 已上传但未激活，可 `--no-activate` 停在此状态 |
| `check_release_failed` | `finops-deploy-control check-release` | release layout/env contract 不满足，禁止激活 |
| `profile_classified` | `release-gate-profile` | 自动得到 `frontend` / `runtime` / `acl`；无法证明 pure frontend 时为 runtime，ACL boundary drift 优先为 acl |
| `acl_profile_classified` | profile=`acl` | 直接鉴权/权限、OA role sync 或 ACL migration 发生变化；仍使用 005-only 标准门禁，失败后只允许 forward repair |
| `schema_plan_verified` | `schema-compatibility-plan` | `RELEASE.json` migration fingerprint 与包内 migration 一致，生产 applied schema 不领先且 checksum 无未知漂移 |
| `schema_compatibility_blocked` | pending migration 且 exact compatibility evidence 缺失/漂移 | 在服务停止和 migration 前失败；生产 runtime/schema 均不变 |
| `preflight_succeeded` | profile-specific pre checkpoint | frontend 证明 ready/005/shell/asset/dist；runtime/acl 证明完整 runtime closure |
| `migration_running` | runtime/acl activation | 正在用 migrator env 执行 PostgreSQL migration；frontend 不进入此状态 |
| `migration_failed` | migration command non-zero | 禁止继续发布；需要恢复/修复 schema 状态 |
| `activation_running` | systemd drop-in/frontend publish/restart | 正在切换 API/worker/frontend |
| `backend_ready` | `GET /health/ready status=ready` | API release readiness 通过 |
| `workers_ready` | `/health.runtime_infrastructure` | required workers missing/stale/mismatch 全为 0 |
| `public_routes_ready` | 公网 `/fin-ops-api/api/session/me`、`/fin-ops/api/session/me` | 未登录时应返回 JSON 401，不应返回 SPA HTML |
| `frontend_t0_verified` | frontend T+0 evidence | active release、published dist、ready、005 session、公开 shell/asset 和 required workers 全通过；无需 T+60/T+300 |
| `runtime_t300_verified` | runtime/acl evidence | pre、T+0、T+60、T+300 queue/read-model/audit 均稳定 |
| `release_succeeded` | deploy script 退出 0 | 发布脚本范围完成；仍需业务 smoke |
| `release_failed` | deploy trap step + exit code | 输出失败 step；不能吞错 |
| `rollback_needed` | migration/activation/readiness/public route/业务 smoke 失败 | 只有 schema 未变化，或 exact previous 已通过 candidate schema（含全部中间 head）写入证据，才可自动切回；否则 maintenance + forward repair |
| `rollback_done` | active release、frontend、API、workers、App Health 收敛 | 回滚完成后仍需验证数据和 worker 状态 |

## 禁止流转

- `check_release_failed` / `migration_failed` -> `activation_running`。
- pending migration 未通过 exact previous-code/candidate-schema evidence -> `migration_running`。
- schema 已前移但兼容证据缺失/漂移 -> `rollback_done`；必须保持 maintenance，不得把旧 binary 启动或声称恢复成功。
- systemd active 但 `/health/ready` 未 ready 时标记 release succeeded。
- required worker missing/stale/mismatch 非 0 时标记 workers ready。
- `/fin-ops/api/*` 被 SPA fallback 返回 HTML 时标记 public routes ready。
- API/worker unit 直接加载 migrator env 或旧 `/root` runtime env。
- `scripts/deploy-oa.sh` 恢复 `--mode legacy-current` 或覆盖 `/opt/fin-ops/current/backend` 的发布流。
- deploy helper 维护硬编码 worker 清单，绕过 `runtime_worker_manifest`。
- 操作者手工指定/降级 profile，或任何标准发布读取 006 token。
- 在稳态发布中恢复 retired env rewrite、OA historical binding cleanup/rollback 或已删除 SQL。
- 通过删除测试、skip、放松断言让 nightly 变绿。

## UI 状态

本模块没有独立业务 UI，但影响全局用户体验：

| UI 状态 | 触发 | 要求 |
| --- | --- | --- |
| loading | 新 release 重启、worker 切换、read model refreshing | App Status 或页面 loading/stale 必须来自真实 runtime/readiness |
| empty | 新 release 后页面 fresh 且 rows 为空 | 不能由旧 cache/read model 缺失伪装 |
| error | API 500/403/session failed/worker failed | 页面显示真实错误或权限状态，不应被 Nginx fallback 成 index.html |
| stale/refreshing | migration 或 worker 后 read model 重建 | App Status yellow/busy，页面不得把旧数据标 fresh |
| permission disabled/hidden | OA cookie/session/role sync 改变 | `/api/session/me` JSON 契约和 app 内权限仍是最终判断 |

## Read Model / Worker 状态

| 状态 | 来源 | 要求 |
| --- | --- | --- |
| `fresh` | readiness/source version + no active dirty scope | 发布后只有真实 worker/projection 证明 fresh 才能 green |
| `missing` | worker 未注册、readiness 缺失、projection 缺表 | App Health missing；需要 migration/worker/env 修复 |
| `refreshing` | dirty scope pending/processing | 发布后允许短暂 yellow，但需要 drain |
| `stale` | worker heartbeat stale、source/schema mismatch | App Health busy/blocked；禁止忽略 |
| `failed` | worker/job/dirty scope failed | 进入 App Health attention；需要 inspect/retry/repair |
| `unavailable` | PostgreSQL/Redis/RabbitMQ/OA/Nginx 不可用 | 部署 smoke 失败，按 dependency 排障 |

## 失败恢复

1. 先看 remote deploy step 和 exit code，定位失败在 packaging、upload、check-release、migration、activation、readiness、public route 还是 cleanup。
2. 读取 `finops-deploy-control status`、systemd status/journal、`/health`、`/health/ready`、App Health dashboard。
3. 如果是 worker readiness，优先检查 worker manifest/env example/systemd instance/heartbeat/event type mismatch。
4. 如果是 Nginx route，检查仓库 example 和服务器 `nginx -T` 是否一致。
5. 如果 migration 或数据风险，先 staging restore 验证，再决定 PITR/rollback/repair。
6. 回滚后验证 frontend hash、API release identity、required workers、public session route 和关键页面 smoke。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐 deploy 状态机 | 明确 CI、release、migration、readiness、worker、public route 和 rollback 状态 | 待本轮模块验证 |
| 2026-07-05 | 移除 `legacy-current` 覆盖式发布入口和旧单文件 env 模板 | 发布状态机只保留 versioned release；legacy current 仅可作为 activate 清理对象 | `tests.test_deploy_oa_script`、`tests.test_deploy_runtime_examples`、`tests.test_platform_runtime_boundary_guards` |
| 2026-08-03 | 自动风险分级并拆分 frontend/runtime/ACL 门禁 | 普通发布只验证 005；纯前端走 pre/T+0 快速门；ACL 变更自动升级双身份专项门禁；一次性 env/OA cleanup 退出运行链 | `tests.test_deploy_oa_script`、`bash -n deploy/oa/bin/finops-deploy-control.sh` |
| 2026-08-05 | 标准发布统一为 005-only，并收窄 ACL 自动分类边界 | 通用 Settings service/store/repository 变更归入 runtime；005/006 双身份工具保留为显式专项验收，不再阻断激活 | `test_release_gate_auto_escalates_acl_without_requiring_006`、`test_release_gate_profile_is_automatic_and_fail_safe` |
