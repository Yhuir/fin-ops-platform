# Phase 26 完成状态复核

日期：2026-07-25

## 结论

Phase 26 已完成，不是 Phase 27 发布前需要重新实现的前置工作。此前未闭环的是 `.planning/ROADMAP.md`、`.planning/STATE.md` 与 `.planning/REQUIREMENTS.md` 的状态记录，而不是当前代码链路。

本次复核只修正文档台账，不重做已验证的业务代码。Phase 27 必须继续保护 Phase 26 的冻结 requirement、关系 ownership、可逆 fixture 和 Audit 合同。

## 代码与计划证据

| 计划 | 当前状态 | 主要提交证据 | 不重复工作的边界 |
| --- | --- | --- | --- |
| `26-01` | complete | `978da7857`、`358a06ed3` | turnover ownership/completion 分离、真实规则快照、selected-member invariant 与旧 resync 删除保持不变 |
| `26-02` | complete | `46db03f1a`、`1dbb6276b`、`6d18ca1f8`、`2a5d65d02`、`48e449d47` | 可逆 requirement repair、Workbench v6 与 partial-missing fail closed 不重写 |
| `26-03` | complete | `08479c073` | invoice-lifecycle → pending-invoice 合法 scope 展开已修复，不再生成 bare month scope |
| `26-04` | complete | `83b6c5396` | invoice/ETC import Audit 的 legacy provenance 与合法 terminal lifecycle 分类已收敛 |
| `26-05` | complete | `a82c169e5`，并由 `a1c8f061a`、`f2a0780cf` 的生产 fixture/recovery 门禁补强 | bank-only Turnover 时间推进不再制造 invoice Audit 假阳性；真实 invoice drift 继续 fail closed |

`26-06` 至 `26-08` 提交标签是生产验证期间的后续门禁修复，并非缺失的新计划：它们把 restore point 改为可选/可删除、限制 recovery freshness 耗时并收窄 invoice relation Audit。当前授权的 test-owned 可逆 fixture 依赖 audited fixture recovery 与 release rollback，不创建额外数据库备份。

## Phase 27 继承的不变量

- `turnover_manual_closure` active relation 只表达 ownership；paired/unpaired 由冻结 OA/发票 requirement 决定。
- 规则保存不追溯改写既有 relation metadata。
- confirm/withdraw 必须使用 test-owned、可恢复 fixture，最终状态为 inactive。
- Workbench v6 active generation 与 source proof 必须 fail closed；Phase 27 只改变页面 freshness 收敛时机，不改变 Phase 26 业务口径。
- 生产验证失败不得用旧 resync、直接 SQL、额外 fan-out 或兼容 fallback 绕过。

## 剩余工作

Phase 26 无剩余实现项。当前唯一剩余工作属于 Phase 27-07：提交并部署 exact candidate，完成一次完整生产性能/正确性矩阵并恢复 fixture。
