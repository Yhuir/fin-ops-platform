# Data Safety Reset Spec-first E2E Coverage

## 覆盖矩阵

| Spec ID | 状态 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| `RESET-E2E-001` | `covered` | `tests/test_settings_data_reset_service.py`、permissions role matrix、`web/src/test/SettingsPage.test.tsx`。 | 真实 OA 密码服务异常仍需 staging smoke。 |
| `RESET-E2E-002` | `covered` | `web/e2e/settings-data-reset-flow.spec.ts`、Settings component tests。 | 真实视觉/长任务由 staging smoke 观察。 |
| `RESET-E2E-003` | `covered` | `tests/test_settings_data_reset_service.py`、`tests/test_background_job_service.py`、`web/e2e/settings-data-reset-flow.spec.ts`。 | 真实长时间 job recovery 需 staging。 |
| `RESET-E2E-004` | `covered` | service tests 覆盖 bank/invoice/OA reset、protected targets、relation 保留/删除边界。 | 真实生产样本不能由本地 fixture 完全代表。 |
| `RESET-E2E-005` | `partial` | `tests/test_app_health_api.py`、`tests/test_runtime_state_policy.py`、derived lifecycle tests、`web/e2e/settings-data-reset-flow.spec.ts`。 | Browser 已覆盖 reset job 完成后 Settings reload，并继续进入银行明细验证 `bank_detail` fresh empty、进入待找发票验证 `pending_invoice` fresh；真实 worker drain、真实缓存清理和大库多页面最终 fresh 仍需要 staging apply。 |
| `RESET-E2E-006` | `external-risk` | operations docs 和 deploy/data safety runbooks。 | 尚无本地自动化可证明真实 PITR/对象存储恢复。 |

## 当前验证入口

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service tests.test_app_health_api tests.test_background_job_service tests.test_runtime_state_policy -v
cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium
```

## 下一步

1. 准备 staging 数据集，执行一种 reset action 后验证 App Health、dirty/outbox、关键页面 fresh。
2. 将 staging runbook 的真实 worker drain、PITR/对象存储恢复和多页面 fresh 结果回填；本地 Browser mock 只能证明 UI 消费 fresh contract，不能证明真实数据恢复闭环。
