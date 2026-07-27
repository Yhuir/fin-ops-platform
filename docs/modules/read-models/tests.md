# Read Model 测试矩阵

> 当前模块只测试三个共享 read model，以及已退役页面链路不能回归。旧 14 项页面
> read-model 矩阵已删除；历史实现可从 Git history 查阅，不再复制到当前合同。

## 当前不变量

1. Manifest、scope policy、App Status registry 和带 `read_model_key` 的 worker registration
   精确等于 `workbench_relation`、`search`、`no_oa_bank_batch`。
2. 已退役页面没有 projector、producer、refresh service、worker handler、RabbitMQ event、
   deploy env、App Status readiness 或前端 freshness/polling。
3. canonical 页面 GET 不读取 projection/cache/queue，不返回 read-model runtime 字段；
   缺少 canonical repository 时 fail fast。
4. 三个共享 projection 仍通过 gateway、durable queue、freshness proof 和登记 worker
   闭环；`all` 只作 fan-out command。
5. 历史 migration/table 只供回滚，不能被当前生产代码或测试 fixture 当作事实源。

## 七类测试

| 类别 | 适用性 | 当前入口与责任 |
| --- | --- | --- |
| 1. 业务核心单元 | 间接适用 | 各 canonical 页面模块测试保护筛选、金额、关系、状态与写入业务规则；本模块不重复测试页面规则 |
| 2. Service / repository | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、三个共享 projection 的 service/repository tests |
| 3. API contract | 适用 | 各页面 API tests 断言 canonical response shape，并断言 retired status/scope/version/job/barrier 字段缺失 |
| 4. Read model / cache / worker | 核心适用 | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker.py`、`tests/test_read_model_freshness.py` |
| 5. 前端交互 | 适用 | 各 canonical 页面 tests 覆盖 loading/empty/error/result、筛选/分页/写后 normal GET，并禁止 freshness polling |
| 6. 端到端业务流 | 适用 | Browser E2E 覆盖目标页面读取、关键写后重读与跨页面 canonical relation 可见性 |
| 7. 既有功能回归 | 核心适用 | 全量 backend/frontend/build/E2E，加静态负向合同保护其它页面、三个共享 read model、import/OA/matching jobs |

## 关键测试入口

- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_read_model_query_gateway.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_page_read_model_fact_display_matrix.py`
- `tests/test_write_operation_impact_matrix.py`
- `tests/test_deploy_runtime_examples.py`
- `tests/test_postgres_migrations.py`

各页面的业务和交互测试归对应 `docs/modules/<module>/tests.md`，本文件不维护第二份
页面清单。

## 必须保留的负向断言

- retired `*.read_model.refresh` event、scope type、worker instance、env 示例和 RabbitMQ
  dispatch 不存在。
- `workbench` active generation/status/cache/SSE runtime 不存在；公开 canonical payload
  会递归剥离历史 generation/read-model 字段。
- retired page source/reason 不能进入 refresh gateway active-coalescing 列表。
- 页面 API/frontend 不出现 `read_model_status`、`source_versions`、`refresh_enqueued`、
  `freshness_targets`、`operation_barrier_targets`。
- deploy preflight 在 retired processing work 存在时拒绝激活新 release，但不恢复旧 worker。
- migration `0127` 不 DROP 历史表、不改写旧 queue/readiness，保证上一版本可回滚。

## 验证命令

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh docs
git diff --check
```

涉及部署前还必须运行 Browser E2E，并在生产使用只读 smoke 验证：

- 十个目标页面及成本统计、外部往来均由 canonical snapshot 返回。
- 三个共享 read model queue/readiness/worker 正常。
- retired worker instance 不运行，retired event/dirty scope 没有 processing。

## 未测风险

- 无 `FIN_OPS_TEST_DATABASE_URL` 时，真实 PostgreSQL integration tests 会跳过；本地 fake
  不能替代生产 schema、数据量与执行计划。
- 本地回归不能证明生产旧 worker 已停止或历史 processing backlog 已清空；部署 preflight
  和生产只读 smoke 必须在发布窗口执行。
