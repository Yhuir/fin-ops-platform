# 部署 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 生产发布入口保持 `./scripts/deploy-oa.sh`，只走 release-based 部署；`legacy-current` 覆盖式部署入口已经移除。
- Nightly CI 的唯一全量入口是 `bash scripts/verify.sh all`；它必须同时运行 clean app check、后端 unittest discovery、前端 Vitest、前端 build、deterministic Playwright browser smoke 和 docs check。clean app check 使用临时 `FIN_OPS_DATA_DIR`，不读取本地 legacy app Mongo；当前配置 runtime check 必须显式运行 `bash scripts/verify.sh runtime-check`。
- deploy-control helper 必须使用 `/etc/fin-ops/fin-ops.common.env`、`fin-ops.secrets.env` 和 migration-only env；API/worker 不允许直接加载 migrator env 或旧 `/root` env。
- required worker 矩阵从 `runtime_worker_manifest` / registry 派生；deploy runbook 和 helper 不维护第二份硬编码清单。
- 发布成功不能只看 systemd active；必须等 `/health/ready`、required worker readiness 和公网 session API JSON proxy。
- 本地自动化保护脚本、workflow、模板和 registry 契约；真实 SSH/sudo/systemd/PostgreSQL migration/Nginx live config/Redis/RabbitMQ/浏览器缓存必须由 staging 或生产前 smoke 证明。
- runtime env 事实源是 `deploy/oa/env/*.env.example` 和生产 `/etc/fin-ops/*` split env；旧单文件 `deploy/oa/fin_ops.env.example` 已移除。

## 历史记录

## 2026-07-24 - 写响应到页面可见的真实性能门禁

- 生产 round 8 暴露 runner 只检查最后一次 consumer GET 的 `target_ms`，却把 `operation_commit_to_visible_ms` 作为非阻断观测；因此 11–12 秒才 fresh 的页面仍可能被标记 pass。
- runner 现在用同一个 consumer `target_ms` 同时约束单次 fresh GET 与成功 mutation response 到首次 fresh/业务断言通过的总耗时，超限返回 `consumer_visibility_slo_miss`。不改变业务 API、queue、worker或页面，只修复生产验收 I/O 的真实性。

## 2026-07-23 - 受影响页面多 scope 生产验证边界

- Cost Statistics 正式页面使用 `project_scope=active`，同一 API 的 `project_scope=all` 仍是导出/后端合同；只访问其中一个 scope 不能证明另一个 scope 已收敛，也不能用运行时 sibling enqueue 伪造覆盖。
- write-operation runner 因此允许同一“受影响页面”最多两个明确 consumer scope probe，逐个执行正常 GET 和 fresh/business assertion；isolation 页面仍必须恰好一个 probe，第三个重复 scope fail fast。
- 该能力只属于 test-owned 生产验证输入，不修改应用 read model scope policy、query owner、写路径 target、worker、queue 或 Cost 精确访问语义，不引入 fan-out。

## 2026-07-23 - Write-operation zero-fan-out receipt 边界修复

