# Prompt 62: 税金抵扣后端月度缓存、指标与预热

## 背景

税金抵扣页面主要读取：

- `GET /api/tax-offset?month=YYYY-MM`
- `POST /api/tax-offset/calculate`
- `POST /api/tax-offset/certified-import/preview`
- `POST /api/tax-offset/certified-import/confirm`

当前 `TaxOffsetService.get_month_payload(month)` 会构建当月快照，来源包括：

- 已导入发票：`ImportNormalizationService.list_invoices()` 后在 `TaxOffsetService._build_month_data_from_imported_invoices(month)` 内按 `invoice_date.startswith(month)` 过滤。
- OA 附件发票：`oa_attachment_invoice_rows_loader(month)`。
- 已认证结果：`TaxCertifiedImportService.list_records_for_month(month)`。

该路径没有成本统计那种 `month=all` 跨多月 explorer，但在发票数量增长后，单月请求仍会因为每次全量扫描发票而变慢。因此本 prompt 同时完成短期生产保障和中期 read model 方案。

## 必须完成

1. 接口结构化耗时日志。
   - `GET /api/tax-offset`
   - `POST /api/tax-offset/calculate`
   - 日志使用结构化 JSON `print(..., flush=True)`，参考现有 `workbench_action_timing` 和 `cost_statistics_explorer_metric`。
   - 不输出发票明细、OA 明细或原始上传内容。

2. 避免 `TaxOffsetService._build_month_data_from_imported_invoices` 每次扫描全量发票。
   - 为 `ImportNormalizationService.list_invoices()` 的结果建立服务内月度索引或月度缓存。
   - 缓存 key 至少包含 `month`。
   - 支持显式清理：`TaxOffsetService.clear_month_cache(months: list[str] | None = None)`。
   - 如果无法判断精确月份，可清全量。

3. 新增 `TaxOffsetReadModelService`。
   - 按 `month` 缓存完整 `get_month_payload(month)` 结果。
   - schema version 过滤旧缓存。
   - 支持 deep copy、snapshot、snapshot_scope_keys、upsert、delete、invalidate_months、clear、metadata。
   - 不缓存 `/calculate` 的交互结果。

4. 持久化 `TaxOffsetReadModelService`。
   - local pickle key：`tax_offset_read_models`。
   - Mongo detailed collections：
     - `tax_offset_read_models_meta`
     - `tax_offset_read_models`
   - 支持 `changed_scope_keys` 增量 replace/delete。
   - 接入 `ApplicationStateStore.load()` 和 `save()`。

5. API 使用 read model。
   - `GET /api/tax-offset?month=YYYY-MM` 先查 read model。
   - cache hit 直接返回 month payload。
   - cache miss 调 `TaxOffsetService.get_month_payload(month)`，写 read model 并持久化，再返回。
   - 输出指标：
     - `kind="tax_offset_month_metric"`
     - `metric="tax_offset.month.duration_ms"`
     - `month`
     - `cache_hit`
     - `duration_ms`
     - `output_count`
     - `input_plan_count`
     - `certified_count`
     - `timestamp`

6. `POST /api/tax-offset/calculate` 输出指标。
   - 不使用 read model 存最终 calculate 结果。
   - 可以内部复用 `TaxOffsetService` 的月度 snapshot/cache。
   - 输出指标：
     - `kind="tax_offset_calculate_metric"`
     - `metric="tax_offset.calculate.duration_ms"`
     - `month`
     - `selected_input_count`
     - `duration_ms`
     - `timestamp`

7. 精确失效。
   - 发票导入确认/撤回：按 normalized rows 的 `invoice_date[:7]` 失效。
   - 税金认证结果导入 confirm：按 `TaxCertifiedImportBatch.months` 失效。
   - OA 附件发票缓存更新：按 callback months 失效。
   - 设置数据重置：全量清。
   - 每次 read model 失效时，也要调用 `TaxOffsetService.clear_month_cache(...)` 清服务内月度索引/cache。

8. 后台预热。
   - 复用 `BackgroundJobService`，不新增独立 worker 进程。
   - job type：`tax_offset_cache_warmup`。
   - 预热是可选能力，必须通过 `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED=1` 显式开启。
   - 开启后，confirm/导入/失效会预热受影响月份。
   - 全量清理后可额外预热当前月和上月。
   - job 幂等，避免重复创建。
   - 预热失败不得破坏旧缓存；只有单月 payload 构建成功后才 upsert。

## 不做

- 不新增独立后端 worker 进程。
- 不改税金抵扣业务口径。
- 不缓存 `/calculate` 的每种选择组合。
- 不改前端 UI。

## 拆分任务

### 子任务 A: TaxOffsetReadModelService + state_store

写入范围：

- `backend/src/fin_ops_platform/services/tax_offset_read_model_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `tests/test_tax_offset_read_model_service.py`
- `tests/test_state_store.py`

验收：

- read model 按 `month` 保存完整 payload。
- schema version 不匹配时丢弃旧缓存。
- local pickle 和 Mongo detailed collection 都能保存/加载。
- `changed_scope_keys` 支持增量 replace/delete。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_read_model_service tests.test_state_store
```

### 子任务 B: TaxOffsetService 月度索引/cache

写入范围：

- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `tests/test_tax_offset_service.py`

验收：

- 同一个 month 的重复构建不重复扫描全部 invoices。
- 不同 month 缓存隔离。
- `clear_month_cache([month])` 只清对应月份。
- `clear_month_cache()` 清全量。
- 现有 OA 附件发票和认证匹配口径保持不变。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service
```

### 子任务 C: Application/API 接入、失效、预热和指标

写入范围：

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_tax_offset_api.py`
- 必要时少量调整 `tests/test_import_api.py` 或其他导入相关测试

验收：

- `/api/tax-offset` cache hit 不调用 `TaxOffsetService.get_month_payload`。
- cache miss 构建、写 read model、持久化。
- `/api/tax-offset/calculate` 输出结构化耗时日志。
- 认证导入 confirm 按 batch months 清 read model 和服务内 cache。
- 发票导入确认/撤回按月份清 read model 和服务内 cache。
- OA 附件发票缓存更新按月份清 read model 和服务内 cache。
- `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED=1` 时，失效后创建/复用 `tax_offset_cache_warmup` 后台任务；默认不开启时不产生后台预热副作用。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api tests.test_import_api tests.test_background_job_service
```

### 集成验证

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_read_model_service tests.test_tax_offset_service tests.test_tax_offset_api tests.test_state_store tests.test_import_api tests.test_background_job_service
cd web && npx vitest run src/test/App.test.tsx
git diff --check
```
