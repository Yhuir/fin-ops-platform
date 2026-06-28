# Canonical Facts E2E 覆盖

本模块不维护独立 E2E case。覆盖关系由各 owner 模块的 `e2e-coverage.md` 记录。

## 当前覆盖要求

| Spec ID | 覆盖位置 | 当前状态 |
| --- | --- | --- |
| `CF-IMPORT-001` | 对应导入模块 E2E/API/integration 覆盖 | owner 模块维护 |
| `CF-REL-001` | 关联台和关系模块 E2E/API/integration 覆盖 | owner 模块维护 |
| `CF-TAG-001` | 银行明细模块 E2E/API/integration 覆盖 | owner 模块维护 |
| `CF-LIFECYCLE-001` | 待找发票、销项收款、OA 待付款等模块覆盖 | owner 模块维护 |

## 缺口处理

如果后续 canonical fact owner 收口跨多个模块，必须在实施模块的 `e2e-coverage.md` 中登记覆盖或缺口，不能只在本治理模块记录。
