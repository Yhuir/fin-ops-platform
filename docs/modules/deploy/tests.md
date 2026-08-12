# 部署 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 当前入口 | 必测原因 |
| --- | --- | --- |
| Nightly CI | `.github/workflows/nightly-ci.yml`、`scripts/verify.sh` | 防止 solo 开发漏跑后端、前端、browser e2e、build 和 docs |
| Release deploy script | `scripts/deploy_oa.py`、`scripts/deploy-oa.sh` | 发布顺序、storage preflight、helper contract、readiness/public route smoke 不能漂移 |
| Deploy control helper | `deploy/oa/bin/finops-deploy-control.sh` | root-owned helper 负责 migration、drop-in、restart、readiness 和 cleanup |
| Worker ensure helper | `deploy/oa/bin/finops-ensure-runtime-workers.sh` | required worker 矩阵必须来自 registry/manifest，不维护第二份清单 |
| Runtime worker registry | `runtime_worker_registry.py`、`runtime_worker_manifest.py` | worker/env/event/heartbeat/App Health 必须同步 |
| Nginx 同域路径 | `deploy/oa/nginx.fin-ops.conf.example` | `/fin-ops/` SPA 和 `/fin-ops-api/`、`/fin-ops/api/` API proxy 不能互相吞路由 |
| Health/readiness | `/health`、`/health/ready` | release 激活后必须等 API 和 required workers ready |
| Runtime env/secrets | `deploy/oa/env/*.example`、systemd drop-ins | DSN、secrets、migrator env、RabbitMQ/Redis/OA env 不能泄露或错用 |
| Backup/rollback | operations docs、deploy helper cleanup/active refs | 本地只能保护脚本契约；真实备份恢复要 staging/生产 runbook |

## 场景覆盖清单

