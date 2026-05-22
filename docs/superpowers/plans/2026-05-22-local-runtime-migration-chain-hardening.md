# Local Runtime And Migration Chain Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local runtime checks production-equivalent and make standard PostgreSQL migration status/apply continue through explicitly accepted historical checksum drift without hiding new drift.

**Architecture:** Local startup remains `scripts/start-backend.sh -> fin_ops_platform.app.main` on port `8001`; validation probes the same split workbench endpoints used by the frontend. Migration history drift is handled through a checked-in acceptance registry that must match version, migration name, applied checksum, and current checksum exactly; any unregistered drift still fails.

**Tech Stack:** Bash runtime scripts, Python migration CLI, PostgreSQL `schema_migrations`, unittest, repository SQL read models.

---

## Final Codex Execution Prompt

```text
/goal 收口本地 production-equivalent runtime 启动入口和 PostgreSQL migration checksum 历史漂移，不能再靠手动绕过。

上下文：
- 仓库：/Users/yu/Desktop/fin-ops-platform
- 本地默认后端应由 scripts/start-backend.sh 启动 fin_ops_platform.app.main，端口 8001。
- 前端 Vite proxy 默认指向 http://127.0.0.1:8001。
- 当前服务器 PG 已应用 0014_workbench_groups_read_model.sql，但 0004-0007 历史 checksum 与当前仓库文件不同。
- 不能改写已发布旧 migration；后续 schema 变化必须新建 migration。

目标：
1. 让本地 runtime check 明确验证 /api/workbench/summary 和 /api/workbench/groups，而不是旧 /api/workbench 全量接口。
2. 启动/检查文档明确 8001 是当前后端入口，8000 上残留的 backend.api.main:app 不能作为本项目状态判断。
3. 建立显式 accepted checksum drift registry，只允许 0004-0007 当前已确认的生产历史 drift 通过。
4. migrate status 对已接受 drift 显示 accepted-checksum-drift。
5. migrate apply 对已接受 drift 跳过并继续；未登记 drift 仍失败。
6. schema_migrations 表已存在时，migrate apply/status 不应要求 runtime 用户拥有 public schema CREATE 权限。
7. 标准 migrate status/apply 在当前 PG 上不再被 0004-0007 阻塞。

串行任务：
1. 读取 scripts/start-backend.sh、scripts/check-local-runtime.sh、web/vite.config.ts、backend/src/fin_ops_platform/postgres/migrate.py、tests/test_postgres_migrations.py。
2. 写 failing tests 覆盖 FIN_OPS_POSTGRES_DATABASE_URL fallback、accepted-checksum-drift、apply skip 和 metadata table already-exists 权限边界。
3. 实现 accepted checksum drift registry 和 migration CLI 支持。
4. 更新 runtime check 到 split workbench endpoints。
5. 更新 backend/local-development 文档，明确 8001 和 split endpoint smoke。
6. 在当前 PG 上运行 migrate status/apply，确认 0014 applied 且 0004-0007 是 accepted-checksum-drift。
7. 重启或校验本地后端入口，再跑 ./scripts/check-local-runtime.sh --require-backend。

可并行任务：
- A: migration CLI/tests。
- B: runtime check/docs。
- C: 当前 PG smoke。

完成门槛：
- PYTHONPATH=backend/src python -m unittest tests.test_postgres_migrations -v 通过。
- DATABASE_URL/FIN_OPS_POSTGRES_DATABASE_URL 指向当前 PG 时，python -m fin_ops_platform.postgres.migrate status 显示 0004-0007 accepted-checksum-drift、0014 applied。
- python -m fin_ops_platform.postgres.migrate apply 不再因为已接受 checksum drift 停住。
- ./scripts/check-local-runtime.sh --require-backend 验证 split workbench endpoints。
- 未登记的 checksum mismatch 仍会失败，不允许静默通过。
```

## Execution Notes

- [x] Added `backend/src/fin_ops_platform/postgres/accepted_checksum_drifts.json`.
- [x] Updated migration CLI to load exact accepted drift records.
- [x] Updated local runtime check to probe `/api/workbench/summary` and `/api/workbench/groups`.
- [x] Updated local/backend docs to describe the `8001` runtime entrypoint and split endpoint smoke.
