# 部署 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-08-03 - 自动风险分级与 005-only 普通发布门禁

- 根因：一次性 Settings ACL 切换逻辑被固化进每次发布，导致普通前端或 runtime 变更也读取 006、重写 env/OA binding，并无条件等待 T+300。
- 修复：deploy-control 直接比较候选与唯一 active release 的实际包内容，自动判定 `frontend`、`runtime` 或 `acl`；不存在手工 profile/skip。无法证明纯前端时保守升级为 `runtime`，ACL 文件变化优先升级为 `acl`。
- `frontend` 只执行 pre/T+0 的 exact dist、active release、worker inventory、ready、005 session 和公开 shell/asset；`runtime`/`acl` 保留 pre/T+0/T+60/T+300；标准激活统一只读取 005。

## 2026-08-05：移除 006 标准发布依赖并收窄 ACL profile

- 根因：`ACL_PATHS` 包含通用 Settings service/store/repository，普通设置扩展会被误判为 ACL；`release-gate-activate` 随后强制要求旧的 005/006 preflight artifact。
- 决策：ACL hash 只保留直接鉴权、权限 route/service、OA role sync、专项工具和 ACL migration；标准激活不再消费双身份 artifact。数据库 ACL guard、strict env、005 session、完整 runtime checkpoint 和 ACL 失败后的 forward-repair 语义保持不变。
- 005/006 preflight/post-deploy 命令仅保留为显式专项验收工具；不删除工具，避免丢失需要人工复验权限矩阵时的既有能力。
- 一次性 retired env/OA binding cleanup 已退出稳态激活链，历史 SQL 和 cleanup/rollback 实现删除；稳态只读断言 retired env 缺席，发现漂移直接失败关闭。

## 2026-08-01 - Production HTTP runtime 边界

- systemd API unit 只启动 Gunicorn WSGI，使用单 worker/有界 threads、backlog、worker recycle 和 graceful timeout；Nginx 同步限制 client body 与 upstream timeout。
- PostgreSQL API read/write pool 各有 acquire timeout、max waiting 和 pool name；HTTP overload/DB pool timeout 映射 503，避免无限线程等待十个连接。
- pidfile 位于 systemd `RuntimeDirectory=fin-ops`，供 data reset worker 完成后受校验请求 Gunicorn reload；旧 custom server 和 SSE release gate 已退出部署链路。

## 2026-08-01 - 新增 required worker 的 preflight registry 边界

- 生产预激活门禁暴露升级顺序缺陷：候选 gate 用候选 registry 审计 stable runtime，会把尚未安装的新增
  `settings-maintenance` worker 误报为缺失。
- `runtime_sync_closure_gate` 增加显式 required worker inventory 输入；deploy-control 仅在 `preflight` 从
  stable release manifest 传入，T+0/T+60/T+300 仍使用候选 registry。没有预启动候选 worker，也没有绕过门禁。
- 回归覆盖 stable inventory 透传、runtime monitoring scope 和 deploy-control 脚本合同。

## 2026-08-02 - OA cleanup 多目标 artifact canonical hash 顺序

- 生产 activation 在 OA cleanup consumer 校验阶段失败：两个 target hash 均合法且唯一，但 preflight producer 沿用 raw
  `(role_id, menu_id)` 顺序，未满足 consumer 的 lowercase SHA-256 字典序合同。
- 最小修复只在 authoritative preflight producer 排序 salted target hashes；rollback targets 和 target-set fingerprint 继续消费
  同一 canonical 列表。deploy-control consumer 不放宽，仍拒绝未排序、重复、非法、不对称或 fingerprint 漂移。
- 失败发生在 OA cleanup、migration、service cutover 前；runtime env 已恢复，旧 API、dispatcher 和六个 worker 保持 active，
  candidate 未激活。本地修复不代表生产通过，必须用新 commit 重建 candidate、重新生成 preflight artifact 并重新批准。

## 当前决策

