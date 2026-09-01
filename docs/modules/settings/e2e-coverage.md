# 设置 E2E 覆盖

| Spec ID | 状态 | 自动化证据 |
| --- | --- | --- |
| `SETTINGS-E2E-001` | covered | settings service/API/component tests、既有 settings Browser flow |
| `SETTINGS-E2E-002` | covered | admin API tests、`SettingsPage.test.tsx`、`permissions-role-matrix.spec.ts` |
| `SETTINGS-E2E-003` | covered | `SettingsPage.test.tsx` 与 Browser matrix 的 OA 搜索→新增→checkbox→保存→session 切换 |
| `SETTINGS-E2E-004` | covered | app settings/state store/PostgreSQL integration tests |
| `SETTINGS-E2E-005` | covered-local | OA role sync/preflight/deploy tests；真实 OA topology 由发布前后 preflight 证明 |
| `SETTINGS-E2E-006` | covered | OA applicant credential service/API/repository/frontend tests |
| `SETTINGS-E2E-007` | covered-local | data reset service/API/frontend/E2E；本次权限改造不执行生产数据重置 |

新增 settings section 时先判断它属于普通 settings 页面能力还是 005 control plane；禁止重新引入账号操作层级。
