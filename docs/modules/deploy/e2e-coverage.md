# Deploy Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `DEPLOY-E2E-001` | `covered` | `tests/test_nightly_ci.py`、`scripts/verify.sh` contract tests。 | GitHub Actions 是否启用需远端确认。 |
| `DEPLOY-E2E-002` | `partial` | `tests/test_deploy_oa_script.py`、多次生产 release smoke 记录。 | 每次发布仍需实际 release smoke；本地不执行 SSH/systemd。 |
| `DEPLOY-E2E-003` | `partial` | 生产只读检查显示 API、dispatcher、20 个 workers 指向同一 release；deploy tests 覆盖 helper contract。 | 未来 release 需重新取证。 |
| `DEPLOY-E2E-004` | `partial` | `tests/test_deploy_oa_nginx_config.py`、public session route smoke。 | live `nginx -T` 与缓存行为需生产/staging smoke。 |
| `DEPLOY-E2E-005` | `partial` | public/local `health_ready_payload_probe` 通过，runtime_health 只读 pass。 | authenticated/admin/write-operation full gate 未闭合。 |
| `DEPLOY-E2E-006` | `external-risk` | operations runbooks、release cleanup tests。 | 真实 rollback/PITR/backup restore 未由本地自动化证明。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_deploy_oa_nginx_config tests.test_nightly_ci tests.test_deploy_runtime_examples tests.test_runtime_worker_registry tests.test_app tests.test_app_postgres_mode -v
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

## 下一步

1. 每次发布后记录 release、health ready、systemd WorkingDirectory、worker readiness 和 public session route。
2. 获取 GitHub Actions 远端启用状态或保留为 documented-risk。
3. 对 rollback/PITR/backup restore 建 staging smoke，不把 deploy script unit tests 当成生产恢复证明。
