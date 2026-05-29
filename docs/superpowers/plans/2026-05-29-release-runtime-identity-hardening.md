# Release Runtime Identity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent production release services from importing stale `/opt/fin-ops/current` code by archiving legacy current and making `/health` fail readiness when working directory, import path, release metadata, or `PYTHONPATH` are inconsistent.

**Architecture:** Release activation remains the only production entry point. The deploy helper archives the legacy current tree during activation, and the API reports a runtime identity contract in `/health`; release-mode mismatches set `status` to `not_ready` so deploy readiness gates fail before users see stale-code behavior.

**Tech Stack:** Python standard library, systemd drop-ins, Bash deploy helper, unittest.

---

## Final Codex Prompt

```text
/goal 生产级收紧 fin-ops release 部署：归档或隔离 legacy /opt/fin-ops/current，避免 release 模式继续误用；在 /health 暴露并校验 WorkingDirectory、实际 fin_ops_platform.__file__、RELEASE.json commit、PYTHONPATH。若进程工作目录和实际 import 路径不一致，或 release metadata 无法读取，health 必须返回 status=not_ready，让 deploy readiness 失败。不要做救急临时方案；实现代码、测试、文档，提交、推送、部署并验证生产。

任务：
1. 后端 health 增加 runtime_release 字段，包含 working_directory、package_file、expected_source_root、pythonpath、release_metadata、is_release_runtime、consistent、problems。
2. release runtime 判定：working_directory 位于 /opt/fin-ops/releases 下，或存在 RELEASE.json。release runtime 下 package_file 必须位于 working_directory/backend/src，RELEASE.json 必须可解析；否则 readiness_summary.status=not_ready。
3. deploy helper activate 归档 legacy /opt/fin-ops/current 到 /opt/fin-ops/legacy-current-archives/current-<timestamp>，并保持幂等；release 模式不再依赖 current。
4. deploy 脚本 contract check 必须验证远端 helper 具备 EnvironmentFile reset、schema migration apply、legacy current archive。
5. 增加 unittest 覆盖 health runtime identity ready/not_ready、deploy helper 和 deploy script contract。
6. 更新部署文档，说明 /opt/fin-ops/current 只作为历史归档，不参与 release runtime。
7. 跑相关测试、语法检查、diff check；提交 push main；安装 helper，正式 deploy，验证生产 /health 和进程环境。
```

### Task 1: Health Runtime Identity Contract

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_app.py`

- [ ] Add a helper that reads runtime identity without secrets: working directory, package file, expected source root, `PYTHONPATH`, release metadata, release-mode flag, consistency boolean, and problem list.
- [ ] Make `readiness_summary()` attach this helper as `runtime_release`.
- [ ] Make `readiness_summary()` set `status` to `not_ready` when `runtime_release.consistent` is false.
- [ ] Add tests for local/dev ready behavior and release-mode mismatch not-ready behavior.

### Task 2: Release Helper Legacy Current Archive

**Files:**
- Modify: `deploy/oa/bin/finops-deploy-control.sh`
- Modify: `scripts/deploy_oa.py`
- Test: `tests/test_deploy_oa_script.py`

- [ ] Add `LEGACY_CURRENT_DIR=/opt/fin-ops/current` and `LEGACY_CURRENT_ARCHIVE_DIR=/opt/fin-ops/legacy-current-archives`.
- [ ] Add an idempotent `archive_legacy_current()` called during `activate` before service restart.
- [ ] Extend deploy preflight contract to require `archive_legacy_current`.
- [ ] Add tests asserting helper archives legacy current and remote deploy script blocks helpers missing that contract.

### Task 3: Documentation, Verification, Deploy

**Files:**
- Modify: `deploy/oa/README.md`

- [ ] Document that `/opt/fin-ops/current` is legacy-only and is archived during release activation.
- [ ] Run `PYTHONPATH=backend/src python3 -m unittest tests.test_app tests.test_deploy_oa_script -v`.
- [ ] Run `bash -n deploy/oa/bin/finops-deploy-control.sh scripts/deploy-oa.sh`.
- [ ] Run `python3 -m py_compile scripts/deploy_oa.py && git diff --check`.
- [ ] Commit, push, install helper, run `./scripts/deploy-oa.sh`, and verify production health/process identity.
