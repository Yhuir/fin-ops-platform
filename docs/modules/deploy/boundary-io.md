# 部署模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：部署模块负责发布、runtime worker/systemd/env/nginx/verify，不承载业务逻辑。
- 当前缺口：新增 read model/worker 时必须同步 deploy examples 和 runtime worker manifest。
- 旧代码删除条件：旧部署脚本或 systemd example 无引用且 README/operations 已迁移。

## 职责边界

### 负责

- `deploy-oa` 发布入口、nginx/systemd/env examples、runtime worker 确保脚本、verify 脚本。
- 生产 rollout、worker manifest、部署前后校验。

### 不负责

- 不直接修复业务数据。
- 不定义业务 API。
- 不绕过应用层执行生产写操作。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Deploy command | `scripts/deploy-oa.sh` | 使用明确 release/remote/env |
| Runtime worker manifest | `runtime_worker_manifest.py` | 必须匹配 registry |
| Verify command | `scripts/verify.sh` | 按 backend/web/docs/ops 分类执行 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Release artifact | 生产服务器 | 可追踪版本 |
| systemd/env files | deploy/oa | 与 registry 一致 |
| Verification result | operator/CI | 失败不得伪装成功 |

## 持久化与投影

- Own read model：无。
- Worker contract：`runtime_worker_registry.py`、systemd/env examples。
- Production docs：`docs/operations/`、`deploy/oa/README.md`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Scripts | `scripts/deploy-oa.sh`、`scripts/deploy_oa.py`、`scripts/verify.sh` |
| CI | `.github/workflows/nightly-ci.yml` |
| Deploy control | `deploy/oa/bin/finops-deploy-control.sh`、`finops-ensure-runtime-workers.sh` |
| Examples | `deploy/oa/nginx.fin-ops.conf.example`、`deploy/oa/systemd/*.service.example`、`deploy/oa/env/*.env.example` |
| Worker manifest | `backend/src/fin_ops_platform/tools/runtime_worker_manifest.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_deploy_*.py`、`tests/test_runtime_worker_registry.py` |

## 依赖方向

- 允许依赖：runtime worker registry, operations docs, CI verify scripts。
- 必须通过：documented deploy scripts.
- 禁止绕过：ad hoc production edits without operations docs; scripts embedding business fixes.

## 测试与验证

- `tests/test_deploy_oa_script.py`
- `tests/test_deploy_runtime_examples.py`
- `bash scripts/verify.sh docs`

## 当前缺口和删除条件

- 新增 worker/read model 是 deploy-impacting change，必须同步 examples、docs、tests。
