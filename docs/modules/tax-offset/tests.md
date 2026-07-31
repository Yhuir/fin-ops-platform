# 税金抵扣测试矩阵

日期：2026-07-27

## 2026-07-31 认证结果 rail 回归

- `web/src/test/TaxOffsetPage.test.tsx` 保护 complementary rail 常驻、toggle `aria-controls/aria-expanded`、折叠内容 `inert/aria-hidden/pointer-events`、transform/opacity-only 和 reduced-motion；不得回归 grid/width 动画。
- 本次只改变前端展示动效，适用第 5 类 frontend interaction 与第 7 类 existing regression；业务规则、service/repository、API、import job/read model 与跨模块业务流未变化，第 1–4、6 类不新增测试。
- 共享 modal drawer 的真实 Chromium motion 由 `web/e2e/drawer-motion.spec.ts` 负责；tax 页面既有 `tax-offset-flow.spec.ts` 继续保护认证导入和计划业务链。

## 核心验收

| 场景 | 测试入口 | 合同 |
| --- | --- | --- |
| canonical snapshot repository | `tests/test_tax_offset_canonical_repository.py` | 单个 repeatable-read/read-only transaction；固定三次 query；发票、认证、最新计划、summary、statistics、token 同一 snapshot；不读 relation/RM |
| Page Audit | `tests/test_tax_offset_page_audit.py` | 同一只读 snapshot 独立重算 canonical 发票/认证/最新计划与统计；不读 Tax RM、queue、cache 或 Workbench relation |
| 税额与认证规则 | `tests/test_tax_offset_service.py` | Decimal 金额、已认证锁定、计划内/外拆分、空集、唯一键匹配 |
| API/权限/写入 | `tests/test_tax_offset_api.py` | read/save/import 权限、非法输入、空集、认证幂等、计划幂等与 409 canonical CAS、写后 normal GET、无旧 runtime fields |
| import job | `tests/test_import_job_queue.py`、`tests/test_import_processing_service.py` | preview/confirm/job 完成与失败回滚；银行导入不误触发税金事实 |
| frontend mapper/page | `web/src/test/TaxApi.test.ts`、`web/src/test/TaxOffsetPage.test.tsx` | loading/empty/error、权限、试算、保存、搜索/排序/筛选、drawer、导入 job、保存/导入后直接 GET、零旧 polling |
| Browser flow | `web/e2e/tax-offset-flow.spec.ts` | read-export/admin/session gate、大数据表格交互、CAS conflict、计划与认证导入完整链 |
| relation 隔离 | `web/e2e/workbench-relations-tax-offset-isolation.spec.ts`、`tests/test_workbench_relation_repository.py` | relation confirm/withdraw 前后税金 facts 不变且不产生 tax queue 写入 |
| 范围外回归 | invoice import、input/output invoice、cost statistics 相关测试 | canonical invoice 写入仍可被税金页读取；成本统计/发票页面行为不变 |

## 七类测试映射

| 类别 | 适用性 | 覆盖 |
| --- | --- | --- |
| 1. Business core | 适用 | `test_tax_offset_service.py` 覆盖金额、去重、认证匹配、锁定、空输入；API 覆盖计划选择重复与冲突 |
| 2. Service/repository | 适用 | `test_tax_offset_canonical_repository.py`、`test_tax_offset_api.py` 覆盖持久化、snapshot、幂等、失败不半写 |
| 3. API contract | 适用 | 权限拒绝、非法月份/body、200 shape、summary、calculate、plan 409、import job/list；明确断言无 `read_model_status/source_versions/targets` |
| 4. Read model/cache/background job | 部分适用 | 页面 read model/cache/polling 已删除；保留认证 import job 测试。共享旧 tax worker/RM 测试归主控 cleanup，不再作为页面读取验收 |
| 5. Frontend interaction | 适用 | loading/empty/error、权限、筛选、排序、选择、保存、drawer/modal、job polling、写后 GET；legacy refresh polling 为负向 guard |
| 6. E2E business flow | 适用 | canonical read -> calculate -> save -> GET，以及认证 preview -> confirm/job -> GET |
| 7. Existing regression | 适用 | 成本统计、发票导入、进项/销项页面、relation 隔离 |

## 查询与性能 guard

- repository 单元测试锁定一次 transaction、一次 transaction-level isolation command、两次 `fetch_all` 和一次 `fetch_one`。
- 禁止逐行 SQL、Redis/cache、queue、worker、外部 OA/Mongo/MySQL/对象存储进入 GET。
- 当前单月完整工作集没有 pagination/detail/export API；现有搜索、日期排序和对方筛选行为由 TaxTable 测试保护。未来新增分页必须由 SQL 实现，不允许浏览器先加载全量后分页。

## 最小验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_canonical_repository tests.test_tax_offset_service tests.test_tax_offset_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_certified_import_service tests.test_import_job_queue tests.test_import_processing_service -v
bash scripts/verify.sh lint
cd web && npm test -- --run src/test/TaxApi.test.ts src/test/TaxOffsetPage.test.tsx
cd web && npm run build
cd web && npx playwright test e2e/tax-offset-flow.spec.ts e2e/workbench-relations-tax-offset-isolation.spec.ts
```

范围外回归：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_input_invoice_usage_api tests.test_output_invoice_collection_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_import_job_queue tests.test_import_processing_service -v
cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx
```
