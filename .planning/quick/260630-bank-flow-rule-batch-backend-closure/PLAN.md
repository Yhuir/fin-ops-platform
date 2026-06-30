# 流水规则批量处理后端闭环 GSD 执行计划

日期：2026-06-30

## 目标

将 `bank_flow_rule_batch` 从旧 `no_oa_bank_batch` 后端链路中拆出，形成生产可运行的独立 API / read model / worker / freshness 边界。新链路不得通过 no-OA route、no-OA freshness alias、no-OA refresh event 或 no-OA refresh producer 执行。

## 范围

1. 新增 `bank_flow_rule_batch` 独立 read model registry、manifest、scope policy、worker registration 和 RabbitMQ dispatch event。
2. 新增 bank-flow 专用 HTTP route，server dispatch 不再把 `/api/bank-flow-rule-batches/*` 交给 `NoOaBankBatchApiRoutes`。
3. 新增 bank-flow refresh producer 与 refresh service event/scope 支持，确保 enqueue、worker completion、operation barrier 都使用 `bank_flow_rule_batch`。
4. 新增 bank-flow read repository port methods，API 查询不再声明 no-OA read repository contract。
5. 删除 no-OA route 内的 bank-flow 分支，新增测试守卫旧 alias 不可回流。
6. 更新模块边界、read model 合同、运行 worker 文档。

## 非目标

1. 本次不删除仍然存在的“免OA批次”业务域本身；该业务域仍有独立页面/API/测试。删除目标是 bank-flow 新链路对 no-OA 旧链路的依赖。
2. 本次不做无迁移保护的物理表拆分；先建立独立逻辑 read model key、event、scope、worker 和 repository port。物理存储仍由现有持久化能力承载，并通过 `relation_mode` 隔离。

## 验收标准

1. `OperationFreshnessTarget("bank_flow_rule_batch")` 解析到 `scope_type="bank_flow_rule_batch"` 和 worker `bank-flow-rule-batch`，不再读取 no-OA readiness。
2. `/api/bank-flow-rule-batches/*` 只由 `BankFlowRuleBatchApiRoutes` 分发，`routes_no_oa_bank_batches.py` 不再包含 bank-flow 路由分支。
3. bank-flow mutation/read 刷新 enqueue 使用 `bank_flow_rule_batch` scope/event；no-OA producer 只发 no-OA scope/event。
4. `READ_MODEL_MANIFEST`、app status registry、scope policy、runtime worker registry、RabbitMQ dispatch event 对 `bank_flow_rule_batch` 一致。
5. 测试覆盖 API route 边界、refresh producer、operation barrier、manifest/worker 注册和旧 alias 防回流。

## Wave 2/3 执行结果

1. 新增中性 `bank_batch_application_service.py`、`bank_batch_service.py`、`bank_batch_read_model_refresh.py` 和 `bank_batch_read_model_repository.py`；bank-flow service/refresh 不再继承或 import no-OA application/refresh 模块。
2. `BankFlowRuleBatchApplicationService.persist_mutation(...)` 走 `save_bank_flow_rule_batch_mutation(...)`；refresh persistence 走 `save_bank_flow_rule_batches_scope(...)` / `save_bank_flow_rule_batches(...)`。
3. `Application` 和 worker 为 bank-flow 构造独立 `BankBatchService` 实例、独立 route、独立 producer 和独立 worker handler；no-OA handler 只服务 legacy no-OA API。
4. 新增静态守卫：bank-flow runtime 文件禁止 import no-OA 模块边界；server/worker bank-flow wiring 禁止注入 no-OA service/repository/persistence 参数。
5. 文档事实源同步为 `implemented-independent-io` / `covered-independent-io`。

## 剩余风险

1. 物理表名仍是历史批次存储兼容层；当前通过 bank-flow 命名 IO adapter 和 `relation_mode=bank_flow_rule_batch` 隔离。若要删除历史物理表名，需要单独 schema migration、数据迁移、回滚和生产 repair 方案。
2. 受控 `rebaseline-no-oa` dry-run/apply 仍作为迁移工具保留；它不是普通 bank-flow 查询/提交/刷新链路。
