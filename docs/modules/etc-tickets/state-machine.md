# ETC票据管理 状态机


> 修改 `ETC票据管理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - `draft/imported`：ETC 发票已导入，业务批次仍在未提交链路。
  - `oa_draft_created`：OA 草稿已创建，等待用户人工确认。
  - `submitted_confirmed`：用户确认 OA 已提交，业务批次进入已提交口径，绑定的 ETC 对账任务同步闭环。
  - `not_submitted`：用户确认 OA 未提交，释放本地 ETC 发票占用并回到未提交链路。
  - `deleted`：用户可见业务批次被删除。删除来源可以是业务批次行或绑定的 ETC 对账任务行；删除只清理本地批次/导入事实，真实 OA 草稿和 OA 流程不删除。
- 状态事实源：`etc_business_batches` 业务批次、绑定的 ETC 对账任务状态、ETC 提交批次及审计事件。
- 允许流转：
  - 导入确认后创建或更新同一个业务批次，不在前端拆成“导入任务”和“对账任务”两个用户可见任务。
  - 创建 OA 草稿后只能由 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`。
  - `submitted` 成功后，关联台 open 区生成一条 `source_kind=etc_invoice_summary` 折叠汇总发票行，金额取业务批次上报金额，等待未来 OA 和银行流水进入后普通配对。
  - 任意业务阶段允许删除本地批次记录；删除必须写入审计并校验 `expectedVersion` 防并发覆盖，但不得因 `importing`、`oa_draft_created`、`submitted_confirmed`、`closed` 等流程状态阻塞。
  - 删除未提交批次会清理本地导入批次、ETC 发票和绑定任务；删除已提交批次会本地 reset 业务批次，释放 ETC 发票 `current_batch_id`，让 `etc_invoice_summary` 消失并使散票回到未配对区。
  - 已提交 `etc_invoice_summary` 若已经参与关联台 active relation，删除批次时必须取消包含该 summary row 的 active relation；取消后不得恢复历史 OA+银行流水二栏 active relation，OA 和银行流水各自回到未配对。
- 禁止流转：
  - ETC 页面不得提供自动 OA 检测、刷新检测或异常检测入口。
  - ETC 后端不得保留专用 OA 检测 refresh API、detector adapter 或 worker；批次已人工确认后不得被后台检测覆盖。
  - 关联台未找到 OA 和银行流水三项匹配前，`etc_invoice_summary` 不得直接进入已配对区。

## UI 状态

- loading：页面加载业务批次、导入/草稿/人工确认动作执行中时显示按钮级 loading，不展示后台英文状态码作为主文案。
- empty：未提交或已提交 tab 下无批次时只显示该 bucket 的空态；一个业务批次在前端只出现一次。
- initial load：页面进入和刷新只能读取已有业务批次/对账任务，不得自动创建空 ETC 对账任务；新建批次只能由用户点击“新建批次”触发。
- error：导入、创建草稿、人工确认、删除失败时显示本地化业务错误；内部对象 id、文件 id、旧检测码不作为主要用户文案。
- submitted delete confirm：已提交批次删除确认框必须说明“取消发票合并，OA 系统中的草稿和已提交记录不会删除”，不得展示为撤销 OA。
- stale/refreshing：ETC 页面本身不触发 OA 自动检测；关联台 read model 刷新状态由关联台页面展示。
- permission disabled/hidden：权限不足时隐藏或禁用创建、导入、草稿、人工确认入口；删除入口不做流程状态阻塞，后端只保留版本并发校验和本地清理一致性校验。

## Read Model / Worker 状态

- ETC 业务批次列表直接读取业务批次事实源；关联台是否出现 `etc_invoice_summary` 由 Workbench SQL projection/read model 决定。
- `submitted` 人工确认会隐藏散落 ETC 发票，并让 Workbench open 区投影一条合并行；投影失败时不应把批次回滚成未提交。
- `etc_invoice_summary` 的展示金额可以保留千分位格式；read model 必须同时持久化结构化金额，用于 `workbench_rows.amount`、分组搜索文本和金额过滤。
- refresh 触发来源：ETC 导入确认、OA 草稿创建、人工提交确认、人工未提交确认、业务批次本地删除/重置、关联台普通配对关系确认或撤回。
- canonical invoice identity：ETC 发票有稳定发票号/强 `source_unique_key` 时，不得同时持久化弱 `data_fingerprint`；runtime worker 和 API 导入确认必须使用同一 ETC invoice 同步路径，避免后台导入成功但本地发票索引未刷新。
- 失败恢复：优先重跑相关 read model refresh；业务批次、ETC 发票占用和审计事实不得从前端临时修补。导入确认的同一 session 只有 queued/running 或近期 succeeded job 可复用；failed、acknowledged、cancelled 等旧 job 必须允许重新确认并创建新 job。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-10 | 修复 ETC 导入/OA 草稿后本地 canonical invoice 持久化弱 fingerprint 冲突，并补齐导入失败 job 的同 session 重试语义，清理旧 ETC OA detection 部署残留 | ImportNormalizationService、Postgres invoice repository、runtime import worker、BackgroundJobService、ETC import confirm API、migration、RabbitMQ 部署样例 | `tests.test_import_service`；`tests.test_postgres_core_repository`；`tests.test_platform_runtime_boundary_guards`；`tests.test_postgres_migrations`；`tests.test_rabbitmq_staging_preflight`；`tests.test_etc_backend` |
| 2026-06-10 | 清理 ETC 任务删除旧状态阻塞，并确认页面初始化不自动创建空任务 | reconciliation task 删除、旧 batch 删除兼容入口、ETC 页面初始化请求 | `tests.test_etc_backend`；`tests.test_etc_reconciliation_service`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | 彻底移除 ETC 专用 OA 自动检测后端链路，草稿后统一进入 `oa_confirmation_pending` 等待人工确认 | ETC business batch API、worker registry、OA projection/Mongo adapter、前端状态显示、历史状态迁移 | `tests.test_etc_backend`；`tests.test_platform_runtime_boundary_guards`；`tests.test_oa_projection_sql_runtime`；`tests.test_mongo_oa_adapter`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts` |
| 2026-06-09 | ETC 批次删除入口统一为任意阶段本地清理；绑定 summary 的 active relation 取消且不恢复历史 OA+流水二栏关系 | ETC 任务入口删除、业务批次入口删除、Workbench active relation、open 区散票恢复 | `tests.test_etc_backend`；`tests.test_workbench_pair_relation_service`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | 已提交 ETC 业务批次支持本地删除/重置，释放合并发票但保留 OA 和已闭环任务事实 | ETC 页面 submitted bucket、业务批次状态、Workbench open 区散票恢复 | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | `etc_invoice_summary` 增加结构化金额并写入 workbench numeric/search 字段，同时修复历史已提交批次数据 | 关联台金额搜索、ETC 历史批次闭环、Workbench read model | `tests.test_workbench_sql_runtime`；生产数据 SQL 验证 |
| 2026-06-09 | Workbench SQL projection 将已提交 ETC 业务批次作为 `etc_invoice_summary` 一等来源，repository 持久化业务批次上报金额和数量 | ETC 人工已提交批次、关联台 open 区 summary、Postgres read model | `tests.test_workbench_sql_runtime`；`tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-08 | ETC 页面统一为单个业务批次链路；人工确认已提交后闭环对账任务并投影 `etc_invoice_summary` | ETC 批次、关联台 open 区、人工确认 API | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