- 预激活 canonical page audit 仍先要求当前 runtime 的鉴权 HTTP 系统审计可达且返回完整 snapshot/contract；
  若它仅因旧 release 的页面审计实现返回已识别的内部完整性失败，候选 gate 才用候选代码对同一生产
  PostgreSQL 执行一次 `repeatable_read_read_only` 系统审计，并复用同一严格结果校验器。HTTP 401、非 200、
  非法 JSON、snapshot/contract 缺失及候选审计失败全部 fail closed；T+0 以后仍必须由已激活候选的 HTTP
  系统审计直接通过。该边界只解决审计代码本身升级时的预激活死锁，不跳过鉴权、不放宽页数/顺序/状态合同。
- 生产发布入口保持 `./scripts/deploy-oa.sh`，只走 release-based 部署；`legacy-current` 覆盖式部署入口已经移除。
- Nightly CI 的唯一全量入口是 `bash scripts/verify.sh all`；它必须同时运行 clean app check、后端 unittest discovery、前端 Vitest、前端 build、deterministic Playwright browser smoke 和 docs check。clean app check 使用临时 `FIN_OPS_DATA_DIR`，不读取本地 legacy app Mongo；当前配置 runtime check 必须显式运行 `bash scripts/verify.sh runtime-check`。
- deploy-control helper 必须使用 `/etc/fin-ops/fin-ops.common.env`、`fin-ops.secrets.env` 和 migration-only env；API/worker 不允许直接加载 migrator env 或旧 `/root` env。
- required worker 矩阵从 `runtime_worker_manifest` / registry 派生；deploy runbook 和 helper 不维护第二份硬编码清单。
- 发布成功不能只看 systemd active；必须等 `/health/ready`、required worker readiness 和公网 session API JSON proxy。
- 本地自动化保护脚本、workflow、模板和 registry 契约；真实 SSH/sudo/systemd/PostgreSQL migration/queue、Nginx live config、API 可选 Redis cache 和浏览器缓存必须由 staging 或生产前 smoke 证明。
- runtime env 事实源是 `deploy/oa/env/*.env.example` 和生产 `/etc/fin-ops/*` split env；旧单文件 `deploy/oa/fin_ops.env.example` 已移除。

## 历史记录

## 2026-07-31 - Release Gate 隔离写探针与 publishing 静默采样

- 根因一：自动 release gate 曾在候选激活后用真实生产业务关系执行 confirm/withdraw；即使输入标记为
  `test_owned`，真实关系的版本冲突也会返回 409 并触发回滚。这类业务 mutation 不应是部署基础设施
  门禁的职责。
- 根因二：RabbitMQ consumer 可能先完成 PostgreSQL durable event，dispatcher 随后才写 publish
  confirm；进程在两者之间退出时会留下 `status=done/publish_status=publishing`。该终态可以安全协调，
  但部署 shell 在 gate 前后隐式协调会掩盖持续复发的 dispatcher/状态机故障。
- 修复：自动 gate 只执行同一生产 PostgreSQL 上的 `pg_temp` 事务内 insert/read/delete/rollback
  可逆写探针，以及只读 canonical page audit；不再读取业务 scenario、approval ticket 或修改真实业务
  关系。`done/publishing` 只允许 closure gate 调用现有 repository 方法协调，并把数量写入 evidence；
  协调后必须再取得一次没有新协调且 `publishing_outbox_count=0` 的干净采样，采样期复发直接 fail
  closed。T+0、T+60、T+300 会重复验证该合同。
- 边界：PostgreSQL 仍是 durable 状态事实源，RabbitMQ 仍只做 transport/wakeup；独立、显式、经审批的
  `write_operation_e2e_smoke` 保留给 operator 验证真实业务入口，但不属于自动发布门禁。没有新增
  worker、表、队列、缓存、定时器或兼容链路。
- 验证：隔离写、canonical audit、409 非提交语义、一次协调后干净采样、持续复发阻断、deploy evidence
  和 production-equivalent T+0/T+60/T+300 gate。
- 预激活合同错位修复：候选 gate 会读取仍在运行的旧 stable API，不能要求旧响应已经包含候选新增的
  registry 明细字段。门禁现在用候选 `PAGE_AUDIT_REGISTRY` 严格核对旧响应的 summary 与完整逐页 proof；
  只有三个 registry 字段整体缺失时可由这两类证据证明，部分字段、漏页、额外页和顺序漂移全部失败关闭。
  同时 canonical audit 移到 runtime convergence 之后，避免在可安全协调的 `done/publishing` 终态清理前
  先制造一次确定失败。

