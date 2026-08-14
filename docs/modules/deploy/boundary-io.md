# Deploy 模块边界与 I/O

日期：2026-08-15

## 输入

- 已提交并推送的 exact `main` commit。
- 本地验证通过的 backend/frontend/docs 与 production frontend build。
- SSH/server/env、独立 migrator、runtime secrets 和当前 release fingerprint。

## 输出

- `/opt/fin-ops/releases/<release>` immutable payload。
- 原子 active symlink、API service、四个 registry worker。
- Migration/evidence/checkpoint/health/SLO 结果。

## 边界

- `scripts/deploy-oa.sh` 负责 build/upload/activate orchestration。
- `finops-deploy-control` 负责 root 级 maintenance、migration、runtime assets、checkpoints。
- `finops-ensure-runtime-workers` 只从 registry 派生 worker；未登记实例 stop/disable。
- 不开放任意 shell/SQL，不修改 OA 源码，不删除主数据库，不恢复旧 projection runtime。

## Forward-only

Migration 0149 退役旧 schema。执行后 previous release 若依赖旧对象则不可自动恢复；候选失败保持 maintenance
并 forward repair。前端-only release 仍可按 immutable fingerprint 回滚。

## 验证

`tests/test_deploy_oa_script.py`、`tests/test_deploy_runtime_examples.py`、
`tests/test_read_model_runtime_removal.py` 与生产 T+0/T+30 evidence。
