# Runtime 同步 Stage 6 - 受控写操作 E2E Smoke 入口

Stage 5 的生产 audit 已证明当前缺口不是“worker 不能跑”，而是“缺少真实高影响写操作样本”。本阶段新增受控
`write_operation_e2e_smoke` 工具，用于在真实登录态下执行指定 mutating HTTP step，并等待该 step 之后的 durable
outbox/dirty scope 满足写操作 SLO。

## 本地变更

- 新增 `fin_ops_platform.tools.write_operation_e2e_smoke`。
- scenario JSON 描述受控写操作步骤、对应 operation profile 和可选写后首屏 API probe。
- 默认 dry-run：只校验 scenario 并输出计划，不发送 mutating HTTP 请求。
- `--apply` 时必须配置真实认证 header/cookie；没有认证返回 `auth_missing`，不会执行写请求。
- 写步骤成功后，工具用数据库 `clock_timestamp()` 作为起点，只审计该时间之后产生的 read model refresh outbox。
- 写步骤失败时跳过 write SLO 判定，避免把失败操作包装成“已同步”。
- 输出不包含 token、cookie、Authorization header，也不输出 scenario 请求 body。

## Scenario 示例

```json
{
  "scenarios": [
    {
      "name": "turnover-withdraw-smoke",
      "operation": "turnover_manual_closure_or_withdraw",
      "steps": [
        {
          "name": "withdraw",
          "method": "POST",
          "path": "/api/turnover-ledger/relations/<relation_id>/withdraw",
          "json": {"note": "controlled SLO smoke"},
          "expected_statuses": [200]
        }
      ],
      "post_api_probes": [
        {
          "name": "turnover_ledger_grouped",
          "path": "/api/turnover-ledger?view=grouped&page=1&page_size=50",
          "expected_statuses": [200, 202],
          "target_ms": 1000
        }
      ]
    }
  ]
}
```

该示例不是生产可直接运行的命令；`<relation_id>` 必须替换为可控测试对象或已确认可回滚的业务对象。

## 使用方式

dry-run：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario /tmp/finops-write-e2e-scenarios.json \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api
```

apply：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario /tmp/finops-write-e2e-scenarios.json \
  --apply \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --write-target-ms 5000 \
  --http-target-ms 1000 \
  --output /tmp/finops-write-e2e-slo-$(date +%Y%m%d%H%M%S).json
```

## 本地验证

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_e2e_smoke.py tests/test_write_operation_slo_audit.py -q
python3 -m py_compile backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py backend/src/fin_ops_platform/tools/write_operation_slo_audit.py
```

补充 CLI dry-run：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario /tmp/finops-write-e2e-scenario.json \
  --base-url https://example.test \
  --api-prefix /fin-ops-api
```

结果：`tests/test_write_operation_e2e_smoke.py` + `tests/test_write_operation_slo_audit.py` 12 passed；语法检查通过；
CLI dry-run 返回 `status=dry_run`，`scenario_count=1`，且输出不包含请求 body。

## 判定边界

该工具能证明：

- 指定 mutating HTTP step 是否成功。
- step 后产生的 durable outbox/dirty scope 是否覆盖对应 operation profile。
- 写操作 enqueue-to-done 是否在 5 秒目标内。
- 可选写后首屏 API 是否在 1 秒目标内返回。

该工具不能自动选择安全业务对象，也不能替代业务回滚策略。生产执行前必须先确定测试对象、预期副作用和回滚路径。
全 app 闭环仍需要逐个覆盖关联台确认/撤回、往来款闭环/撤回、银行导入确认、发票/OA/ETC 导入确认、标签/规则/设置变更。
