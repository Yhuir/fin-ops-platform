# 外部往来款管理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：外部往来款页面通过 turnover ledger direct API 读取 grouped data；后端不再使用 turnover 页面 read model，前端不消费页面级同步状态，也不等待 legacy operation barrier。
- 当前缺口：read facade 位于 `app/` 下，历史 fallback adapters 仍需继续收敛；正常 write facade/UoW 路径不得再使用 `turnover_ledger:all` 作为默认刷新范围。
- 旧代码删除条件：旧 direct write/read paths 不再被 API、测试或工具引用，confirm/withdraw/recovery 全链路通过。

## 职责边界

### 负责

- 外部往来款列表、确认关联、撤回、导出、余额/账期查询。
- direct grouped payload 和外部往来写操作前端消费。
- 与银行流水、关联台关系事实源之间的 write/read adapter。

### 不负责

- 不拥有银行流水源事实。
- 不直接维护 workbench relation 表。
- 不绕过 write UoW 直接更新 turnover source versions。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TurnoverLedgerPage.tsx`、`features/turnoverLedger/api.ts` | 进入 query service/read facade |
| 确认/撤回写操作 | write facade/UoW | 已知 affected months 的写路径触发 turnover/workbench/workbench_relation/cost affected month scopes；Search 不进入 dirty/outbox，通过 direct `/api/search` payload 反映；未知月份例外才允许 `all` fan-out |
| Affected scope diagnostics | turnover write facade / UoW | month or `all`；`all` 只作为诊断/fan-out 例外，不是普通写操作默认收敛条件 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | direct grouped payload；不包含页面级旧同步字段 |
| 写操作结果 | API/frontend direct refresh | 可审计、幂等或有版本保护；页面写成功后直接重读 grouped ledger；后端仅返回 affected scope keys，不再返回 legacy target envelope |
| Affected scope diagnostics | API / runtime diagnostics | 不再输出 turnover page refresh；仅用于下游 direct API、operation projection 或真实后台任务诊断 |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Page projection：已从 active manifest/App Status/worker lane 和 SQL row storage 移除
- Projection：无 turnover page projection；页面读取只走 direct query
- Worker：无 turnover 专用页面刷新 worker
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：direct service/repository facts；无 turnover read-model repository port

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` |
| Frontend feature/components | `web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`、`backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py` |
| Backend service | `turnover_ledger_service.py`、`turnover_relation_service.py`、`turnover_ledger_query_service.py`、`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py` |
| Repository / SQL | direct facts repositories used by `TurnoverLedgerService` / write adapters |
| Runtime/source version | `turnover_ledger_source_versions.py`；无 turnover page projection worker |
| Tests | `tests/test_turnover_*.py`、`web/src/test/TurnoverLedger*.test.*`、`web/e2e/turnover-ledger-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank row version provider, workbench relation adapters, direct query service/read facade。
- 必须通过：TurnoverLedgerQueryService for reads, write facade/UoW for writes。
- 禁止绕过：直接操作数据库确认/撤回；写操作绕过 expected_versions 或后端 stale precondition；恢复 turnover page read-model repository/projection。

## 测试与验证

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_query_service.py`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/e2e/turnover-ledger-flow.spec.ts`

## 当前缺口和删除条件

- 读 facade 从 `app/` 下继续迁移前，先补测试保护。
- 方式 B 可控样本验证优先通过业务操作恢复；若生产样本没有业务恢复路径，可按用户批准的 bounded DB restore protocol 使用精确 predicate 恢复到操作前快照，不得通过 DB 伪造页面同步状态。
