# 税金抵扣模块边界与 I/O

日期：2026-07-27

## 模块状态

- 状态：direct canonical read complete；共享旧 worker/RM cleanup pending main-control handoff。
- Query owner：`TaxOffsetQueryService`
- Repository owner：`PostgresTaxOffsetCanonicalRepository`
- Business policy：`TaxOffsetService`
- 事实一致性：每个页面/summary/calculate 请求各自使用一个显式 `REPEATABLE READ / READ ONLY` snapshot。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 月份查询 | `GET /api/tax-offset?month=YYYY-MM` | repository 在同一 snapshot 内批量读取发票、认证记录和最新计划；非法月份返回 400 |
| 页面默认月份 | `MonthContext` | 首次且没有有效 session 选择时使用 `Asia/Shanghai` 当前业务月；用户已有选择继续按既有 session 合同恢复。 |
| 摘要查询 | `GET /api/tax-offset/summary?month=YYYY-MM` | 返回同一 canonical 口径的 month、summary、statistics 和 canonical token |
| 试算 | `POST /api/tax-offset/calculate` | 从一次 canonical snapshot 读取 rows，再由 `TaxOffsetService` 按选择计算；不返回 202 |
| 计划保存 | `POST /api/tax-offset/plans` | 必须携带 `expected_canonical_snapshot_version`；校验后使用同一已读 payload 计算并保存，重复 idempotency key 返回原计划 |
| 认证导入 | preview/confirm/job API | 文件解析只在导入工作流；confirm 提交认证 canonical facts，页面完成后直接 GET |
| 发票事实 | `app.invoices` | 只消费已提交、`status <> 'deleted'`、目标月份的 canonical invoice |
| 认证事实 | `app.tax_certified_import_records` | 只消费目标月份且未删除的正式认证记录 |
| 已保存计划 | `app.tax_offset_plans` | 读取目标月份最新 `status='saved'` 计划，选择 ID 与当前可用 rows 求交 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows | 页面两张发票表与认证 drawer | 输出/进项/认证匹配/范围外 rows 使用同一 snapshot |
| summary/statistics | 页面卡片与统计 popover | 与 rows 同一 snapshot；金额由 Decimal 业务策略计算并以无千分位两位小数输出 |

页面标题 `statistics` 只包含当前月份 canonical 进项和销项发票数量；认证匹配、认证范围、可抵扣和勾选数量不再属于标题统计合同。
| `canonical_snapshot_version` | 前端计划保存 CAS | 对发票与认证页面事实生成稳定 SHA-256 token，不含 read-model 版本语义 |
| 计划保存结果 | 前端 | `status`、`plan`、`affected_scope_keys`；不含 read-model targets |
| 认证导入结果 | 前端/job | batch/job 与 `affected_scope_keys`；不含 tax operation barrier |

## 关系与外部系统边界

- 税金页不读取 `app.workbench_pair_relations`，relation confirm/withdraw 不改变本页 rows、summary 或 token。
- 禁止读取 Workbench、cost statistics、invoice lifecycle 或其它页面 read model 作为页面事实。
- OA/Mongo/MySQL/对象存储/OCR/文件解析不得进入 GET 热路径。
- OA 附件发票只有在正式 promotion 到 `app.invoices` 后才可进入页面。

## 查询与性能合同

- PostgreSQL 页面 repository 固定三次 query，无逐行/逐组 N+1。
- 三次 query 必须位于同一 read-only repeatable-read transaction。
- 当前页面合同是单月完整工作集，搜索、日期排序和对方筛选在已有表格组件中保持原行为；纯金额搜索按无千分位文本匹配。当前没有独立 detail/export endpoint 或分页 UI，不新增推测性合同。若未来新增分页，必须在 SQL 层分页并同步 summary/facets snapshot 语义。
- 不新增 cache、worker、queue、materialized view 或索引 migration。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `TaxOffsetPage.tsx`、`features/tax/*`、`components/tax/*` |
| Route | `app/routes_tax.py` |
| Query/service | `tax_offset_query_service.py`、`tax_offset_service.py`、`tax_offset_plan_service.py` |
| Repository | `services/postgres_repositories/tax_offset.py`、`services/postgres_repositories/tax_offset_page_audit.py` |
| Import | `tax_certified_import_*`、既有 import processing owner |
| Tests | `test_tax_offset_canonical_repository.py`、`test_tax_offset_api.py`、`test_tax_offset_service.py`、Tax Vitest/Playwright |

## 旧代码删除结果

页面 SQL read model、cache gateway、polling、projection/repository、refresh/rebuild/warmup、manifest/scope policy、runtime worker、App Status、deploy env 和 RabbitMQ 条目已删除；税金 Page Audit 使用 direct-canonical proof。历史 migration/表暂留作回滚证据，没有运行时 reader/writer。
