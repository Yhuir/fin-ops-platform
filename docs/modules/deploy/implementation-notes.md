# 部署 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 生产发布入口保持 `./scripts/deploy-oa.sh`，默认走 release-based 部署；legacy-current 仅保留兼容路径。
- Nightly CI 的唯一全量入口是 `bash scripts/verify.sh all`；它必须同时运行 clean app check、后端 unittest discovery、前端 Vitest、前端 build、deterministic Playwright browser smoke 和 docs check。clean app check 使用临时 `FIN_OPS_DATA_DIR`，不读取本地 legacy app Mongo；当前配置 runtime check 必须显式运行 `bash scripts/verify.sh runtime-check`。
- deploy-control helper 必须使用 `/etc/fin-ops/fin-ops.common.env`、`fin-ops.secrets.env` 和 migration-only env；API/worker 不允许直接加载 migrator env 或旧 `/root` env。
- required worker 矩阵从 `runtime_worker_manifest` / registry 派生；deploy runbook 和 helper 不维护第二份硬编码清单。
- 发布成功不能只看 systemd active；必须等 `/health/ready`、required worker readiness 和公网 session API JSON proxy。
- 本地自动化保护脚本、workflow、模板和 registry 契约；真实 SSH/sudo/systemd/PostgreSQL migration/Nginx live config/Redis/RabbitMQ/浏览器缓存必须由 staging 或生产前 smoke 证明。

## 历史记录

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
