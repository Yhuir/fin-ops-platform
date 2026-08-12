# 批量账务模块边界与 I/O

日期：2026-08-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：页面专属 API -> query service -> 页面专属 PostgreSQL query repository -> canonical facts。
- 写边界：`BatchAccountingService` -> `WorkbenchRelationCommandService` -> canonical relation repository。
- read model/worker：不拥有、不读取、不刷新。

## 职责边界

### 负责

- 批量账务页面、银行/OA 双分页、OA 搜索、选择、金额校验、提交和撤回交互。
- canonical 候选资格和 active batch relation 列表的业务组合。
- 页面专属 PostgreSQL 查询以及一次请求内一致快照。
- 左栏银行流水的 current effective tag 展示、未提交规则筛选和规则抽屉。
- 写前 active relation 冲突、expected version、差额说明和跨月 scope 计算。

### 不负责

- 不拥有银行、OA、发票或关系 canonical 表。
- 不写 `app.bank_transactions`、`app.oa_applications`、`app.invoices` 或 `app.workbench_pair_relations`。
- 不读取 Workbench active generation、`read_model.workbench_*` 或 `workbench_relation` projection。
- 不管理 read-model manifest、scope policy、runtime worker、queue、RabbitMQ、App Status 或部署 worker env。
- 不主动刷新关联台、成本统计、搜索等下游页面。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| `bank_year` | 页面/API | 四位年份；决定银行候选和 submitted relation 中银行成员的年份 |
| `bucket` | 页面/API | `unsubmitted` 或 `submitted` |
| 银行分页 | `bank_page`、`bank_page_size` | 服务端执行；page/page size 必须为正数，page size 最大 200 |
| OA 分页 | `oa_page`、`oa_page_size` | 仅未提交 bucket 使用；服务端执行，最大 200 |
| OA 搜索 | `oa_search` | 最长 200 字符；纯金额输入归一为无千分位文本，在 canonical OA SQL 中匹配申请人、项目、金额、事由 |
| 银行候选 | `app.bank_transactions` | 指定年份、未删除、对方户名“批量账务集中处理”、`txn_direction='outflow'`、金额大于 0、没有任何 active relation；银行名/尾号只取 normalized payload 的结构化银行字段，不得用账户户名冒充银行名 |
| effective category | Bank Details canonical classifier | 对本次精确业务流水 ID 集合一次 set-based 分类；使用当前 active category/confirmation/自动标签设置，禁止复制第二套标签算法 |
| 标签选择规则 | `app.app_settings.batch_accounting_tag_selection` | stable tag codes + version；未持久化时默认当前 active definitions 全选，迁移后新增标签默认不选；归档标签从选择中原子移除 |
| 标签规则 command | `expected_version + selected_tag_codes[]` | full/admin 可写，read-export 只读；CAS、semantic no-op、未知/非 active code 校验和 audit 由 Settings owner 承担 |
| OA 候选 | `app.oa_applications` | 未删除、已完成状态别名、日常报销主单、不限年份、没有包含 canonical 银行成员的 active relation |
| OA 附件发票 | `app.invoices.source_links` + `app.oa_attachments` | 只按当前可见或本次选中的 OA IDs 批量查询；不得扫描全量附件 |
| submitted relations | `app.workbench_pair_relations` | 只读 `status='active' and relation_mode='batch_accounting'`，并要求关系包含指定年份的 canonical 银行成员 |
| submitted members | `row_ids + row_types`、canonical OA/invoice tables | 对齐且去重的 typed member set 是唯一成员事实源；对当前页 member IDs 一次 union bulk query |
| submit context | 页面/API | 指定 `bank_row_id + oa_row_ids`；在一个 read-only repeatable-read snapshot 中读取银行、OA、附件发票；submit/withdraw 必须携带页面按一次用户意图生成并在网络重试中保持不变的 `idempotency_key`，缺失时 fail closed。 |
| relation 冲突/CAS | `WorkbenchRelationCommandService` | 基于 canonical active relations、owner、version、idempotency 和 command repository |
| 权限/session | route/Application | GET 遵循页面读取权限；submit/withdraw 必须有业务写权限 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `summary` | 页面 | `unsubmitted_count`、`submitted_count`、`bank_year` 与 rows 在同一 snapshot |
| `bank_rows` | 页面 | 当前 bucket 的服务端分页银行行；`bank_name + account_last4` 是银行 chip，`trade_time` 是 canonical 时间文本，页面只做无时区换算的展示归一化 |
| bank tag fields | 页面左栏 | `tag_code/tag_label/tag_primary_label/tag_sub_label/tag_source` 来自当前 canonical classifier；页面只展示，不自行推断 |
| `tag_selection_version` | 页面 submit | 当前列表采用的规则版本；submit 必须原样回传，后端在窄 snapshot 内重新分类并检查版本与选中状态 |
| tag-rules payload | HeroUI drawer | `version`、`active_tags`、`selected_tag_codes`、`can_save`；active tags 仅限业务流水实际出现且当前 active 的标签，selected 保留其它当前 active stable codes，保存不可误删隐藏选择 |
| `oa_rows` | 页面 | 未提交 bucket 的服务端分页 OA 候选；submitted 返回空列表 |
| `relations_by_bank_row_id` | 页面 | submitted 当前页 active batch relation 及 canonical OA/发票成员详情 |
| `pagination` | 页面 | 银行分页始终返回；未提交同时返回 OA 分页 |
| `Server-Timing` | HTTP | `canonical_snapshot`、`payload_assembly` 和 serialization；不进入业务 JSON |
| submit 结果 | 页面 | canonical relation、受影响 row IDs/months/scopes、金额校验和 message；相同 key/fingerprint 重试返回同一 durable 结果，不重复追加 relation/history。 |
| withdraw 结果 | 页面 | canonical cancel 结果、受影响 row IDs/months/scopes 和 message；相同 key/fingerprint 重试不得重复撤回或重复写审计。 |
| 写后 GET | 当前页面 | 每次成功 submit/withdraw 后一次；不 poll、不触发 operation barrier |