| 场景 | 覆盖入口 | 状态 |
| --- | --- | --- |
| nightly 支持手动、定时、main push，并运行 `bash scripts/verify.sh all` | `tests/test_nightly_ci.py` | 2026-06-11 新增 |
| `verify.sh all` 先运行锁定生产依赖安全审计，再运行 clean app check、全量 unittest、前端 Vitest/build、Playwright browser smoke、docs check；`check-release` 在隔离 venv 重跑审计，且 clean app check 不读取本地 legacy app Mongo | `tests/test_nightly_ci.py`、`tests/test_deploy_oa_script.py` | 2026-08-09 更新 |
| `verify.sh docs` 检查 Spec-first E2E 全局文档和每个模块的 `e2e-spec.md` / `e2e-coverage.md`；backend unittest 检查模块索引、inventory 和 Spec ID 映射 | `tests/test_nightly_ci.py`、`tests/test_spec_first_e2e_docs.py` | 2026-06-19 新增 |
| 当前配置 runtime app check 必须显式使用 `verify.sh runtime-check`，避免把 legacy app Mongo 数据问题混入 clean CI 门禁 | `tests/test_nightly_ci.py` | 2026-06-11 新增 |
| release remote script 使用 versioned release、deploy-control、worker ensure、storage preflight、cleanup | `tests/test_deploy_oa_script.py` | 已覆盖 |
| release metadata 绑定 migration count/head/fingerprint；pending migration 在 stop 前要求 exact previous-code/candidate-schema evidence；迁移后回滚复用同一证据，缺失时 maintenance + forward repair | `tests/test_deploy_oa_script.py::test_release_archive_accepts_frontend_assets_under_configured_base_path`、`test_release_gate_blocks_unproven_schema_rollback_before_services_stop` | 2026-08-09 新增 |
| 候选 gate 读取旧 stable system audit 时，以候选 registry + summary + 完整逐页 proof 严格验真；部分 registry 字段、漏页和顺序漂移失败关闭 | `tests/test_write_operation_e2e_smoke.py` | 2026-07-31 更新 |
| 旧 stable HTTP 审计仅因旧页面审计实现失败时，候选 gate 用候选代码执行同库只读审计；HTTP 鉴权、transport 或 payload contract 失败不得触发该路径 | `tests/test_runtime_sync_closure_gate.py` | 2026-08-08 更新 |
| runtime convergence 先协调 terminal publish 并取得干净样本，canonical audit 最后执行 | `tests/test_runtime_sync_closure_gate.py` | 2026-07-31 更新 |
| release 激活后先等 `/health/ready`，再检查公网 session API route JSON proxy | `tests/test_deploy_oa_script.py` | 已覆盖 |
| no-activate 只上传和校验，不激活、不清理、不启动 worker ensure | `tests/test_deploy_oa_script.py` | 已覆盖 |
| legacy-current 覆盖式发布入口已移除，CLI 不接受 `--mode` 且脚本无 legacy archive/remote script | `tests/test_deploy_oa_script.py` | 已覆盖 |
| deploy-control helper 使用 `/etc/fin-ops` secret contract、migration env、drop-in reset、worker readiness | `tests/test_deploy_oa_script.py` | 已覆盖 |
| exact candidate 自动分类 frontend/runtime/ACL，普通发布只读取 005，ACL 自动要求专项 preflight | `tests/test_deploy_oa_script.py::test_release_gate_profile_is_automatic_and_fail_safe`、`test_frontend_release_gate_is_005_only_and_skips_runtime_audits` | 2026-08-03 新增 |
| 纯前端门禁只执行 pre/T+0 ready/session/dist/shell/asset，不运行 RabbitMQ apply、runtime closure、page audit 或 T+60/T+300 | `tests/test_deploy_oa_script.py::test_frontend_release_gate_is_005_only_and_skips_runtime_audits` | 2026-08-03 新增 |
| 一次性 retired env/OA binding cutover 已退出稳态链并删除历史 SQL | `tests/test_deploy_oa_script.py::test_release_gate_steady_state_rejects_retired_env_without_rewriting_files`、`test_retired_role_binding_cleanup_is_deleted_and_user_sync_stays_member_scoped` | 2026-08-03 新增 |
| runtime worker ensure 从 manifest 派生 required workers/env/check command | `tests/test_deploy_oa_script.py`、`tests/test_runtime_worker_registry.py` | 已覆盖 |
| Workbench direct cutover 在 stop 前保存 exact page-worker env；previous rollback 在 ensure/start 前恢复且禁止 example fallback/迁移；backup 仅在 candidate final evidence 或 rollback checkpoint PASS 后删除 | `tests/test_deploy_oa_script.py::test_workbench_page_worker_env_backup_restores_exact_bytes_without_secret_output`、`test_runtime_worker_helper_refuses_example_fallback_for_required_restored_env`、`tests/test_deploy_runtime_examples.py::test_workbench_page_worker_env_has_exact_cutover_and_rollback_lifecycle` | 2026-08-13 新增 |
| Nginx SPA fallback、assets 404/cache、index no-store、API proxy 顺序 | `tests/test_deploy_oa_nginx_config.py` | 已覆盖 |
| RabbitMQ dispatcher/env examples 覆盖 registry events | `tests/test_deploy_runtime_examples.py`、`tests/test_runtime_worker_registry.py` | 已覆盖 |
| `/health/ready` 不执行重 self-test，暴露 runtime infrastructure contract | `tests/test_app.py`、`tests/test_app_postgres_mode.py` | 已覆盖 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 | 缺口等级 | 维护要求 |
| --- | --- | --- | --- | --- | --- |
| 1. Business core unit tests | 不直接适用 | N/A | deploy 模块没有业务金额/状态规则；核心规则是脚本/环境契约 | N/A | 若新增发布策略算法或 release retention 规则，补脚本级 unit tests |
| 2. Service-layer tests | 适用 | `tests/test_deploy_oa_script.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py` | 覆盖 deploy helper、worker registry、env examples、RabbitMQ dispatch contract | 无 P0 | 修改 helper/systemd/env/worker manifest 时必须补 |
| 3. API contract tests | 间接适用 | `tests/test_app.py`、`tests/test_app_postgres_mode.py`、`tests/test_deploy_oa_script.py` | 覆盖 `/health/ready` 和 session route proxy smoke 脚本契约 | 无 P0 | 修改 health/session/Nginx path 时补 route contract |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 worker manifest、read model event、RabbitMQ dispatcher env、runtime boundary | P1 | 真 systemd/RabbitMQ/Redis/worker drain 需要 staging |
| 5. Frontend component and interaction tests | 间接适用 | `scripts/verify.sh frontend`、`scripts/verify.sh e2e`、nightly CI | deploy 不改页面；通过全量 Vitest/build 和 Playwright app shell smoke 防旧页面破坏 | P1 | 更多真实浏览器/OA iframe/缓存刷新需 smoke |
| 6. End-to-end business-flow integration tests | 适用但本地有限 | deploy release script tests + health tests | 覆盖发布脚本顺序，不执行真实 SSH/systemd/migration | P1 | 真实 release -> migration -> restart -> worker ready -> App Health 绿灯需 staging/生产前 smoke |
| 7. Existing feature regression tests | 适用 | `scripts/verify.sh all`、nightly CI、全量测试 | 保证部署/CI 改动不会漏跑旧模块测试，并防止开发机 legacy app Mongo 旧状态破坏 clean 回归入口 | 无 P0 | 改验证入口时必须保护 backend/frontend/browser e2e/docs 都仍被 all 覆盖 |