## 2026-07-26 - Workbench relation Cost active/all 生产验证闭环

- Candidate C 的 test-owned `bank_oa_invoice` 生产链路证明 confirm、自动 recovery、六个受影响页面和两个 isolation 页面均正确，但两个 checkpoint 的 System Audit 因 `all:2026-06` Cost scope 未被访问而停在 15/16。
- 根因是 runner 新增的 relation-impact Cost gate 把每一个 Cost consumer 都强制为 `project_scope=active`，与本模块既有“同一页面最多三个精确 scope probe”和 System Audit 同时检查 active/all 的合同冲突。
- 最小修复继续要求至少一个 `project_scope=active` semantic probe，并只允许额外的 `project_scope=all` probe；所有 Cost probes 仍必须使用 project/bank/expense_type Workbench-dependent view 和 relation-derived assertion。未修改 Cost runtime、read model scope、worker、queue、业务 API 或写后 zero-fan-out。
- 回归覆盖 active-only 可用、all-only fail closed、active+all 可用；Candidate D 发布后复用同一 test-owned fixture 重新执行 confirm -> active/all fresh -> withdraw -> active/all fresh -> System Audit 16/16。

## 2026-07-25 - Write-operation apply 证据持久化

- 生产 apply runner 已实际完成 6 次 test-owned confirm/withdraw 并返回 0，但 SSH stdout 证据文件为 0 字节；API release metrics、写状态、队列和 fixture recovery 证明业务执行成功，stdout 不能继续作为唯一证据载体。
- deploy-control 复用 runner 既有 `--output`，先将 dry-run/apply JSON 写入 `mktemp` 创建的 mode-600 临时报告，再单次输出并由 `EXIT` trap 精确删除。runner 非零退出仍输出 JSON 并保留原退出码，报告缺失则 fail closed。
- 临时文件只承载单次验证报告，不是业务备份或恢复点；该修复不改变业务 API、read model、queue、worker、事实源或页面 I/O。

## 2026-07-25 - 跨月关系生产验证 scope 上限

- test-owned Turnover closure 生产证据证明，同一关系可以同时影响两个 canonical 月份和 Workbench `all` 组合视图；Cost 还需要一个绑定 fixture 身份的流水视图，以及 `project_scope=active/all` 两个 Workbench-dependent 视图。
- write-operation runner 因此允许同一受影响页面最多三个明确 consumer scope probe；第 4 个重复 scope 继续 fail fast，isolation 页面仍必须恰好一个 probe。
- 同一受影响页面至少一个 probe 必须绑定 test-owned row/case 身份；其它精确 scope 仍必须执行 registered API、fresh gate 和非空业务根断言，但聚合视图无需伪造不存在的行身份。
- 该调整只修正生产验证输入边界，不改变页面 query owner、read model scope、queue、worker、写路径或运行时 fan-out。

## 2026-07-24 - 写响应到页面可见的真实性能门禁

- 生产 round 8 暴露 runner 只检查最后一次 consumer GET 的 `target_ms`，却把 `operation_commit_to_visible_ms` 作为非阻断观测；因此 11–12 秒才 fresh 的页面仍可能被标记 pass。
- round 9 进一步证明 mutation-response 计时会把 runner 自己在首次页面访问前执行的 zero-fan-out 审计算进页面 SLO，与访问触发合同冲突。runner 现在先并发访问 consumer，再执行写后审计；同一个 consumer `target_ms` 约束单次 fresh GET 与首次访问到 fresh/业务断言通过的总耗时，超限返回 `consumer_visibility_slo_miss`。`operation_commit_to_visible_ms` 只作观测，不改变业务 API、queue、worker或页面。

## 2026-07-23 - 受影响页面多 scope 生产验证边界

- Cost Statistics 正式页面使用 `project_scope=active`，同一 API 的 `project_scope=all` 仍是导出/后端合同；只访问其中一个 scope 不能证明另一个 scope 已收敛，也不能用运行时 sibling enqueue 伪造覆盖。
- write-operation runner 因此允许同一“受影响页面”最多两个明确 consumer scope probe，逐个执行正常 GET 和 fresh/business assertion；isolation 页面仍必须恰好一个 probe，第三个重复 scope fail fast。
- 该能力只属于 test-owned 生产验证输入，不修改应用 read model scope policy、query owner、写路径 target、worker、queue 或 Cost 精确访问语义，不引入 fan-out。