响应禁止出现 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`source_versions`、`refresh_enqueued`、`freshness_targets` 或 `operation_barrier_targets`。

`special_metadata` 只保存 `source`、`bank_year`、`oa_years`、`affected_scope_keys`、`created_by` 等来源/审计上下文。成员身份不得写入或读取 `special_metadata.bank_row_id`、`oa_row_ids`、`invoice_row_ids` 或旧 `year` alias；submitted DTO 也不透传 raw relation / metadata。

## 事务与查询合同

`PostgresBatchAccountingQueryRepository` 的每个 public query 都在同一连接事务中执行：

```sql
set transaction isolation level repeatable read read only
```

- rows、summary、count、pagination 和 relation member detail 使用同一个 snapshot。
- 未提交、已提交和 submit context：固定最多 5 条语句（含 isolation 和一次 set-based classifier）。
- tag-rules snapshot：固定最多 3 条语句（含 isolation）。
- 标签筛选只在指定年份且对方户名精确命中的业务候选集合内完成，再做服务端分页；禁止读取全量银行流水、浏览器过滤、N+1、逐月或逐 scope 循环。

## 依赖方向

```text
BatchAccountingPage
  -> features/batchAccounting/api
  -> BatchAccountingApiRoutes
  -> BatchAccountingService
     -> PostgresBatchAccountingQueryRepository (read only)
        -> Bank Details canonical effective-category projection (read only)
     -> AppSettingsService (tag-selection owner)
     -> WorkbenchRelationCommandService (write owner)
```

禁止反向依赖：repository 不依赖 service/route；service 不依赖 HTTP、auth 或 `Application`；route 不包含 SQL 或业务组合。

## 文件范围

### 页面模块拥有

- `web/src/pages/BatchAccountingPage.tsx`
- `web/src/components/batchAccounting/BatchAccountingTagRulesDrawer.tsx`
- `web/src/features/batchAccounting/api.ts`
- `web/src/features/batchAccounting/types.ts`
- `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
- `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/batch_accounting.py`
- 页面专属 backend/frontend/E2E tests
- `backend/src/fin_ops_platform/postgres/migrations/0135_batch_accounting_tag_selection.sql`
- `docs/modules/batch-accounting/`

### 仅最小接线

- `backend/src/fin_ops_platform/app/server.py`

### 禁止由本模块删除或修改的共享资源

- `read_model_manifest.py`
- `runtime_worker_registry.py`
- `read_model_scope_policy.py`
- `runtime_worker_handlers.py`
- App Status 全局 registry
- deploy/worker env、RabbitMQ dispatcher
- `docs/architecture/module-boundaries/read-model-contracts.md`
- shared Workbench/workbench-relation repository、facade、projection、migration

## 旧代码删除状态

页面 runtime、service、route、frontend mapper 和 E2E mock 已不再调用或表达：

- 三个旧 batch Workbench loader。
- batch 专用 `WorkbenchRelationReadFacade` readers。
- relation freshness/status/enqueue/polling/202/fallback。
- operation barrier 和跨页面 refresh targets。
- 客户端全量 OA 搜索分页。

批量账务专用的 Workbench generation loader/reader 已删除；关联台页面同样不再拥有 Workbench page worker 或注册项。本模块不得恢复对关联台 projection 的依赖、双读或 fallback，也不得改用 `workbench_relation` distribution。

## 边界变化触发文档更新

如果候选业务口径、canonical 表、API shape、权限、relation command、query count、文件范围或依赖方向变化，必须同步本文件、`README.md`、`tests.md`，并按长期事实影响更新 app architecture、API 或产品文档。
