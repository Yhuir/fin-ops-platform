# Canonical Facts 测试矩阵

本模块本轮只补文档和边界合同，没有新增运行时代码。后续任何代码重构如果改变 canonical fact owner、写入口、读入口、affected diagnostics、真实后台任务或禁止路径，必须按影响面补测试。

## 七类测试适用性

| 类别 | 当前是否适用 | 说明 |
| --- | --- | --- |
| 1. Business core unit tests | 后续代码变更适用 | owner 模块业务状态机、金额、匹配、幂等、权限或冲突规则变化时必须覆盖。 |
| 2. Service-layer tests | 后续代码变更适用 | command service、repository、UoW、affected diagnostics、audit、outbox/job、rollback 或 partial failure 变化时必须覆盖。 |
| 3. API contract tests | 后续 API 变更适用 | 写 API 或读 API response shape、affected scope/job diagnostics、error/status 字段变化时必须覆盖。 |
| 4. Read model/cache/background job tests | 后续影响 cache/background/legacy guard 时适用 | canonical write 影响 list、summary、workbench、ledger、tax 等页面时必须覆盖 direct payload、cache warmup 或真实后台任务收敛；legacy read model 只覆盖 no-restore/delete guard，Search 只验证 direct `/api/search` payload，不恢复 refresh worker。 |
| 5. Frontend component/interaction tests | 后续页面变更适用 | 页面读写 canonical facts、写后 direct refetch 或错误反馈行为变化时必须覆盖。 |
| 6. E2E business-flow integration tests | 跨模块重构适用 | import -> confirm -> worker -> page、relation confirm -> downstream pages 等跨模块链路变化时必须覆盖至少一条关键路径。 |
| 7. Existing feature regression tests | 总是评估 | owner 收口可能影响旧页面、旧 API、legacy read model guard、旧导出、旧权限和真实 worker。 |

## 当前文档验证

文档变更至少运行：

```bash
git diff --check
bash scripts/verify.sh docs
```

如果 `scripts/verify.sh docs` 不存在或环境不可用，改跑仓库已有的最小文档/Markdown 校验，并在最终说明中写清原因。

## 后续重构建议测试入口

- Legacy read model guard：`tests/test_read_model_manifest.py`、`tests/test_read_model_architecture_guards.py`
- Runtime/worker 合同：`tests/test_runtime_worker_registry.py`
- 生产边界 guard：`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_architecture_guards.py`
- 各 owner 模块测试：以对应 `docs/modules/<owner>/tests.md` 为准。