## 2026-07-23 - Write-operation zero-fan-out receipt 边界修复

- 生产 test-owned bank-turnover closure 中，confirm 与 recovery 均在 1 秒内返回 200/committed，业务 inverse 已恢复 inactive；runner 却因响应的 `outbox_event_ids: []` 被 truthy 判断丢失，继续强制查询 disabled-by-default durable idempotency 表并误报 `expected exactly one Workbench idempotency record`。
- 最小修复保留显式空 receipt：空列表代表本次普通写没有写后页面 refresh event；只有响应完全缺少 receipt 时才查询 durable record。每个 checkpoint 开始前清除内部 receipt 变量，禁止 confirm receipt 污染 withdraw/recovery。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`，不改变业务 API、canonical facts、read model、worker、queue 或生产 env；verification 继续用同一 test-owned fixture 复跑 confirm -> withdraw/recovery -> System Audit。
- 测试新增空 receipt 捕获和跨 checkpoint 隔离，覆盖显式零 fan-out跳过 durable lookup、下一 checkpoint receipt 缺失时仍准确查询 durable evidence。

## 2026-07-26 - 固定生产 scenario 与 bounded preview sample 转发

- Phase 30 候选前只读 preflight 发现 root-owned helper 仍只允许 `/tmp` scenario 且不接受第四个 sample 参数，无法按既有固定标准 scenario 执行 10 次只读 preview。
- 最小修复让 helper 接受固定 root-owned `0600` `/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`，同时保留临时 scenario 的 `/tmp`、`finops-deploy` owner、非 symlink、1 MiB 与不可 group/world write 门禁；其它路径继续拒绝。
- 第四参数只接受 `1..20`，默认 1，并原样转发给同一 release runner 的 `--relation-preview-samples`。它不放宽 Admin Token/standing approval stdin、test-owned/inverse、mutation count、业务 API 或 SQL 边界。
- 本地 deploy/runner 回归与完整候选门通过后才允许推送和部署；生产 dry-run 必须先证明固定文件仍是一个可逆 `bank_oa_invoice` scenario，缺 fixture 或 inverse 时零 mutation。

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
- 2026-08-05：复用同一固定工具增加显式 `--retire-etc-session-id`，只解决已删除 ETC task 遗留严格 session 阻断发布的生命周期冲突；保留全部 session/附件证据，写入前绑定 task deleted、稳定 session、零活动 job/outbox 与 snapshot fingerprint，禁止任意 SQL、扫描式目标或门禁豁免。

## 2026-08-07 OA 附件发票受控恢复入口

- 复用既有 `OAAttachmentInvoicePromotionService`，通过生产已批准的 `finops-deploy-control workbench-rehydrate <release> --promote-oa-attachment-invoices` 固定维护入口调用 exact release 代码，不要求 root helper 自更新，也不新增任意 SQL/shell 入口。
- dry-run 输出候选 SHA-256 fingerprint；apply 必须携带相同 fingerprint 和显式确认参数，候选变化时 fail closed。
- 身份桥恢复只写缺失或变化的强身份行，重复执行候选与应用数均为 0；保留人工导入来源证据，不覆盖规范发票身份。
# 2026-08-24 - Migration 失败必须终止 release 激活

- 生产演练发现 `release_gate_activate` 通过 `if ! (activate_release ...)` 调用激活函数时，Bash 条件上下文会使函数内部单独的 migrator 非零退出继续向后执行；因此 0153 证据拒绝后 binary 仍被激活，虽然 schema 保持 0152 且没有半写数据。
- 最小修复在 `run_schema_migrations` 调用点显式 `|| die`，迁移失败立即终止候选激活并进入既有 rollback/forward-repair 状态机；不新增 profile、skip、fallback 或第二部署入口。
- 回归由 `tests/test_deploy_oa_script.py::DeployOAScriptTest::test_activation_stops_immediately_when_schema_migration_fails` 保护调用顺序与显式失败传播。