## 历史 bug 回归库

| 日期 | 失败模式 | 回归测试 | 验证 |
| --- | --- | --- | --- |
| 2026-08-13 | Workbench direct cutover 删除 live page-worker env 后，previous rollback 的 ensure 可能从 example 重建默认 env，丢失生产 transport/tuning 并导致 queue consumer closure 失败；若安装 previous 旧 helper，还会丢失 exact-env guard | `test_workbench_page_worker_env_backup_restores_exact_bytes_without_secret_output`、`test_runtime_worker_helper_refuses_example_fallback_for_required_restored_env`、`test_workbench_page_worker_env_has_exact_cutover_and_rollback_lifecycle` | `bash -n deploy/oa/bin/finops-deploy-control.sh && bash -n deploy/oa/bin/finops-ensure-runtime-workers.sh`；`PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_deploy_runtime_examples.py tests/test_deploy_oa_script.py tests/test_runtime_worker_registry.py tests/test_runtime_queue.py tests/test_runtime_monitoring.py tests/test_rabbitmq_runtime.py` |
| 2026-08-13 | 默认 HTTP 门禁只读 paired groups，且 page worker 停止后的 T+0/T+60/T+300 没有动态证明旧 event/scope、projection table/statement 零增量，也没有绑定 candidate commit 的 Redis page-cache source/runtime-owner 缺席证据 | `test_default_workbench_probes_are_unique_direct_canonical_reads`、`test_release_gate_proves_retired_workbench_page_runtime_zero_delta_across_candidate_window`、`test_retired_workbench_page_runtime_window_not_required_evidence_is_executable`、`test_retired_workbench_page_runtime_observer_passes_zero_delta_and_rejects_drift` | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_http_slo_probe.py tests/test_deploy_runtime_examples.py tests/test_deploy_oa_script.py`；`bash -n deploy/oa/bin/finops-deploy-control.sh` |
| 2026-08-03 | 一次性 005/006 ACL cutover 被硬编码进每次发布，导致普通功能也要求 006、写 env/OA、等待 T+300 | `test_release_gate_profile_is_automatic_and_fail_safe`、`test_frontend_release_gate_is_005_only_and_skips_runtime_audits`、`test_release_gate_auto_escalates_acl_without_requiring_006` | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script -v`；`bash -n deploy/oa/bin/finops-deploy-control.sh` |
| 2026-08-09 | forward-only migration 后自动回滚只切换旧 binary、不回退 schema，可能形成旧代码 + 新 schema 并把失败误报为恢复成功 | `test_release_gate_blocks_unproven_schema_rollback_before_services_stop`、release metadata schema contract assertions | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script -v`；`bash -n deploy/oa/bin/finops-deploy-control.sh` |
| 2026-08-05 | 通用 Settings service/store/repository 被误列入 ACL hash，且 ACL 标准激活仍强制消费 005/006 artifact | `test_release_gate_auto_escalates_acl_without_requiring_006`、`test_release_gate_profile_is_automatic_and_fail_safe`、`test_frontend_release_gate_is_005_only_and_skips_runtime_audits` | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script -v`；`bash -n deploy/oa/bin/finops-deploy-control.sh` |
| 2026-08-03 | frontend 激活先 stop workers，却在 stop 后只遍历 active workers 重启，导致候选和自动回退都遗留全部 required workers inactive | `tests.test_deploy_runtime_examples.DeployRuntimeExampleTests.test_frontend_activation_restarts_the_workers_captured_before_stop` | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_runtime_examples -v`；`bash -n deploy/oa/bin/finops-deploy-control.sh`；生产 frontend profile T+0 inventory |
| 2026-08-02 | ACL preflight 无条件要求 006 带 OA 菜单权限，导致合法的 steady/forward-repair `denied + no permission` 被阻断；post-deploy 又同时要求 denied/router 不可见，形成自相矛盾的初始契约 | `test_representative_bearer_requires_exact_identity_and_phase_matched_permission`、`test_post_deploy_role_matrix_restores_bearer_and_emits_redacted_evidence`、`test_post_deploy_rejects_initial_denied_bearer_with_oa_menu_permission` | `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_access_control_preflight -v` |
| 2026-08-02 | 0132 将 protected admin 追加到 `allowed_usernames` 尾部，违反应用 canonical 顺序并导致候选 page audit 失败；若 preflight 仍只查 0132 会误判 steady | `test_settings_access_control_canonical_order_repairs_0132_append_bug`、`SettingsAccessControlPostgresIntegrationTests.test_0133_repairs_0132_order_and_enforces_exact_acl_shape`、`test_database_guard_only_fails_closed_until_0133_check_is_validated` | `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_settings_access_control_preflight -v`；`FIN_OPS_TEST_DATABASE_URL=<disposable> bash scripts/verify.sh settings-acl-postgres` |
| 2026-06-11 | nightly workflow 或 `verify.sh all` 被改坏后漏跑后端/前端/docs，导致远端 CI 失去门禁价值 | `tests/test_nightly_ci.py` | `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v` |
| 2026-06-17 | nightly workflow 或 `verify.sh all` 被改坏后漏跑 deterministic Playwright browser smoke，导致真实浏览器 gate 失去保护 | `tests/test_nightly_ci.py`、`web/e2e/app-shell.spec.ts` | `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`cd web && npm run e2e:smoke` |
| 2026-06-19 | 新增模块后漏建 `e2e-spec.md` / `e2e-coverage.md`，或 Spec ID 没有 coverage 映射，导致 Spec-first E2E Audit 看似完整但后续 controller 无法追踪缺口 | `tests/test_spec_first_e2e_docs.py`、`tests/test_nightly_ci.py`、`bash scripts/verify.sh docs` | `PYTHONPATH=backend/src python3 -m unittest tests.test_spec_first_e2e_docs tests.test_nightly_ci -v`；`bash scripts/verify.sh docs` |
| 2026-06-11 | `verify.sh all` 读取本地 `.runtime/fin_ops_platform/app_mongo_config.json`，legacy ETC pickle 因旧字段/slots 变化反序列化失败，导致 clean 代码回归被本地历史状态阻塞 | `test_backend_verification_uses_clean_app_state_by_default`、`test_runtime_check_is_explicit_opt_in_for_current_runtime_state` | `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v` |
| 既有 | deploy-control helper 使用旧 `/root` env、未加载 secrets、未 reset EnvironmentFile、未校验 OA env | `test_deploy_control_script_uses_canonical_etc_finops_secret_contract` | 模块后端验证 |
| 既有 | release 激活后未等待 `/health/ready` 就检查公网 route | `test_release_remote_script_waits_for_backend_before_public_route_smoke` | 模块后端验证 |
| 既有 | Nginx 把 `/fin-ops/api/*` 吃成 SPA index.html | `test_fin_ops_relative_api_routes_do_not_fall_back_to_index_html` | 模块后端验证 |
| 既有 | required worker 清单在 deploy helper 中硬编码，新增 worker 后生产漏启 | `test_required_workers_match_deploy_helper_defaults`、`test_manifest_cli_lists_required_instances_and_env_examples` | 模块后端验证 |
| 2026-07-05 | `legacy-current` 覆盖式发布、旧单文件 env 模板或 systemd 示例 current/backend 路径继续污染 release-based I/O | `test_legacy_current_deploy_mode_is_removed`、`test_systemd_examples_do_not_pin_retired_current_backend_path`、`test_runtime_env_examples_pin_standard_write_operation_smoke_inputs`、deploy runtime template guards | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_deploy_runtime_examples tests.test_platform_runtime_boundary_guards -v` |
| 2026-07-23 | 普通写响应显式返回 `outbox_event_ids: []`，runner 把空 receipt 当成缺失并错误要求 durable Workbench idempotency record；共享变量还可能把上一 checkpoint receipt 带入下一步 | `test_write_step_preserves_explicit_zero_fanout_receipt`、`test_zero_fanout_receipt_skips_durable_lookup_and_does_not_leak_to_next_checkpoint` | `PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_e2e_smoke -v` |
| 2026-07-26 | 生产 helper 不能把 bounded preview sample count 传给 runner，且 `/tmp`-only policy 拒绝固定 root-owned 标准 scenario | `test_deploy_control_script_uses_canonical_etc_finops_secret_contract`、`test_deploy_control_write_operation_runner_refuses_untrusted_scenario_path` | `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_write_operation_e2e_smoke -v` |
| 2026-07-26 | `bank_oa_invoice` runner 把每个 Cost probe 都强制为 `project_scope=active`，导致关联写后 `all:YYYY-MM` 无法按访问收敛，System Audit 固定停在 15/16 | `test_bank_oa_relation_impact_cost_probe_requires_active_project_scope`、`test_bank_oa_relation_impact_cost_probe_allows_additional_all_scope_for_system_audit` | `PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_e2e_smoke -v` |

## 关键 smoke flows

- Nightly smoke：手动触发 GitHub Actions `Nightly CI`，确认 checkout、pip install、npm ci、Playwright Chromium install、`bash scripts/verify.sh all` 成功；该入口使用 clean app state，不读取本地 legacy app Mongo。
- Runtime smoke：需要验证当前机器或服务器 runtime 状态时显式运行 `bash scripts/verify.sh runtime-check`，再结合 `/health`、worker 和关键页面 smoke 判断迁移残留。
- Release dry-run：`./scripts/deploy-oa.sh --dry-run --no-activate --allow-dirty`，检查远端命令不执行激活但包含 release layout/check-release/storage preflight。
- Staging release：上传 release -> check-release -> auto profile -> profile-specific pre -> activate -> `/health/ready` ready -> 005 admin session -> worker readiness zero missing/stale/mismatch；frontend 到 T+0 结束，runtime/ACL 继续 T+60/T+300。
- Nginx smoke：刷新 `/fin-ops/`、深链 route、hashed assets、`/fin-ops-api/api/session/me`、`/fin-ops/api/session/me`。
- Worker smoke：required worker instances 来自 manifest；systemd active；App Health 无 missing/stale/mismatch worker；dirty scope backlog 不增长。
- Rollback smoke：切回上一个 release 或恢复备份，确认 frontend hash、API release identity、worker drop-in 和 App Health 收敛。

## 模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_deploy_oa_script \
  tests.test_deploy_oa_nginx_config \
  tests.test_nightly_ci \
  tests.test_deploy_runtime_examples \
  tests.test_runtime_worker_registry \
  tests.test_app \
  tests.test_app_postgres_mode \
  tests.test_spec_first_e2e_docs \
-v

cd web && npm run e2e:smoke

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

- nightly 调用 `bash scripts/verify.sh all`，覆盖全量后端 unittest、前端 Vitest、前端 build、Playwright browser smoke 和 docs。
- `tests/test_nightly_ci.py` 保护 workflow 和 verify script 不被改成漏跑。
- `scripts/verify.sh backend` / `all` 使用临时 `FIN_OPS_DATA_DIR` 做 clean app check；`runtime-check` 才读取当前配置 runtime。
- nightly 仍不能证明真实 SSH、sudo、systemd、PostgreSQL migration、Redis/RabbitMQ、Nginx live config 和 OA cookie 行为。

## 未测风险

- 真实服务器 SSH/sudo 权限、root-owned helper 安装、systemd drop-in、worker restart 和 journal 日志只靠 staging/生产前 smoke。
- PostgreSQL migration、备份/PITR、对象存储、Redis/RabbitMQ 真连接和大生产库 worker drain 不由本地 unittest 证明。
- Nginx live config 可能与仓库 example 偏离，必须在服务器上 `nginx -T` 或实际 route smoke。
- GitHub Actions 是否在远端仓库启用、secret/cache 配置和权限需要在 GitHub 侧确认。
- 浏览器真实缓存、OA iframe cookie、下载和移动端布局仍由真实浏览器 smoke 覆盖。
