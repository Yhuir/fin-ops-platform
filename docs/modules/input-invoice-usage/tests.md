# 进项发票使用情况 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | - | 本次未改变支付状态、金额、生命周期或权限业务规则。 |
| 2. Service-layer tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py` | 覆盖 `PostgresReadModelRepository.list_input_invoice_usage_rows` 的 all scope source_versions 聚合。 |
| 3. API contract tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py` | 覆盖 `/api/input-invoice-usage/rows` 在 all scope 基础版本 fresh 时返回 `200/fresh/rows`，source version 缺失时仍返回 `202/refreshing`。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_read_model_freshness.py` | 覆盖 read model scope freshness、source version mismatch 和 all scope worker 展开。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/InputInvoiceUsagePage.test.tsx` | 覆盖页面 fresh rows、refreshing 空 rows、空态和表格渲染契约。 |
| 6. End-to-end business-flow integration tests | 不适用 | - | 本次只修复已构建 read model 的 all scope 读取判定，没有改 import、OA、workbench 写入或 worker 生成链路。 |
| 7. Existing feature regression tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` | 保护 output/oa 同仓储行为、输入发票页面既有 API shape 和前端加载/空态行为。 |

## 现有验证命令

```bash
# 后端 read model / API 回归
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v

# 前端页面回归
cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx

# 全量前端构建，发布前或触及前端代码时运行
cd web && npm run build
```

## 未测风险

- 本地单元测试覆盖 all scope 判定与页面契约；生产环境仍需在部署后通过只读查询确认 `/api/input-invoice-usage/rows` 默认查询返回 `read_model_status=fresh` 且 `pagination.total` 大于 0。
