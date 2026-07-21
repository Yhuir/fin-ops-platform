# 关联台 E2E 覆盖

日期：2026-07-22

| Spec | 状态 | 证据 | 合同 |
| --- | --- | --- | --- |
| `RECON-WB-E2E-001` | covered | `web/e2e/workbench-relation-fanout.spec.ts`、`workbench-network-recovery-flow.spec.ts` | 未配对单行选择 -> preview -> 正式 relation -> fresh paired group |
| `RECON-WB-E2E-002` | covered | `web/e2e/workbench-relation-fanout.spec.ts` | confirm 后银行明细重新读取正式 linked 标签 |
| `RECON-WB-E2E-003` | covered | `web/e2e/pending-invoices-fanout.spec.ts` | confirm 后待找发票重新读取正式 linked 状态 |
| `RECON-WB-E2E-004` | covered | `web/e2e/workbench-withdraw-flow.spec.ts` | paired group -> locked withdraw -> fresh singleton unpaired recovery |
| `RECON-WB-E2E-005` | API/integration covered | `tests/test_workbench_relation_grouping.py`、`tests/test_workbench_v2_api.py` | 无 active relation 的历史非正式 metadata 不合并、不隐藏；对象保持 singleton unpaired |
| `RECON-WB-E2E-006` | covered | `web/e2e/workbench-stale-error-flow.spec.ts` | refreshing/stale/failed 不伪装 fresh，false-empty 与写入被阻止 |
| `RECON-WB-E2E-007` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts` | 写失败不移动；写成功而 refetch 失败时明确提示并避免重复写入 |
| `RECON-WB-E2E-008` | covered | `web/e2e/workbench-permissions-flow.spec.ts`、`permissions-role-matrix.spec.ts` | read-export/full/admin 的读取和 mutation gate |
| `RECON-WB-E2E-009` | covered | `web/e2e/workbench-exception-flow.spec.ts` | 未配对异常处理、取消、ignore/unignore 后状态恢复 |
| `RECON-WB-E2E-010` | covered | `web/e2e/workbench-large-scroll-flow.spec.ts` | 首屏 50 组、滚动自动分页、失败停止/显式重试、跨未加载页全量搜索、详情、选择保持和三栏滚动 |
| `RECON-WB-E2E-011` | covered | `web/e2e/workbench-network-recovery-flow.spec.ts` | 网络恢复、重试和幂等提交 |
| `RECON-WB-E2E-012` | covered | `web/e2e/workbench-stale-error-flow.spec.ts`、`workbench-permissions-flow.spec.ts` | App Health/OA dirty 写安全 gate 与只读诊断 |
| `RECON-WB-E2E-013` | covered | `web/e2e/workbench-cash-special-flow.spec.ts` | paired 现金特殊处理写链路及 barrier |

剩余生产风险是实际数据量下的 P95/P99、真实外部 OA 延迟和发布后的全量 rehydrate 时长；由生产 SLO/Audit 处理，不通过增加第三种页面状态规避。
