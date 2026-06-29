# Read Model Performance Optimization /goal Prompt

把下面整段复制给 Codex `/goal`。它是主控 prompt：每轮只生成一个 bounded execution prompt，立即执行，然后根据结果决定下一轮。

```text
Fully close the read model performance optimization task for /Users/yu/Desktop/fin-ops-platform.

Objective:
Optimize read model performance to production-grade high performance with measured evidence, not guesses. Finish the loop across planning, local verification, safe production migration/deploy, production metric collection, targeted second-wave optimization for any proven slow handler, docs, and final risk report.

Use GSD as the controller workflow:
- Maintain one closed-loop controller.
- In each loop, generate exactly one bounded execution prompt for the next action.
- Execute that prompt immediately in the same run.
- Review the result.
- Decide DONE, BLOCKED, or CONTINUE.
- If CONTINUE, derive the next single prompt from the latest evidence. Do not generate a backlog.

Repository and architecture rules:
- Follow AGENTS.md and repository-local docs.
- Use Ponytail/full discipline: smallest evidence-backed change that works; no new framework, no speculative cache, no broad rewrite.
- Preserve user changes in the worktree. Never revert unrelated files.
- Before behavior changes, read the affected module boundary docs.
- Read model pages must keep the existing freshness/status/enqueue contracts unless the task explicitly proves a contract bug.
- Do not bypass ReadModelRefreshGateway, dirty scope policy, runtime queue, or source-version guards.
- Do not make pages read stale read models while reporting fresh.
- Redis can only cache after a fresh gate. RabbitMQ is transport/wakeup, not truth.
- Workers must remain independent from Application, app.server, app.auth, HTTP response objects, cookies, and route modules.
- server.py stays thin. SQL/table knowledge stays in repositories. Business logic stays in services.

Current known context:
- GSD directory: .planning/refactors/read-model-performance-optimization/
- Existing Wave 1 files may already exist:
  - PLAN.md
  - SUMMARY.md
  - backend/src/fin_ops_platform/postgres/migrations/0076_outbox_read_model_refresh_metric_attention.sql
  - tests/test_postgres_migrations.py
  - tests/postgres_test_utils.py
  - docs/operations/monitoring.md
- Wave 1 intent: fix RuntimeMonitoringRepository read model refresh metric sampling by adding a partial index over job.outbox_events for completed duration samples plus failed/dead-lettered refresh rows.
- Do not assume Wave 1 is deployed. Verify local and production state.

Hard production safety gates:
- Do not deploy from a dirty mixed worktree. If unrelated dirty files exist, create/use a clean branch or worktree containing only intended read-model-performance changes.
- Preferred branch name: codex/read-model-performance-optimization.
- Stage/commit only intended files when a clean release package is required. Do not push unless explicitly needed.
- Production deployment path is ./scripts/deploy-oa.sh in release mode.
- Production activation runs migrations through /usr/local/sbin/finops-deploy-control activate.
- The migration runner wraps migration files in begin/commit. Before applying any index migration to a large production table, inspect lock risk. If CREATE INDEX inside a transaction is unsafe for production table size/write rate, do not force it; either implement an approved safe migration path with truthful schema_migrations accounting or mark BLOCKED with exact evidence.
- Do not run ad hoc UPDATE/DELETE/TRUNCATE against production runtime tables.
- Production read-only SQL/EXPLAIN is allowed when needed. Mutating refresh smoke is allowed only through existing read_model_slo_smoke / ReadModelRefreshGateway and only after recording why it is safe.
- Never print or persist tokens, DB URLs, passwords, cookies, or secret env values. Redact reports.
- If an Admin-Token is required, ask the user to paste it interactively, store it only in the current shell env, and do not write it to files.
- SSH/root may be used only for production validation, release helper operations, and controlled existing tools. Prefer finops-deploy + sudo helper first; use root only when helper cannot run the required approved validation.

Performance targets:
- /health/ready: pass health_ready_payload_probe, target <= 1000ms, JSON, <= 50KB, bounded api_performance, no HTML fallback.
- Authenticated HTTP SLO: core API/page probes p95 <= 1000ms after warmup where realistic; no critical read model API should exceed 5000ms without a documented external blocker.
- Read model enqueue-to-fresh: critical read_model_slo_smoke target <= 5000ms as the hard production gate, then tighten obvious hotspots toward 1000ms when a small evidence-backed change can do it safely.
- Runtime monitoring/dashboard: AppHealth read model refresh metrics must use bounded indexed samples and must not scan historical outbox.
- Final status must be based on before/after production data, not local assumptions.

Required artifacts:
- Keep raw non-secret evidence under .planning/refactors/read-model-performance-optimization/evidence/<timestamp>/.
- Update SUMMARY.md after each major loop with:
  - status
  - production baseline
  - production post-change metrics
  - slowest read_model keys/handlers
  - files changed
  - tests run
  - docs impact
  - remaining risks
- Update PLAN.md only when the plan materially changes.
- Update docs/ only for long-term facts. Do not copy raw prompt text into docs/.

Loop algorithm:

1. Analyze current state
   Generate and execute one prompt that:
   - Reads AGENTS.md, README.md, ARCHITECTURE.md, docs/index.md, docs/app-architecture/README.md, docs/modules/README.md.
   - Reads these read-model/runtime docs:
     - docs/architecture/module-boundaries/README.md
     - docs/architecture/module-boundaries/inventory.md
     - docs/architecture/module-boundaries/read-model-contracts.md
     - docs/modules/read-models/README.md
     - docs/modules/read-models/boundary-io.md
     - docs/modules/read-models/tests.md
     - docs/modules/runtime-workers/README.md
     - docs/modules/runtime-workers/boundary-io.md
     - docs/modules/app-health-operations/README.md
     - docs/modules/app-health-operations/boundary-io.md
     - docs/operations/runtime-worker-governance.md
     - docs/operations/monitoring.md
     - deploy/oa/README.md
   - Checks git status and separates intended changes from unrelated dirty files.
   - Checks whether Wave 1 files exist and whether migration 0076 is already applied locally/production.
   - Reviews backend/src/fin_ops_platform/postgres/migrate.py for transaction semantics before any production index apply.
   - Reviews the actual queries that use the new index before trusting it.
   Stop condition: a written state summary in SUMMARY.md and a decision: CONTINUE to local verification, or BLOCKED with missing facts.

2. Local verification and release isolation
   Generate and execute one prompt that:
   - Creates or switches to a clean branch/worktree if needed.
   - Ensures only read-model-performance files are present for the release.
   - Runs the smallest useful checks first:
     PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_runtime_monitoring tests.test_health_ready_payload_probe tests.test_http_slo_probe tests.test_read_model_slo_smoke -v
     bash scripts/verify.sh docs
     git diff --check
   - If frontend build is required by deploy script, allow deploy script to build it; do not add frontend changes for this task.
   Stop condition: clean intended diff and local checks pass, or BLOCKED with exact failing command and root cause.

3. Production baseline, read-only first
   Generate and execute one prompt that:
   - Creates evidence/<timestamp>/baseline/.
   - Gets active release:
     ssh finops-deploy@finops-prod 'sudo -n /usr/local/sbin/finops-deploy-control status'
   - Runs health-ready probe against production:
     PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.health_ready_payload_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --json --output <baseline>/health-ready.json
   - If admin token is needed, asks user to paste it and keeps it only in env FIN_OPS_HTTP_SLO_ADMIN_TOKEN.
   - Runs authenticated HTTP SLO:
     PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --admin-token "$FIN_OPS_HTTP_SLO_ADMIN_TOKEN" --iterations 5 --warmup 1 --target-ms 1000 --include-samples --output <baseline>/http-slo.json
   - Runs helper dry-run scope discovery:
     ssh finops-deploy@finops-prod 'sudo -n /usr/local/sbin/finops-deploy-control read-model-slo-smoke <active-release> --json --critical-only --target-ms 5000'
   - Captures runtime read model refresh by key from /health/ready or AppHealth payload where available.
   Stop condition: baseline evidence saved and summarized, or BLOCKED with auth/SSH/helper issue.

4. Migration lock-risk decision
   Generate and execute one prompt that:
   - Uses read-only production evidence to estimate job.outbox_events size, write rate, pending/processing counts, and whether a transactional CREATE INDEX is acceptable.
   - Checks whether outbox_events_read_model_refresh_metric_attention_idx already exists.
   - If index exists and migration is accounted for, skip deploy and go to post-change validation.
   - If index does not exist and lock risk is acceptable, continue to deploy.
   - If lock risk is not acceptable, do not apply the current migration blindly. Implement the smallest safe supported migration/deploy path or mark BLOCKED if the current migration framework cannot truthfully support it.
   Stop condition: explicit apply/no-apply decision with evidence.

5. Deploy/apply Wave 1
   Generate and execute one prompt that:
   - Deploys only from the clean intended branch/worktree.
   - Uses:
     ./scripts/deploy-oa.sh --release-name read-model-perf-<short-sha>-<YYYYMMDDHHMMSS>
   - Does not pass --allow-dirty unless the release tree has been deliberately isolated and the remaining dirt is known generated build output not packaged as source.
   - Captures deploy output and active release status in evidence/<timestamp>/deploy/.
   - Verifies /health/ready after activation.
   Stop condition: deployment success and active release confirmed, or BLOCKED with deploy step and rollback/status information.

6. Post-deploy production measurement
   Generate and execute one prompt that:
   - Runs the same health_ready_payload_probe and http_slo_probe commands as baseline into evidence/<timestamp>/postdeploy/.
   - Runs read-model-slo-smoke dry-run through helper.
   - If controlled enqueue-to-fresh measurement is needed and safe, use root/current release env to run:
     release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
     cd "$release_src"
     PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.read_model_slo_smoke --json --critical-only --apply --target-ms 5000 --reason read_model_perf_validation_<timestamp> --output /tmp/finops-read-model-slo-smoke-<timestamp>.json
   - Copies only non-secret JSON output back into .planning evidence.
   - Compares before/after p50/p95/p99, slow events, failed/dead-lettered rate, current windows, and slowest read_model_key.
   Stop condition: before/after report in SUMMARY.md and decision DONE or CONTINUE to targeted optimization.

7. Targeted second-wave optimization
   Only enter this loop if production evidence still misses targets.
   Generate and execute one prompt for exactly one slowest proven bottleneck:
   - Select the slowest current read_model_key/API endpoint by production p95 or enqueue-to-fresh evidence.
   - Use CodeGraph for structural flow: context first, then explore/trace only what is needed.
   - Read that module's docs/modules/<module>/boundary-io.md and tests.
   - Inspect exact repository SQL/query path and existing indexes.
   - Get EXPLAIN (ANALYZE, BUFFERS) or the closest safe production query plan for the exact slow SQL. If EXPLAIN cannot be run safely, use pg_stat_statements/read-only stats and mark the evidence gap.
   - Apply the first Ponytail rung that works:
     1. delete unnecessary repeated work
     2. use existing index/helper/gateway
     3. add one missing bounded index
     4. narrow one query
     5. add one source-version skip where contract already supports it
     6. only then change projection logic
   - Add or update focused tests for the changed contract.
   - Update module docs only if boundaries, I/O, worker/read model contract, deployment, or performance facts changed.
   - Run local targeted tests, docs verify if docs changed, and git diff --check.
   - Deploy and re-measure production only after local checks pass and release tree is clean.
   Stop condition: that bottleneck passes target or is proven externally blocked; then decide DONE or loop to the next slowest bottleneck.

8. Completion gate
   Mark DONE only when all are true:
   - Intended code/docs/tests are isolated from unrelated worktree changes.
   - Local relevant verification passed or failures are explicitly unrelated and evidenced.
   - Production baseline and post-change metrics are saved.
   - Migration/index state is verified in production.
   - Critical read model SLO gate passes, or any miss has a concrete blocker with production evidence and no safe smaller code change remains.
   - SUMMARY.md contains before/after numbers and remaining risks.
   - docs/ long-term facts are updated if behavior/architecture/operations facts changed.

   Mark BLOCKED only when:
   - Required production auth/SSH/DB access is unavailable.
   - Migration lock risk cannot be safely handled by the current deploy/migration framework.
   - A needed user/DBA/business approval is required for mutating smoke or a risky production operation.
   - The same blocker persists after reasonable retry.

Final response format:
- Result
- Production before/after numbers
- Files changed
- Tests added or changed
- Seven test categories covered
- Seven test categories not applicable and why
- Verification commands run
- Production commands run
- Docs impact
- Remaining risk
```
