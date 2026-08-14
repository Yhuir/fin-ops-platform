# Read Model 退役模块

- Module key: `read-models`
- 状态: retired
- 当前运行时集合: empty

本目录现在是删除合同和防回归入口，不再描述一个可运行模块。App 页面统一通过页面专属 API 直接读取
canonical PostgreSQL facts 与 active 正式关系。

## 当前闭环

- 生产 registry 仅包含 `oa-sync`、`workbench-matching`、`import`、`settings-maintenance` 四个 worker。
- `workbench-matching` 是领域计算；通用 outbox/attempt/heartbeat 是任务基础设施。
- Migration `0149_remove_read_model_runtime.sql` 删除 dirty-scope 表和 projection schema。
- 部署精确退役旧 worker、env、timer 和 helper，并禁止 forward-only migration 后自动回滚到旧 release。
- 负向事件审计拒绝任何新 `%.read_model.refresh`。

## Public surface

无。禁止新增 manifest、gateway、scope、freshness、readiness、projection repository 或 refresh worker。

若未来 direct canonical query 确有无法通过 SQL、索引、分页和 HTTP cache 解决的实测瓶颈，必须作为新的架构
决策单独评估；不能复活本模块或复制旧代码。

## 维护入口

- 边界：`boundary-io.md`
- 全局合同：`docs/architecture/module-boundaries/read-model-contracts.md`
- Worker：`docs/modules/runtime-workers/boundary-io.md`
- 生产治理：`docs/operations/runtime-worker-governance.md`
- 删除防回归：`tests/test_read_model_runtime_removal.py`