- 生产 test-owned bank-turnover closure 中，confirm 与 recovery 均在 1 秒内返回 200/committed，业务 inverse 已恢复 inactive；runner 却因响应的 `outbox_event_ids: []` 被 truthy 判断丢失，继续强制查询 disabled-by-default durable idempotency 表并误报 `expected exactly one Workbench idempotency record`。
- 最小修复保留显式空 receipt：空列表代表本次普通写没有写后页面 refresh event；只有响应完全缺少 receipt 时才查询 durable record。每个 checkpoint 开始前清除内部 receipt 变量，禁止 confirm receipt 污染 withdraw/recovery。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`，不改变业务 API、canonical facts、read model、worker、queue 或生产 env；verification 继续用同一 test-owned fixture 复跑 confirm -> withdraw/recovery -> System Audit。
- 测试新增空 receipt 捕获和跨 checkpoint 隔离，覆盖显式零 fan-out跳过 durable lookup、下一 checkpoint receipt 缺失时仍准确查询 durable evidence。

## 2026-07-05 - 部署模块边界与 I/O close

- 目标：关闭部署模块旧 I/O 污染，确保发布入口、runtime env、worker/helper 合同只服务 release-based 链路。
- Grill-me 结论：`legacy-current` CLI 分支和 `deploy/oa/fin_ops.env.example` 都没有生产新链路必要性；`finops-deploy-control` 的 legacy current 归档是 release 激活清理，不是旧发布入口。
- Ponytail 决策：不新增兼容层、不保留隐藏 fallback，直接删除 `--mode legacy-current`、legacy remote script、legacy archive 和旧单文件 env 模板；systemd 示例和运维命令改为 active release 路径，不再指向 `/opt/fin-ops/current/backend`。
- 影响范围：`scripts/deploy_oa.py`、部署脚本测试、deploy runtime example/guard 测试、`deploy/oa/README.md`、`docs/operations/deployment.md`、部署模块文档和相关长期索引。
- 测试覆盖：`test_legacy_current_deploy_mode_is_removed` 保护 CLI/function/source 删除；runtime env tests/guards 只扫描 split env，并继续保护 PostgreSQL storage backend 和 write-operation smoke env。
- 未测风险：本地测试不执行真实 SSH/sudo/systemd/migration/Nginx live config；生产发布前仍需 staging 或生产前 release smoke。

## 2026-06-19 - Spec-first E2E docs guard

- 目标：防止后续新增模块时漏建 `e2e-spec.md` / `e2e-coverage.md`，或 Spec ID 没有 coverage 映射，导致全页面 Spec-first E2E controller 无法可靠推进。
- 影响范围：`scripts/verify.sh` 的 docs check、`tests/test_spec_first_e2e_docs.py`、`tests/test_nightly_ci.py`、`docs/dev/testing.md` 和本模块测试矩阵；不改变业务代码、部署脚本执行顺序、worker、Nginx 或 runtime env。
- 关键决策：`verify.sh docs` 保持轻量，只检查长期文档入口和每个模块的 Spec-first E2E 文件存在；更细的模块索引、全局 inventory 和 Spec ID -> coverage 映射由 backend unittest 保护，并进入 `verify.sh all`。
- 测试覆盖：新增 `tests/test_spec_first_e2e_docs.py`，覆盖所有 `docs/modules/*/README.md` 都有 `e2e-spec.md` / `e2e-coverage.md`、模块索引和目录一致、全局 inventory 提及每个模块、每个 `e2e-spec.md` 的 Spec ID 都映射到 `e2e-coverage.md`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_spec_first_e2e_docs -v`、`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`、`bash scripts/verify.sh docs`。
- 未测风险：该 guard 只保护文档入口和映射完整性，不证明每个 Spec 的真实业务行为已经自动化，也不替代 staging/runtime gates。

## 2026-06-19 - Write-operation E2E approval gate hotfix release

- 目标：把 `write_operation_e2e_smoke --apply` 与 `runtime_sync_closure_gate --apply-write-scenarios` 的审批闸门发布到生产，确保真实业务写 smoke 在缺少审批引用时无法误触 mutating HTTP。
- 影响范围：生产 active release、API/worker systemd drop-in、SLO/closure 工具；不改变业务 API、read model projection、worker handler、Nginx 或 env contract。
- 关键决策：继续使用临时干净 worktree，从生产基线 `codex/invoice-lifecycle-batch-hotfix` 创建 `codex/write-e2e-approval-gate-hotfix`，只提交 write-operation approval gate 工具代码和测试，避免带入主工作树其他 Spec-first E2E 未提交改动。release `main-33a150e7-write-e2e-approval-gate-20260619151922` 先 `--no-activate` 上传并通过 `check-release`，再用 root-owned `finops-deploy-control activate` 激活。
- 验收结果：激活后 `/health/ready` 返回 `status=ready`；API、RabbitMQ dispatcher 和 20 个 worker unit active，WorkingDirectory 指向 `main-33a150e7-write-e2e-approval-gate-20260619151922`。生产本机执行 minimal turnover scenario 的 `write_operation_e2e_smoke --apply` 但不带 approval，返回 exit code 2、`status=approval_missing`、`error=write_operation_e2e_requires_approval_ticket`、`scenario_count=1`、`approval_configured=false`；未执行业务写操作。发布后 critical `read_model_slo_smoke --critical-only --apply --target-ms 5000` 15/15 pass，summary p50 约 926.619ms、p95/max 约 4960.071ms；DB 汇总为 `job.outbox_events=done`、`job.read_model_dirty_scopes=done`、`read_model.app_status_readiness=fresh`。
- 测试覆盖：hotfix worktree 运行 `PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_p2p3_gate_result_classifier -v` 34 tests passed；`py_compile` 和 `git diff --check` 通过；前端 `/fin-ops/` build 通过，保留现有 CSS minify warnings。
- 未测风险：该 release 只证明审批闸门已经部署并能阻止缺 approval 的 apply；真实 write-operation closure 仍需业务批准、真实认证和受控 mutating scenario 样本。

## 2026-06-19 - Invoice lifecycle batch save hotfix release

- 目标：用正式 release-based 部署路径发布只包含 `invoice_lifecycle` read model rows batch save 的后端 hotfix，关闭生产 critical read model 5 秒 SLO 风险。
- 影响范围：生产 active release、API/worker systemd drop-in、read model critical apply gate；不改变 deploy 脚本、systemd 模板、Nginx 或 env contract。
- 关键决策：当前主工作树包含大量未完成 Spec-first E2E 改动，不能用 `--allow-dirty` 直接部署。采用临时干净 worktree `codex/invoice-lifecycle-batch-hotfix`，只提交 `read_models.py` 与对应 boundary test，构建 `/fin-ops/` 前端 dist，先 `--no-activate` 上传并通过 `check-release`，再用 root-owned `finops-deploy-control activate` 激活 release `main-99ea9b35-invoice-lifecycle-batch-20260619145710`。
- 验收结果：发布后 `/health/ready` ready，API、RabbitMQ dispatcher 和 20 个 worker 的 `WorkingDirectory` 均指向新 release；production critical `read_model_slo_smoke --critical-only --apply --target-ms 5000` 15/15 pass，summary p95/max 约 3.52 秒；DB 汇总为 outbox/dirty 全 `done`，readiness 全 `fresh`。
- 测试覆盖：发布前 hotfix worktree 运行 `pytest` invoice lifecycle/read model targeted tests 28 passed，`npm run build` 通过；生产 release 通过 deploy-control check-release、activate readiness、critical apply gate。
- 未测风险：这次 release 只证明 direct refresh worker drain 和该 hotfix 发布路径；真实业务写操作 profile 仍需有业务样本或 staging 场景继续审计。

## 2026-06-19 - RabbitMQ dispatcher import fact route

- 目标：让 release/env 示例与 runtime worker registry 保持一致，确保 RabbitMQ dispatcher 会发布 `import.fact.changed` wakeup。
- 影响范围：`deploy/oa/env/fin-ops.rabbitmq-dispatcher.env.example`、runtime worker manifest/registry 派生事件；不改变发布脚本、systemd 模板或 root-owned deploy helper 流程。
- 关键决策：`import.fact.changed` 仍以 PostgreSQL durable queue 为事实源，RabbitMQ 只负责 envelope/wakeup；dispatcher event list 必须包含该事件，否则生产 RabbitMQ transport 下 import worker 即使能 claim，也缺少正常 publish/consume wakeup。
- 文档影响：同步 runtime-workers 与 imports-invoices 实施记录。
- 测试覆盖：`tests/test_runtime_worker_registry.py` 覆盖 dispatcher env 示例包含 registry-derived RabbitMQ events。
- 未测风险：本地测试不连接真实 RabbitMQ；发布后需通过 worker check、queue backlog 和 App Status 观察真实 drain。

## 2026-06-11 - verify clean-state 回归修复

- 目标：修复 `bash scripts/verify.sh all` 因读取本地 legacy app Mongo 旧 ETC pickle 而失败的问题，让日常回归验证只验证代码和测试闭环。
- 根因：`fin_ops_platform.app.main --check` 默认读取 `.runtime/fin_ops_platform`；开发机残留 `app_mongo_config.json` 后会加载旧 app Mongo snapshot。旧 `EtcBusinessBatch` pickle 含已移除字段，当前 dataclass slots 无法接收，反序列化失败。
- 关键决策：`backend` / `all` 改为使用临时 `FIN_OPS_DATA_DIR` 运行 clean app check；当前配置 runtime 状态保留为显式 `runtime-check`。
- 测试覆盖：更新 `tests/test_nightly_ci.py`，保护 clean app check、backend/all 调用链和 `runtime-check` opt-in contract。
- 文档影响：更新 `docs/dev/nightly-ci.md`、`docs/dev/local-development.md`、`docs/dev/runtime-development.md`、`docs/operations/postgresql-runtime.md` 和本模块测试矩阵。
- 未测风险：clean-state 验证不证明真实 `.runtime`、生产 PostgreSQL 历史数据或 legacy app Mongo 退役状态；这些必须用 `runtime-check`、runtime smoke 和运维 runbook 验证。

## 2026-06-11 - 首轮 deploy 测试闭环

- 目标：审计 deploy/nightly CI/verify/deploy-oa/systemd/Nginx/env/worker manifest/DB migration/backup rollback/App Health smoke 的测试闭环。
- 影响范围：`.github/workflows/nightly-ci.yml`、`scripts/verify.sh`、`scripts/deploy_oa.py`、`deploy/oa/bin/*`、systemd/env/Nginx templates、runtime worker registry、health/readiness routes。
- 关键决策：新增 CI contract test，避免 nightly workflow 或 `verify.sh all` 被改成漏跑后端、前端、browser e2e、build 或 docs。
- 文档影响：补齐 `README.md`、`tests.md`、`state-machine.md`，并更新全局依赖地图和测试闭环状态。
- 测试覆盖：新增 `tests/test_nightly_ci.py`，覆盖 workflow 触发、依赖安装、统一 verify 入口，以及 `verify.sh all` 的 backend/frontend/browser e2e/docs 调用。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`
  - 本轮模块验证命令见 `docs/modules/deploy/tests.md` 和 `docs/dev/testing-closure-state.md`。
- 未测风险：真实远端 GitHub Actions 是否启用、SSH/sudo/root-owned helper、systemd restart、PostgreSQL migration/PITR、Nginx live config、Redis/RabbitMQ 真连接、OA iframe cookie 和真实浏览器缓存。
- 后续事项：发布前执行 staging release smoke；所有模块闭环后进入完成审计。
## 2026-07-15 import Audit 受控恢复入口

- `finops-deploy-control import-audit-repair` 固定调用 release 内 module，不开放任意 SQL/shell。
- dry-run 为 repeatable-read read-only snapshot；execute 要求相同 SHA-256 fingerprint，并在 serializable advisory-lock 事务内只写 import rows 与 source-batch 一致的 invoice totals。
