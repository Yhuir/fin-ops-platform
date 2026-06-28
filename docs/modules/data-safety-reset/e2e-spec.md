# Data Safety Reset Spec-first E2E Spec

数据安全与重置是危险跨模块功能。Spec-first E2E 目标不是证明按钮能点，而是证明管理员权限、OA 密码复核、protected targets、后台 job、App Health 和多页面 direct API 收敛都闭环。

## Spec IDs

| Spec ID | 用户/运维可观察合同 | 必须证明 |
| --- | --- | --- |
| `RESET-E2E-001` | 非 admin 或密码错误不能触发 reset，响应和 job payload 不泄露密码。 | API/前端/权限矩阵测试。 |
| `RESET-E2E-002` | 管理员发起 reset 前必须看到影响确认，并可取消。 | Settings Browser flow。 |
| `RESET-E2E-003` | reset job create/poll/active recovery 可用，页面离开后可恢复进度。 | job API + Settings UI。 |
| `RESET-E2E-004` | reset 后 protected targets 保留，目标数据按 action 删除，失败可诊断。 | service/API tests。 |
| `RESET-E2E-005` | reset 完成后受影响 cache/worker/direct API 不显示旧数据；App Health 暴露 running/failed/partial。 | lifecycle/runtime/App Health tests。 |
| `RESET-E2E-006` | 真实 staging/production 备份、PITR/restore、对象存储和后台任务收敛可完成。 | staging runbook/smoke；本地不能替代。 |

## 外部风险

真实 PostgreSQL PITR、对象存储快照恢复、Redis/RabbitMQ/systemd 后台任务收敛、大生产库 reset 耗时和真实 OA 重建都必须在 staging/生产前 smoke 中证明。
