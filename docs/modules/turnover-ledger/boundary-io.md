# 外部往来款管理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：外部往来款页面读取 `turnover_ledger` read model；写操作通过 write facade/UoW/adapters 进入 scoped dirty projection。
- 当前缺口：read facade 位于 `app/` 下，历史 write adapters 和 service 边界仍需继续收敛。
- 旧代码删除条件：旧 direct write/read paths 不再被 API、测试或工具引用，confirm/withdraw/recovery 全链路通过。

## 职责边界

### 负责

- 外部往来款列表、确认关联、撤回、导出、余额/账期查询。
- `turnover_ledger` read model。
- 与银行流水、关联台关系事实源之间的 write/read adapter。

### 不负责

- 不拥有银行流水源事实。
- 不直接维护 workbench relation 表。
- 不绕过 write UoW 直接更新 turnover source versions。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TurnoverLedgerPage.tsx`、`features/turnoverLedger/api.ts` | 进入 query service/read facade |
| 确认/撤回写操作 | write facade/UoW | 触发 turnover/workbench_relation/bank scopes |
| Refresh scope | `turnover_ledger` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | query gateway 后 fresh/status |
| 写操作结果 | API/frontend operation barrier | 可审计、幂等或有版本保护；返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Dirty scope | runtime queue | `turnover_ledger.read_model.refresh` |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Read model：`turnover_ledger`
- Projection：`partitioned_scoped_incremental`
- Worker：`turnover-ledger`
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：`TurnoverLedgerReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` |
| Frontend feature/components | `web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`、`backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py` |
| Backend service | `turnover_ledger_service.py`、`turnover_relation_service.py`、`turnover_ledger_query_service.py`、`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py` |
| Repository / SQL | `turnover_ledger_read_model_repository.py`、`turnover_ledger_sql_projection.py` |
| Worker/read model | `turnover_ledger_read_model_refresh.py`、`turnover_ledger_read_model_refresh_producer.py`、`turnover_ledger_source_versions.py` |
| Tests | `tests/test_turnover_*.py`、`web/src/test/TurnoverLedger*.test.*`、`web/e2e/turnover-ledger-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank row version provider, workbench relation adapters, read model query gateway。
- 必须通过：TurnoverLedgerQueryService for reads, write facade/UoW for writes。
- 禁止绕过：直接操作数据库确认/撤回；API 返回 stale payload as fresh。

## 测试与验证

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/e2e/turnover-ledger-flow.spec.ts`

## 当前缺口和删除条件

- 读 facade 从 `app/` 下继续迁移前，先补测试保护。
- 方式 B 可控样本验证必须通过业务操作，不直接数据库写。
