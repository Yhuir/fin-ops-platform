# 外部往来款管理 Spec-first E2E Spec

本文件定义 `/turnover-ledger` 的用户可观察业务合同。实现细节以 `boundary-io.md` 为准。

## 用户角色

- `admin`：读取、导出、标签设置、extra、确认和撤回。
- `read_export_only`：读取和导出，不能 mutation。

## 验收场景

| Spec ID | 场景 | 优先级 | 合同 |
| --- | --- | --- | --- |
| `TURNOVER-E2E-001` | 首次访问/刷新/失败重试 | P0 | 每次 load 直接读取一个 canonical snapshot；成功显示完整 grouped rows/statistics，空结果是真空，失败显示错误且普通刷新可恢复 |
| `TURNOVER-E2E-002` | 标签设置保存 | P0 | 保存 canonical settings/version/audit；当前页只重跑一次 GET，零 Turnover refresh job |
| `TURNOVER-E2E-003` | 外部往来确认闭环 | P0 | 同组至少一收一支且差额零；按钮立即 submitting；成功写 active canonical pair relation，当前页重载后两侧显示同一闭环 case |
| `TURNOVER-E2E-004` | 关联台反向确认 | P0 | 关联台确认的 active bank pair 在外部往来款下一次刷新时显示同一 case/闭环 tag |
| `TURNOVER-E2E-005` | 撤回恢复 | P0 | 从任一合法入口撤回 active case 后，两页各自手动刷新都不再显示 active pair；可恢复的 OA-bank 历史关系按既有 command 合同恢复 |
| `TURNOVER-E2E-006` | Workbench/OA 合并边界 | P0 | 仅允许既有 `{oa, bank}` relation 合并；包含 invoice/其它 type 时 fail closed 并提示转关联台 |
| `TURNOVER-E2E-007` | 旧投影隔离 | P0 | 历史 Turnover projection 即使残留错误/旧行，也不得改变页面响应；API 不返回 projection freshness metadata |
| `TURNOVER-E2E-008` | relation extra | P1 | expected version 校验、canonical 保存、当前页一次 GET；失败不半写 |
| `TURNOVER-E2E-009` | 导出与权限 | P1 | 导出复用 direct query/筛选/权限；超限结构化失败；只读角色零 mutation |
| `TURNOVER-E2E-010` | 生产运行边界 | P0 | confirm/withdraw 后不产生 `turnover_ledger.read_model.refresh` 或 dirty scope；无 Turnover worker registration；Audit pass；记录 GET 和写操作耗时 |

## 交互合同

- GET loading、empty、error、retry 必须可区分。
- confirm/withdraw 点击后立即 disabled 并显示进行中，禁止出现“像没点到”。
- canonical write 成功、随后页面 GET 失败时，提示“操作已成功，页面重新加载失败”；不能弹“操作失败”。
- 另一个页面或 tab 不自动刷新。它在自己的手动刷新/重新访问时读取新事实。
- 不监听 focus/visibility/BFCache，不轮询 App Status，不使用 operation barrier 等待 Turnover 页面。

## 生产 fixture

- 只使用明确标记 `test-owned`、可确认并可撤回恢复的一收一支银行流水。
- 先记录 case/members/category/version 和 queue baseline。
- 执行 confirm → 外部往来刷新 → 关联台刷新 → Audit/queue 检查 → withdraw → 两页恢复检查。
- 任一步失败先记录整条链路证据；不在验证过程中逐问题部署。
