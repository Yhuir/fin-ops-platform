# server-py:turnover-ledger-route-owner-local-closure-audit

日期：2026-06-25

## 结论

`/api/turnover-ledger*` 的 route-owner 本地闭环已完成为 `analysis-closed`：

- `server.py` 不再定义任何 `_handle_api_turnover_ledger*` route callback。
- `server.py` 只保留一个 delegating dispatch：
  - `self._turnover_ledger_api_routes.route(method, route_path, query, body, headers)`
- 具体 turnover ledger route path 判断和 HTTP mapping 均位于 `TurnoverLedgerApiRoutes.route(...)`。
- 本结论只证明 `server.py` route-owner support 已本地闭合；不声明 turnover ledger 模块全局 closed，也不声明生产 PostgreSQL/worker/App Status/browser/admin/write evidence closed。

## 证据

静态搜索：

```bash
rg -n "def _handle_api_turnover_ledger|_handle_api_turnover_ledger" backend/src/fin_ops_platform/app/server.py
```

结果：无输出。

Route dispatch evidence：

```bash
rg -n "route_path.*turnover-ledger|/api/turnover-ledger" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py
```

结论：

- `server.py` 只命中 delegating dispatch；
- `routes_turnover_ledger.py` 命中 read/export/GET、tag-selection、bank-row-tags、relation-extra、confirm、closure confirm、closure withdraw、relation withdraw 和 relation detail route branches。

Static Guard：

- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

该 Guard 已覆盖 removed handler list：

- `_handle_api_turnover_ledger`
- `_handle_api_turnover_ledger_export_preview`
- `_handle_api_turnover_ledger_export`
- `_handle_api_turnover_ledger_relation`
- `_handle_api_turnover_ledger_relation_extra`
- `_handle_api_turnover_ledger_tag_selection`
- `_handle_api_turnover_ledger_tag_selection_update`
- `_handle_api_turnover_ledger_bank_row_tags_batch`
- `_handle_api_turnover_ledger_relation_extra_update`
- `_handle_api_turnover_ledger_confirm`
- `_handle_api_turnover_ledger_closure_confirm`
- `_handle_api_turnover_ledger_closure_withdraw`
- `_handle_api_turnover_ledger_withdraw`

## 剩余 Application surfaces 分类

### 组合根 / 服务装配

- `_build_turnover_ledger_extra_service(...)`
- constructor 中 `TurnoverLedgerService` / `TurnoverLedgerQueryService` / `TurnoverLedgerApiRoutes` / `TurnoverLedgerReadFacade` 装配。

这些是 composition-root 责任，当前不属于 route callback gap。

### Write facade / request boundary providers

- `_turnover_ledger_tag_selection_write_facade(...)`
- `_turnover_ledger_tag_selection_request_boundary_facade(...)`
- `_turnover_ledger_bank_row_tags_write_facade(...)`
- `_turnover_ledger_bank_row_tags_request_boundary_facade(...)`
- `_turnover_ledger_relation_extra_write_facade(...)`
- `_turnover_ledger_relation_extra_request_boundary_facade(...)`
- `_turnover_ledger_confirm_write_facade(...)`
- `_turnover_ledger_confirm_request_boundary_facade(...)`
- `_turnover_ledger_closure_write_facade(...)`
- `_turnover_ledger_closure_request_boundary_facade(...)`
- `_turnover_ledger_withdraw_write_facade(...)`
- `_turnover_ledger_withdraw_request_boundary_facade(...)`

这些方法负责在 app composition root 组装 local/PostgreSQL builder、legacy fallback、idempotency store、stale precondition port、repository/queue 等依赖。它们不读取 HTTP body/cookie/header，不构造 route response，不直接处理 route path。

### Local runtime support / snapshot compatibility

- `_turnover_ledger_local_runtime_support(...)`
- `_bind_local_turnover_relation_runtime(...)`
- `_bind_local_turnover_ledger_extra_runtime(...)`
- `_replace_local_turnover_relation_snapshot(...)`
- `_save_local_turnover_relations_snapshot(...)`
- `_replace_local_turnover_ledger_extra_snapshot(...)`
- `_save_local_turnover_ledger_extras_snapshot(...)`
- `_turnover_ledger_relation_extra_row_provider(...)`

这些是 local runtime/test compatibility support。它们仍是 turnover-specific app surfaces，但当前不是 route-owner gap；是否进一步下沉应作为后续 local implementation boundary 单独评估，不在本 route-owner closure audit 中扩大。

### Read model / source-version / platform adapter

- `_turnover_ledger_read_model_refresh_producer(...)`
- `_turnover_ledger_export_response(...)`
- `_turnover_ledger_source_versions(...)`
- `_turnover_ledger_stale_reasons(...)`
- `_with_turnover_ledger_source_versions(...)`

这些是 app-level provider/platform adapter 或 source-version helpers。`turnover_ledger` read model refresh producer 已是显式 service boundary；本轮不新增 runtime 代码改动。

### Legacy invalidation / persistence adapters

- `_after_turnover_relation_mutation(...)`
- `_turnover_ledger_relation_mutation_invalidation_adapter(...)`
- `_persist_turnover_relations_best_effort(...)`
- `_persist_turnover_ledger_extras_best_effort(...)`

这些被 legacy fallback adapter 或 local runtime support 使用，保留为兼容/provider surface。它们不是 HTTP route callback，但仍是 future cleanup candidate；后续若要继续下沉，应先做单独 impact audit。

### Workbench source-version providers

- `_turnover_relation_snapshot_for_workbench(...)`
- `_active_turnover_relations_for_workbench(...)`

这些用于 Workbench source-version/snapshot compatibility，不属于 turnover route ownership。

## 下一步选择

本轮不新增运行时代码。下一步选择 `planning:post-turnover-ledger-route-owner-next-boundary-selection`，原因：

- turnover ledger route-owner support 已局部闭合；
- 继续在 turnover ledger 内部下沉 local runtime/support helpers 需要单独比较收益和风险；
- T0 应回到全局 `server.py` residual route/support queue，选择下一条最高风险安全本地边界，而不是凭本轮 audit 直接声明 module/global closure。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- 本 audit 未声明 turnover ledger module/global closure。
- Future cleanup candidates 包括 legacy fallback invalidation/persistence adapter、local runtime support helpers 和 broader `server.py` support surfaces。
