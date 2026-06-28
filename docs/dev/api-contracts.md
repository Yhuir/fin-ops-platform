# API 契约

> 2026-06-26 目标架构变更：页面读取迁移为 direct API，不再新增或扩展 `read_model_status`、`refresh_enqueued`、`read_model_scope_keys` 或 legacy target fields。本文中保留的 read model 字段只作为历史/负向合同；迁移单个接口时必须同步删除这些字段、更新前端 mapper 和测试。

## 契约原则

- API 返回字段应稳定，前端不能猜测不存在的字段。
- 写操作返回 affected rows/months，便于前端局部刷新。
- 高风险动作应有 preview 或 confirm 两段式接口。
- 后端错误应返回可展示的业务消息，不返回空 body 让前端猜测。
- HTML 响应视为部署或代理错误。

## 主要 API 分组

- `/api/session/*`：OA 会话和当前用户。
- `/api/workbench*`：关联工作台查询、详情、动作、异常、设置。
- `/imports/*`：导入预览、确认、模板、批次和文件会话。
- `/api/no-oa-bank-batches/*`：免 OA 批次。
- `/api/etc/business-batches*`：ETC 用户可见业务批次、补充导入、OA 草稿和 OA 提交人工确认。
- `/api/tax-offset*`：税金抵扣和已认证导入。
- `/api/cost-statistics*`：成本统计、下钻和导出。
- `/api/bank-details*`：银行明细、自动分类展示和 XLSX 导出。
- `/api/pending-invoices*`：待找发票列表、筛选、关系明细、候选进项发票、规则和导出。
- `/api/search`：全局搜索资源 API。
- `/api/background-jobs*`：后台任务。
- `/api/app-health*`：健康状态。
- `/api/operations/app-health-dashboard`：管理员只读运维观测 Dashboard。

## Workbench 设置 API

`GET /api/workbench/settings`

返回关联台和设置页共享的平台设置 payload。响应可包含 `bank_transaction_tags`，用于前端展示当前银行明细标签事实和配置待找发票/免 OA/往来款等下游规则候选。

`POST /api/workbench/settings`

保存项目范围、访问控制、银行账户映射、OA 导入/留存、列布局、待找发票规则等设置项。该接口不是银行明细自动标签规则写入口。

- 请求体不得包含 `bank_transaction_tags`。只要出现该字段，后端返回 `400 bank_transaction_tags_write_forbidden`，不得部分保存其它设置。
- `AppSettingsService.update_settings(...)` 不暴露 `bank_transaction_tags` 写参数；银行明细自动标签规则只能通过银行明细自动标签 API 或复用该 application service 的恢复工具保存。
- 前端 settings/workbench API mapper 不得把 GET 得到的 `bank_transaction_tags` 原样回传到该接口，避免把规则内部元数据洗成只剩 label/path/status 的展示字典。
- 银行明细标签定义、自动匹配规则、外部往来 `turnover_action_type` / `turnover_role` 等元数据只能通过 `/api/bank-details/auto-tag-rules`、`/api/bank-details/auto-tag-rules/file-replacement` 或相关银行明细规则 service 保存。
- 待找发票、免 OA、往来款标签选择等下游规则只能引用当前 active 银行明细标签 code；保存这些下游规则不得递增 `bank_transaction_tags.version`。

## 日常报销批量账务管理 API

`GET /api/batch-accounting?bank_year=YYYY&oa_year=YYYY&bucket=unsubmitted|submitted`

响应字段：

| 字段 | 说明 |
| --- | --- |
| `summary.unsubmitted_count` | 当前筛选下未提交候选银行流水数量。 |
| `summary.submitted_count` | 当前银行年份下已提交批量账务关系数量。 |
| `summary.bank_year` / `summary.oa_year` | 后端实际使用的银行流水年份和 OA 单据年份。 |
| `bank_rows` | 当前 bucket 的银行流水列表。 |
| `oa_rows` | `unsubmitted` bucket 的可选 OA 日常报销单据列表。 |
| `relations_by_bank_row_id` | `submitted` bucket 中按银行流水 ID 索引的已提交关系详情。 |

该 GET 不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys` 或 `refresh_enqueued`。前端只按业务 rows、summary、relations 和 pagination 渲染；关系分布追赶中不能作为页面合同字段暴露。

列表读取当前仍可复用现有 relation facade 获取关系分布，但不能把 facade legacy sync/status/scope diagnostics 透传给页面。后续 direct query batch 负责替换这条后端 legacy 读路径。

`POST /api/batch-accounting/submit`

`POST /api/batch-accounting/{relation_id}/withdraw`

写操作由 `WorkbenchRelationCommandService`、canonical active relation、idempotency、version conflict、权限/session 和 DB 可写性校验保护；普通 relation distribution legacy sync state 不再作为默认写阻断条件。成功响应返回 `affected_months` 和 `affected_scope_keys`，不返回 `read_model_scope_keys`。

## 待找发票规则 API

`GET /api/pending-invoices/rules?direction=expense|income`

返回指定方向的待找发票规则集。`direction=expense` 使用 `pending_invoice_tag_groups.version`；`direction=income` 使用 `pending_output_invoice_tag_groups.version`。该 `version` 是规则集自己的乐观锁版本，不等于 `bank_transaction_tags.version`。银行明细自动标签版本只代表标签定义和自动匹配规则事实。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 当前 direction 的待找发票规则版本。 |
| `direction` | `expense` 或 `income`。 |
| `available_tags` | 当前可配置的 active 银行明细自动标签候选。 |
| `groups` | 当前规则分组。支出可编辑 `bank_statement_as_invoice`、`no_invoice_required`；收入可编辑 `no_invoice_required`、`cash_income`。 |
| `groups.requires_invoice` | active tag complement，由后端实时派生，不是用户可编辑持久事实。 |
| `permissions.can_save` | 当前用户是否可保存规则。 |

`PUT /api/pending-invoices/rules?direction=expense|income`

请求示例：

```json
{
  "version": 7,
  "direction": "expense",
  "groups": {
    "bank_statement_as_invoice": {"tag_codes": ["bank_receipt_fee"]},
    "no_invoice_required": {"tag_codes": ["external_turnover_payment"]}
  }
}
```

保存规则：

- `version` 使用当前 direction 的规则版本做乐观锁；支出版本冲突返回 `409 pending_invoice_tag_groups_version_conflict`，收入版本冲突返回 `409 pending_output_invoice_tag_groups_version_conflict`。
- 未知标签、归档标签、重复映射必须 fail fast，不写审计、不触发 lifecycle。
- `requires_invoice` 即使出现在请求中也会被忽略；它始终是 active tag complement。
- 保存成功只递增对应规则集版本，不递增 `bank_transaction_tags.version`。支出和收入规则版本互不影响。
- 银行标签归档如果自动剥离待找发票规则引用，必须同时递增银行标签版本和被影响的待找发票规则版本。

成功响应返回新的规则 payload，并额外携带：

| 字段 | 说明 |
| --- | --- |
| `derived_data_lifecycle` | `pending_invoice_rules_changed` lifecycle 执行摘要，包含 affected domains、skipped domains、invalidated scopes 和 enqueued jobs。 |

规则变更只通过 `pending_invoice_rules_changed` 进入派生数据生命周期。该事件标记发票生命周期、待找发票、关联台、进项使用、OA 待付款、销项收款、税金抵扣、成本统计和搜索相关派生数据；不得影响 `turnover_ledger`、`no_oa_bank_batch`、`bank_account_balance`。

成本统计不再通过 `cost_statistics.read_model.refresh` 表示页面可见性。`derived_data_lifecycle.enqueued_jobs` 可以包含真实下游 worker 事件或 `cost_statistics_cache_warmup`，但页面必须通过 direct API 重读确认结果。

## App Health 全局状态 API

`GET /api/app-health` 保留既有字段，并新增 `app_status` 作为 Global Runtime Status Plane 的用户可见投影。SSE `/api/app-health/stream` 的 `app_health` 事件必须携带同样的 `app_status` shape。

`app_status` 字段：

| 字段 | 说明 |
| --- | --- |
| `version` | app status contract 版本，当前为 `1`。 |
| `generated_at` | 后端生成时间。 |
| `overall.level` | `ok`、`busy` 或 `blocked`。 |
| `overall.color` | `green`、`yellow` 或 `red`，供全局 icon 使用。 |
| `overall.reason` | 全局状态原因。 |
| `overall.blocks_mutations` | 当前全局状态是否应阻断写入；该字段由 `overall.write_safety.blocks_mutations` 派生，不能由普通 legacy projection diagnostics 直接推导。 |
| `overall.write_safety` | 写操作安全闸门，至少包含 `status`、`reason`、`blocks_mutations` 和 `blockers`。只有 session/auth、runtime/DB、关键依赖或目标写模型不可用等写安全 blocker 才应进入 `blockers`。 |
| `domains[]` | 所有页面数据域状态。 |
| `background_tasks[]` | 用户可见后台任务进度投影。 |
| `alerts[]` | 当前 active 运行告警摘要。 |

`domains[*]` 至少包含 `key`、`label`、`route`、`level`、`status`、`reason`、`details`、`workers`、`job_ids` 和 `updated_at`。App Status domain payload 不再返回 `read_models`、`read_model_scopes` 或 `historical_read_model_scopes`；页面级 legacy projection readiness 不是全局 domain 状态合同的一部分。`status` 必须来自后端规则集：`ready`、`loading`、`pending`、`processing`、`refreshing`、`stale`、`failed` 或 `unavailable`。页面切换不能改变这些字段；只有后端 runtime facts 变化才改变全局状态。

`overall.level="blocked"` 表示全局运行状态红色，不等价于所有写操作都必须禁用。页面和 mutation hook 必须使用 `overall.write_safety.blocks_mutations` / `overall.blocks_mutations` 作为全局写闸门，并继续在具体写 API 内执行权限、审计、幂等、version conflict 和 operation-level read/write precondition。页面 legacy projection failed/unavailable 不再让 App Status 对应 domain blocked/red；需要阻断的同步或写前置条件必须由具体页面 API 或写 API 自己返回。

`domains[*].details` 只用于真实 runtime、worker、job、dependency、alert 或 session 问题说明。页面 legacy projection readiness、schema/source mismatch、missing readiness 和 historical scope 不再进入 App Status domain payload；旧 read model 诊断应通过对应 legacy 页面、运维 dashboard 或后续删除清单处理，不能重新作为全局状态字段。

outbox failures 只有在没有后续同 scope `done` 或 superseding event 证明时，才作为当前 blocker 参与 App Status。被后续真实后端完成事实覆盖的 `failed/dead_lettered/publish_failed` 事件属于历史诊断和后续 repair/审计对象，不应污染用户当前页面同步状态。

`background_tasks[*]` 至少包含 `job_id`、`type`、`status`、`label`、`short_label`、`message`、`phase`、`current`、`total`、`percent`、`affected_domains`、`affected_scopes`、`affected_months`、`route`、`attention` 和 `updated_at`。没有真实百分比的 worker/task 不得伪造 percent，可返回 `null`。`file_import` 等泛化类型必须优先使用 payload 中的 `affected_domains`，否则按 source/import type 映射到单一 import domain，不能默认影响所有导入页。

前端必须对 `overall.level/color/reason`、domain `key/level/status/reason`、task `job_id/status` 做 fail-closed 校验。关键字段缺失或非法时，不能把 payload 默认解释为 `ok/green/ready`。

## Search API

`GET /api/search`

该 GET 是 direct business payload：后端直接调用 `SearchService.search(...)` 组装 rows、groups、summary 和过滤结果，不读取 SQL search read model 或 freshness service 作为页面返回前置条件。响应不返回 `read_model_status`、`read_model_scope_key`、`refresh_enqueued`、`read_model_stale_reasons` 或 `read_model_unavailable`。

legacy `search.read_model.refresh`、`SearchQueryFreshnessService`、Search worker lanes 和 Search SQL index/projection 已删除。历史 `search_pending_sql_projection.py` 也已随 pending-invoice legacy projection 删除，不是 Search 页面读取路径。生产环境缺少 SQL search repository 时，`/api/search` 仍按 direct `SearchService` payload 返回，而不是返回 `503 read_model_unavailable`。

## 免 OA 流水批量处理 API

`GET /api/no-oa-bank-batches/tag-selection`

返回免 OA 页面的全局标签准入范围。该接口只读取银行明细自动标签规则中的可用标签作为候选，不创建独立标签事实源。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 免 OA 标签准入配置版本，用于保存时乐观锁。 |
| `bank_auto_tag_rules_version` | 当前银行明细自动标签规则版本；前端可用它判断标签事实源是否已变化。 |
| `selected_tag_codes` | 当前已保存、仍处于可用状态的标签 code 列表。首次为空数组，后续由用户保存决定。 |
| `inactive_selected_tag_codes` | 历史配置中已停用或不可用的标签 code；不参与候选生成，保存后会被清理。 |
| `active_tags` | 银行明细自动标签规则中的可用标签，供抽屉按主/子标签层级展示。 |

`active_tags[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 银行明细标签稳定身份。 |
| `label` | 标签显示名称。 |
| `path` | 标签路径，可用于审计或调试。 |
| `status` | 当前只返回 `active`。 |
| `output_primary_label` / `output_sub_label` | 免 OA 页面展示的主/子标签。`output_sub_label` 可为空，前端显示为“主标签本身”。 |

免 OA 标签准入不返回第三层流水分类字段。外部往来流水的“个人往来 / 公司往来 / 银行往来 / 业务往来”只属于银行明细候选确认或人工补分类时选择的流水级分类，不作为免 OA 自动规则保存或展示。

`PUT /api/no-oa-bank-batches/tag-selection`

请求示例：

```json
{
  "expected_version": 3,
  "selected_tag_codes": ["fee", "salary"]
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 no_oa_bank_batch_tag_selection_version_conflict`。
- `selected_tag_codes` 可为空数组，表示免 OA 页面暂不生成新的未提交候选。
- 只能提交当前 `active_tags` 中存在且处于可用状态的标签 code；未知或停用标签返回业务错误。
- 成功后返回与 GET 相同结构，并写审计动作 `no_oa_bank_batch_tag_selection_updated`。
- 保存后只影响后续未提交候选；已提交历史批次继续可见并允许按批次撤回。

`GET /api/no-oa-bank-batches`

查询免 OA 批次列表。常用查询参数：

| 参数 | 说明 |
| --- | --- |
| `month` | `YYYY-MM` 月份。 |
| `bucket` | `unsubmitted`、`submitted`、`withdrawn` 或 `all`。 |
| `account_key` | 银行账户筛选。 |

响应中的 `summary.categories[*]` 和 `batches[*]` 需要携带 `category_primary_label`、`category_sub_label`、`category_label_path`，供前端构造主/子标签三栏。未提交候选批次只来自当前保存的免 OA 标签准入范围，且必须排除已被关联台 active relation 占用的银行流水；已提交历史批次即使标签不再准入也继续返回。

该 GET 通过 direct service rows 返回 `summary`、`batches` 和 `pagination`，不读取 no-OA SQL read model 作为页面 list 数据源，也不因 SQL 投影 missing/stale 入队刷新。响应不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys` 或 `refresh_enqueued`。后台 `save_no_oa_bank_batches` 写入的是当前完整 no-OA canonical snapshot；不在新 snapshot 中的旧 draft/conflict/submitted 批次必须从 `app.no_oa_bank_batches` 清理，不能继续作为列表数据返回。

`POST /api/workbench/actions/confirm-link`

关联台确认两条银行流水时，如果选中流水当前分类全部为 `internal_transfer`，后端必须委托免 OA 批次统一提交入口：刷新免 OA 候选，优先复用完全匹配这组 `row_ids` 的 submitted no-OA internal transfer batch；若不存在 submitted fact，再找到完全匹配的内部往来 draft batch 并按批次提交。成功响应仍保持关联台 `confirm_link` 兼容结构，但最终事实必须是一个 `status=submitted` 的内部往来免 OA 批次，以及一条 `relation_mode=no_oa_bank_batch` 的 Workbench active pair relation；关联台已配对区消费该 relation，免 OA 已提交区域消费同一批次。免 OA 页面先提交或关联台先提交同一组流水都必须返回同一个 `case_id`，不得创建第二条 active relation。

存量 active `manual_confirmed` 关系只有在 `internal_transfer` 已纳入免 OA 标签准入，且两行、全银行流水、同金额、不同账户、收支成对、有效分类均为 `internal_transfer` 时，刷新 no-OA 批次时才迁移为 submitted no-OA internal transfer batch；其他普通 `manual_confirmed` 关系保持关联台语义，不由 no-OA 模块接管。Workbench active pair relation 对 row 是独占事实，不同 active case 不允许复用同一 row。

如果选中银行流水中只有部分为 `internal_transfer`，接口返回 `400 no_oa_bank_batch_selection_internal_transfer_conflict`，不得静默写入 `manual_confirmed`。非内部往来的银行-only 平衡确认保持原有关联台普通确认语义，可写入 `relation_mode=manual_confirmed`。

`POST /api/no-oa-bank-batches/submit-selection`

提交当前页面选中的银行流水，后端按这一次选择生成一个免 OA 批次并立即提交，不按银行账户自动拆分多个批次。

请求示例：

```json
{
  "transaction_ids": ["bank-row-001", "bank-row-002"],
  "note": ""
}
```

提交规则：

- `transaction_ids` 必填且不能为空，不能重复。
- 所有流水必须来自同一月份、同一银行账户、同一 `category_code`，且该 `category_code` 必须在当前免 OA 标签准入范围内。
- 只提交请求中的流水；同银行区域内未选中的流水不提交。
- 成功后写入 `relation_mode=no_oa_bank_batch`，返回 `affected_months` 和 `workbench_rebuild_queued` 供前端刷新关联台。

`POST /api/no-oa-bank-batches/{batch_id}/withdraw`

撤回已提交免 OA 批次。撤回必须使用批次 API，不能从关联台绕过批次直接普通取消 relation。

## 外部往来款管理 API

`GET /api/turnover-ledger/tag-selection`

返回外部往来款管理页面的标签准入范围。该接口只读取银行明细自动标签规则中的可用外部往来规则作为候选，不创建独立标签事实源。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 外部往来款标签准入配置版本，用于保存时乐观锁。 |
| `selected_tag_codes` | 当前已保存、仍处于可用状态且属于外部往来的银行明细标签 code。首次默认为全部可用外部往来规则。 |
| `inactive_selected_tag_codes` | 历史配置中已停用、未知或不再属于外部往来的标签 code；不参与台账候选，保存后会被清理。 |
| `active_tags` | 银行明细自动标签规则中的可用外部往来标签，供抽屉按主/子标签层级展示。 |

`active_tags[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 银行明细标签稳定身份。 |
| `label` | 标签显示名称。 |
| `path` | 标签路径，可用于审计或调试。 |
| `status` | 当前只返回 `active`。 |
| `output_primary_label` / `output_sub_label` | 抽屉展示的主/子标签；不包含子子标签。 |
| `turnover_role` / `turnover_action_type` | 外部往来台账语义字段。 |

`PUT /api/turnover-ledger/tag-selection`

请求示例：

```json
{
  "expected_version": 2,
  "selected_tag_codes": ["external_turnover_payment_borrow_out"]
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 turnover_ledger_tag_selection_version_conflict`。
- `selected_tag_codes` 可为空数组，表示外部往来款管理暂不拉取新的流水。
- 只能提交当前 `active_tags` 中存在且处于可用状态的标签 code；未知、停用或非外部往来标签返回业务错误。
- 成功后返回与 GET 相同结构，并写审计动作 `turnover_ledger_tag_selection_updated`。
- 外部往来款管理列表只纳入 `effective_category_code` 位于 `selected_tag_codes`，且已经在银行明细确认 `个人往来`、`公司往来`、`银行往来` 或 `业务往来` 第三层分类的流水；未确认第三层分类的外部往来候选继续留在银行明细处理。

`GET /api/turnover-ledger`

查询外部往来款台账。常用查询参数：

| 参数 | 说明 |
| --- | --- |
| `view` | `grouped` 返回按对方户名和往来类别归并的页面台账。未传时保持兼容的列表响应。 |
| `family` | `all`、`personal`、`company`、`bank`、`business`。 |
| `direction` | 兼容参数：`all`、`borrow_in`、`borrow_out`。主页面不再展示该筛选，但 API、导出和自动化测试仍可使用。 |
| `page` / `page_size` | 分页参数。 |

`summary` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `pending_repayment_amount` | 当前待还款余额总额，来自借入类 principal 未结余额。 |
| `repaid_amount` | 累计已还款发生额，来自借入类 `repaid` settlement 历史发生额。 |
| `pending_collection_amount` | 当前待收款余额总额，来自借出/业务应收类 principal 未结余额。 |
| `collected_amount` | 累计已收款发生额，来自借出/业务应收类 `collected` settlement 历史发生额。 |
| `closed_amount` | 已闭合兼容金额；主页面不作为页头 block 展示。 |
| `suggested_count` / `conflict_count` / `row_count` | 兼容计数字段。 |

`family_summaries[*]` 每个类别都应稳定返回：

| 字段 | 说明 |
| --- | --- |
| `family` / `label` | 类别 code 和展示名。 |
| `pending_repayment_amount` | 该类别当前待还款余额。 |
| `repaid_amount` | 该类别累计已还款发生额。 |
| `pending_collection_amount` | 该类别当前待收款余额。 |
| `collected_amount` | 该类别累计已收款发生额。 |
| `pending_amount` / `closed_amount` / `row_count` | 兼容字段；`pending_amount` 等于待还款与待收款余额合计。 |

`view=grouped` 响应中的 `groups[*]` 还应稳定输出 `pending_repayment_amount`、`repaid_amount`、`pending_collection_amount`、`collected_amount`、`closed_amount`。`summary_row` 和 `flow_rows[*]` 应携带 `bank_account_labels`、`category_primary_label`、`category_sub_label`、`category_third_label`、`category_label_path` 和 `repayment_remark`。金额列归属以 `turnover_action_type` 归一后的 `borrow_amount` / `repayment_amount` 为准，不得仅按现金流入/流出判断。前端表头应将 `borrow_amount` 展示为“往来发生”、`repayment_amount` 展示为“结清发生”；金额 chip 使用 `borrow_direction` / `repayment_direction` 展示“收”或“支”，并按实际现金方向着色。

`GET /api/turnover-ledger` 和 `view=grouped` 是 direct business payload，不返回 `read_model_status`、`read_model_scope_keys`、`refresh_enqueued` 或 legacy stale reasons。闭环确认、流水选择和补充信息编辑的写安全由提交前重新加载 grouped payload、`expected_versions`、权限、idempotency 和后端 stale precondition 保护，不由页面旧同步字段决定。

外部往来款 `deterministic` 只表示系统识别到零差额候选，不表示已闭环，也不得作为关联台 open 分组或已配对事实。外部往来闭环的共同事实源是 Workbench active pair relation；来源可以是外部往来页人工确认闭环，也可以是关联台已经把同一往来组内的银行收入/支出配成同一个零差额 case。`view=grouped` 的 `summary_row` 和 `flow_rows[*]` 必须输出 `linked_oa`、`linked_invoice`、`cash_closure_linked`、`cash_closure_case_id`、`cash_closure_source`、`cash_closure_relation_id`；前端只能据此显示“已关联 OA”“已关联 发票”“收支闭环”三个正向 chip，不得从 `workbench_relation_status/mode` 自行推断“已关联业务单据”“未闭环”“候选关联”等旧 chip。若所选银行流水已存在仅含 OA + 银行的 active relation，确认闭环应把既有 OA-bank relation 和新增银行流水合并进同一个 `turnover_manual_closure` active case。Workbench 分区仍必须遵守三栏规则：未补齐发票的外部往来闭环留在 open，只有 OA + 银行 + 发票三栏补齐后才进入 paired。

`POST /api/turnover-ledger/closures/confirm`

人工确认同一往来组内多笔外部往来流水闭环。请求示例：

```json
{
  "bank_row_ids": ["bank-income-001", "bank-income-002", "bank-expense-001"],
  "expected_versions": {"turnover_bank_row:bank-income-001": "v1"},
  "idempotency_key": "closure-20260605-001",
  "note": "人工确认零差额闭环"
}
```

校验规则：

- `bank_row_ids` 必须至少两条且不能重复；不再限制为正好两条。
- 后端必须重新读取当前银行流水和分类事实；全部流水必须属于同一往来台账组、同一往来语义、同一对方，并同时包含收入和支出。
- 收入金额与支出金额差额必须为 `0.00`；否则返回 `400 turnover_closure_amount_mismatch` 或方向/语义相关业务错误。
- 流水不得已被其他 active Turnover confirmed relation 占用。若所选流水已被 Workbench active relation 占用，只有 row types 子集为 `{oa, bank}` 的 relation 可被本次闭环合并；包含 `invoice` 或其他业务 row type 时返回 `409 turnover_closure_requires_workbench` 或 `409 turnover_relation_conflict`，并提示去关联台处理完整关系。已确认后如需补选流水，必须先撤回原闭环关系，再重新选择完整流水确认。
- `expected_versions` 进入写 UoW 的 stale precondition；版本冲突必须在写 relation 和 pair relation 前失败。
- `idempotency_key` 进入写 UoW 的幂等边界；相同 payload 重放返回第一次结果，不同 payload 返回 `409 idempotency_key_conflict`。

成功响应至少包含：

| 字段 | 说明 |
| --- | --- |
| `turnover_relation` / `relation` | Turnover 手动闭环关系，`status=confirmed`、`source=manual`；两笔流水保留 `evidence.closure_mode=manual_zero_difference_pair`，三笔及以上为 `manual_zero_difference_group`。该 relation 自身不再依赖 `sync_to_workbench` 表示闭环。 |
| `workbench_pair_relation` | 同一写事务内创建的 Workbench active pair relation，`relation_mode=turnover_manual_closure`，作为共同事实源。可为 bank-only，也可在合并既有 OA-bank relation 时包含 `oa` + `bank` rows；未含发票的关系不得直接驱动关联台 paired 区，三栏补齐后才进入 paired。 |
| `affected_months` | 受影响月份，用于前端刷新外部往来、关联台和 relation direct payload。 |

成功写入必须返回 `affected_months` / `affected_scope_keys`，必要时写入真实后台 outbox；页面通过 direct GET 或 operation projection 刷新，不得在页面或 Workbench 查询层用 `turnover_relation` 重新拼 open 分组。

`POST /api/turnover-ledger/relations/{relation_id}/withdraw` 撤回外部往来手动闭环时，若对应 Workbench active relation 仍是 `turnover:{relation_id}` 的 `relation_mode=turnover_manual_closure`，且 row types 只包含 `oa` 与 `bank`，后端必须在同一写事务中撤回 Turnover relation，并通过 Workbench relation command service 只撤回该外部往来闭环 active case。若闭环确认前存在被合并的 OA-bank relation，撤回后必须恢复这些 relation；未参与既有 OA 关系的新增银行流水不应留在 active relation 中。该操作返回受影响的 `turnover_ledger`、`workbench`、`workbench_relation`、`cost_statistics`、`search` scope/month 诊断，由页面 direct reload 或 operation projection 消费。若该 Workbench relation 已补齐发票或其他业务 row type，接口必须返回 `409 turnover_closure_withdraw_requires_workbench`，提示用户到关联台撤回完整关系。

`POST /api/turnover-ledger/closures/withdraw` 撤回关联台来源的同组银行收支闭环。请求体使用 `cash_closure_case_id`（或 camelCase `cashClosureCaseId`），后端必须通过 `TurnoverLedgerWriteFacade` -> `TurnoverLedgerWorkbenchPairPort` -> `WorkbenchRelationCommandService.withdraw_relation(case_id=...)` 撤回同一个 Workbench active case，不得由外部往来页直接改 pair snapshot，也不得回退到 legacy pair service cancel。成功响应返回 `status=withdrawn`、`workbench_pair_relation`、`affected_months` 和 `affected_scope_keys`；不再返回 legacy target fields，页面写成功后重读业务 GET。缺少 case id 返回 `400 invalid_cash_closure_case_id`；case 已变化或不存在返回结构化 precondition error。

## 银行明细自动标签规则 API

`GET /api/bank-details/accounts`

返回银行明细页左侧账户列表和总余额。页面读取是 direct business payload：后端直接通过银行流水事实/服务组装账户与余额，不读取 `read_model.bank_detail_rows` 或 `read_model.bank_account_balances` 作为页面 freshness gate，也不返回 `read_model_status`、`balance_read_model_status`、`read_model_scope_keys` 或 `refresh_enqueued`。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `accounts` | 账户列表。 |
| `total_balance` | CNY 账户最新余额合计；没有任何非空余额时为 `null`。 |
| `total_balances_by_currency` | 按币种汇总的账户最新余额。 |
| `balance_account_count` | 有最新余额的账户数。 |
| `missing_balance_account_count` | 没有可用余额的账户数。 |

`accounts[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `account_identity` | 账户事实身份。优先使用完整账号哈希；缺少完整账号时回退为银行 + 尾号哈希。 |
| `account_key` | 前端筛选流水使用的稳定 key；由 direct bank details service 从银行流水事实生成。 |
| `bank_name` / `account_last4` / `display_name` | 账户展示字段。 |
| `account_no` / `account_name` | 可选账户原始字段；完整账号只用于身份区分和必要展示，不参与前端自造 key。 |
| `latest_balance` | 该账户按交易时间排序的最新一笔非空 `balance`。 |
| `latest_balance_at` | 贡献最新余额的流水时间。 |
| `latest_balance_transaction_id` | 贡献最新余额的流水 ID，用于审计和排查余额变化。 |
| `currency` | 币种，缺省为 `CNY`。 |
| `has_balance` | 是否有可用最新余额。 |
| `transaction_count` | 当前日期范围内该账户流水数量；只影响列表徽标，不参与余额计算。 |
| `transaction_total_count` | 该账户全部流水数量。 |

日期筛选只影响 `transaction_count`，不改变 `latest_balance`、`total_balance` 或 `total_balances_by_currency`。关键字、分类筛选和自动标签规则变化不调用该接口重新计算账户余额；银行流水导入、删除、重导或原始余额字段变化后，页面 GET 直接重新读取银行流水事实，不等待 bank_detail 或 bank_account_balance 投影。

`GET /api/bank-details/transactions`

返回银行明细流水列表。除基础流水字段、自动标签字段和关系标签外，自动标签候选确认相关字段如下：

该 GET 是 direct business payload，不存在 active `bank_detail` SQL read model、bank-detail worker、Redis page cache 或 read-model freshness/status 前置条件；响应不返回 `read_model_status`、`read_model_scope_keys`、`read_model_stale_reasons`、`refresh_enqueued` 或 `cache_status`。导出接口复用同一 direct query 边界，不以 direct payload refreshing 返回 `202`。

| 字段 | 说明 |
| --- | --- |
| `category_resolution_status` | 分类解析状态：`auto_matched`、`needs_confirmation`、`internal_transfer`、`manual_confirmed` 或 `unmatched`。 |
| `category_rule_version` | 生成该自动标签或候选集时使用的自动标签规则版本。 |
| `manual_confirmed_category_code` | 用户从自动候选集中确认后的标签 code；未确认时为 `null`。 |
| `auto_candidate_category_codes` | 当前自动规则命中的候选标签 code 列表；只有 `needs_confirmation` 时用于页面选择。 |
| `auto_candidate_categories` | 候选标签展示对象列表，包含 `category_code`、`category_label`、`category_primary_label`、`category_sub_label`、`category_third_label`、`category_label_path`、`category_path`、`turnover_role`、`turnover_action_type`、`turnover_family`、`rule_code` 和 `reason`。 |

当 `category_resolution_status=needs_confirmation` 时，前端只能展示 `auto_candidate_categories` 作为确认项，不得回退到全量银行明细标签字典。确认后接口返回的行应表现为 `manual_confirmed`，`effective_*` 字段按确认标签填充；撤销后回到当前自动规则重新计算结果。外部往来规则命中但缺少第三层标签时，候选项为同一规则展开出的 `个人往来`、`公司往来`、`银行往来`、`业务往来` 四类第三层标签，`turnover_action_type` 来自规则。

当 `category_resolution_status=unmatched` 且没有 `effective_category_code` 时，前端可展示 `待分类` 人工补分类入口。该入口使用当前响应中的 `bank_transaction_tags.definitions` 过滤 active 标签后按普通主/子标签和外部往来三层标签展示，不能调用自动候选确认接口。

自动候选生成按优先级层级收敛：`内部往来款` priority `1` 先执行并命中即停止；普通规则按 priority 从小到大分桶执行。某个普通 priority 层级一旦存在命中，后端不再检查更低优先级层级；该层级命中一个标签返回 `auto_matched`，命中多个标签返回 `needs_confirmation`，候选列表只包含该层级命中的标签。

`POST /api/bank-details/transactions/{transaction_id}/category-confirmation`

从当前自动规则命中的候选标签中确认一个标签。请求体：

```json
{
  "category_code": "external_payment",
  "category_third_label": "个人往来"
}
```

后端必须按当前流水和当前自动标签规则重新计算候选集，并校验请求标签存在、启用且属于当前候选集；同一 `category_code` 有多个外部往来第三层候选时，必须同时校验 `category_third_label`。不满足时返回 `400 invalid_category_confirmation_candidate`，不得接受前端伪造的非候选标签。成功后写来源为 `auto_confirmation` 的确认记录、审计记录，并触发下游 turnover/workbench/audit 等直接副作用；不再入队 `bank_detail.read_model.refresh`。

`DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`

撤销该流水当前自动候选确认。撤销后写来源为 `auto_confirmation_revoked` 的记录、审计记录，并触发同样的派生数据刷新链路。该接口只撤销候选确认，不恢复旧版“任意人工分类”能力。

`POST /api/bank-details/transactions/{transaction_id}/category-assignment`

为当前自动规则未命中的流水补充人工分类。请求体：

```json
{
  "category_code": "external_payment",
  "category_primary_label": "外部往来款付款",
  "category_sub_label": "借出款",
  "category_third_label": "个人往来",
  "category_label_path": ["外部往来款付款", "借出款", "个人往来"],
  "turnover_action_type": "pending_collection",
  "turnover_family": "personal"
}
```

后端必须重新计算当前流水的自动标签解析状态；只有当前状态为 `unmatched` 时允许写入来源为 `manual` 的人工分类。请求标签必须存在且处于启用状态；外部往来人工补分类必须携带第三层标签和可由规则解析的动作语义。`needs_confirmation`、`auto_matched`、`internal_transfer` 等状态返回 `400 invalid_manual_category_assignment_target`，不能用该接口绕过候选确认或覆盖确定性自动结果。成功后写审计动作 `bank_detail_category_manually_assigned`，记录 `selected_category_code`、`previous_resolution_status` 和 `assignment_source=manual`，并触发下游 turnover/workbench/audit 等直接副作用；不再入队 `bank_detail.read_model.refresh`。

`DELETE /api/bank-details/transactions/{transaction_id}/category-assignment`

清除该流水来源为 `manual` 的人工补分类事实。成功后写审计动作 `bank_detail_category_manual_assignment_cleared`，并触发同样的下游直接副作用链路。该接口不撤销 `auto_confirmation` 候选确认；候选确认仍必须调用 `/category-confirmation` 的 DELETE。

`GET /api/bank-details/auto-tag-rules`

返回银行明细文本类自动标签规则。该接口只读取 `bank_transaction_tags`，不读取平行规则表。

普通文本规则可由 `银行流水标签ui2.numbers` 归一化后一次性替换现有 app 内普通规则；替换时后端按主/子标签尽量复用稳定 `code`，未出现在文件中的旧普通规则进入停用/归档口径。`internal_transfer` 是系统规则，不由文件导入或 PUT 请求提交。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 当前银行明细标签配置版本，用于保存时乐观锁。 |
| `system_rule` | 固定系统规则，目前为 `internal_transfer`/`内部往来款`，只展示不允许编辑，UI 固定显示优先级 `1`。 |
| `active_rules` | 可用文本类标签，按优先级升序返回。 |
| `archived_rules` | 停用文本类标签，不参与自动命中。 |
| `field_options` | 可用于规则配置的稳定语义字段。 |
| `turnover_third_label_options` | 外部往来流水级可选第三层标签：个人往来、公司往来、银行往来、业务往来。自动标签规则抽屉只读展示这些候选，不保存到规则。 |
| `turnover_action_type_options` | 外部往来可选台账动作类型。 |
| `permissions.can_save` | 当前用户是否可以保存。 |

`active_rules[*]` 和 `archived_rules[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 稳定标签身份；新增标签保存前可为空，保存后由后端生成。 |
| `label` | 当前显示名称。 |
| `status` | `active` 或 `archived`。 |
| `priority` / `priority_label` | 可用区优先级；系统规则固定为 1，普通规则默认为 2，且必须大于等于 2。 |
| `sort_order` | 同优先级内稳定排序号；用于保持 xlsx/file 原始业务顺序，不表达执行优先级。 |
| `direction` | 适用方向：`income`、`expense`、`any`。 |
| `account_scope` | 兼容保留的适用账户范围字段：`{"type":"any","values":[]}`、`bank_account`、`account_type` 或 `bank`。普通维护 UI 不编辑账户范围，保存时固定写 `{"type":"any","values":[]}`。 |
| `rules.match_fields` | 语义字段列表。 |
| `rules.exact_any` | 精确命中任一字样列表，可为空。旧字段 `exact` 作为兼容别名读取。 |
| `rules.contains_any` | 包含任一字样列表，可为空。旧字段 `contains` 作为兼容别名读取。 |
| `rules.contains_all` | 必须同时包含字样列表，可为空。 |
| `rules.none_of` | 不包含任一字样列表，可为空。旧字段 `excludes` 作为兼容别名读取。 |
| `rules.regex_any` | 兼容保留的正则命中任一列表，可为空。普通维护 UI 不编辑正则，保存时固定写空数组。 |
| `output_primary_label` / `output_sub_label` | 规则输出标签；子标签可为空。`output_third_label` 不再是有效规则字段，外部往来旧 payload 中携带时由后端清理为空。 |
| `turnover_role` / `turnover_action_type` | 外部往来规则级语义字段；非外部往来规则不得提交这些字段。`turnover_family` 由具体流水确认的第三层标签产生，不作为规则级配置保存。 |
| `rule_summary` | 后端生成的人类可读摘要。 |
| `editable` / `archivable` / `sortable` | 前端交互能力标志。 |

普通 UI 不展示或编辑 `rule_id`、`version`、`stop_on_match`、`review_required`、`route_to`、命中说明、审计字段、账户范围和正则条件。这些系统字段由后端持久化、执行和审计使用。命中解释在结果预览或调试场景展示，不作为规则编辑项。

`field_options` 固定暴露语义字段，不暴露银行原始字段名：`counterparty_name`、`counterparty_account`、`counterparty_bank`、`purpose_text`、`summary_text`、`note_text`、`detail_text`、`all_text`。后端导入和自动分类服务负责把工行、建行、民生、平安等不同银行原始字段映射到这些语义字段。

`PUT /api/bank-details/auto-tag-rules`

请求示例：

```json
{
  "expected_version": 3,
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "direction": "expense",
      "account_scope": {"type": "any", "values": []},
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact_any": [],
        "contains_any": ["工资"],
        "contains_all": [],
        "none_of": [],
        "regex_any": []
      }
    },
    {
      "label": "供应商退款",
      "direction": "income",
      "account_scope": {"type": "any", "values": []},
      "rules": {
        "match_fields": ["all_text"],
        "exact_any": [],
        "contains_any": ["退款"],
        "contains_all": [],
        "none_of": ["保证金"],
        "regex_any": []
      }
    }
  ],
  "archived_rules": []
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 bank_transaction_tags_version_conflict`。
- 请求提交完整的可用区和停用区文本规则列表。`internal_transfer` 不在请求体中提交。
- 已存在标签必须携带原 `code`；新建标签不得提交 `code`，由后端生成稳定 `custom_...` code。
- 可用标签的 `output_primary_label` 去首尾空格后不能为空；唯一性按 `output_primary_label + output_sub_label` 组合判断，同主同子不允许重复，停用区允许历史重复。
- 可用标签唯一性按 `output_primary_label + output_sub_label` 判断。外部往来付款/收款规则提交 `output_third_label` 时后端规范化清空，用于清理旧客户端或旧配置；普通非外部往来规则不得提交 `output_third_label`、`turnover_role`、`turnover_action_type` 或 `turnover_family`。
- 外部往来规则必须能解析台账动作类型。标准外部往来子标签可由后端推导默认 `turnover_action_type`；用户新增外部往来子标签时必须显式提交 `turnover_action_type`。
- 可用普通标签的 `priority` 必须是大于等于 `2` 的整数；`1`、`0`、负数、小数和非数字字符串均返回 `invalid_auto_tag_rule` 结构化字段错误。缺失 priority 仅在新建或历史兼容路径按 `2` 处理。
- 保存后返回按 `priority ASC, sort_order ASC` 排序的规则；同一优先级内不按标签名称重排，避免打散 xlsx 原始业务顺序。
- 普通维护 UI 保存时，所有规则固定提交 `account_scope={"type":"any","values":[]}` 和 `rules.regex_any=[]`。后端继续兼容读取旧数据中的账户范围和正则字段，但普通维护 UI 不生成这些高级条件。
- 可用标签必须至少填写 `exact_any`、`contains_any` 或 `contains_all` 中的一类；`none_of` 只能为空或配合正向条件使用，不能单独构成命中。
- `match_fields` 只能使用 `field_options` 中的语义字段，且不能为空。
- 停用已被待找发票规则或免 OA 批量标签选择引用的标签时，后端同步移除这些引用、写入审计，并在响应中返回受影响范围，供页面直接重读相关 direct API。
- 成功后返回与 GET 相同结构，并写审计动作 `bank_auto_tag_rules_updated`。
- 成功保存返回受影响范围并可写入真实后台 outbox/cache warmup 事件；API 请求热路径不得同步扫描全量银行流水、免 OA 批次、关联台或待找发票旧投影。

重新应用当前规则：

`POST /api/bank-details/auto-tag-rules/reapply`

- 需要银行明细写权限。
- 不读取请求体，不修改 `bank_transaction_tags`，不递增 `version`。
- 使用服务器当前已保存的自动标签规则重新计算 direct 规则视图；不会入队页面级 bank_detail 旧刷新任务，也不要求 runtime queue 可用。
- 成功返回 `202`，响应主体包含与 GET 相同的规则结构，并附加 `affected_scope_keys`。不返回 `read_model_status`、`read_model_scope_keys`、`refresh_enqueued` 或 legacy target fields；页面保存/重跑成功后直接重读银行流水。
- 成功后写审计动作 `bank_auto_tag_rules_reapply_requested`，metadata 至少包含当前规则 `version`、`scope_keys` 和 `reason`。
- 该接口只负责确认当前规则重新应用语义；同优先级规则命中多个标签时仍按自动标签规则执行结果进入待确认，不强制选择任一标签。

文件规则替换：

`POST /api/bank-details/auto-tag-rules/file-replacement`

- 需要银行明细写权限。
- 请求体为空时使用仓库内 `fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json` 作为生产基准规则；也可提交同结构 JSON 或 `{ "source": ... }`。
- 后端用文件内普通规则替换当前普通自动标签规则，保留 `内部往来款` 系统规则；能按主标签+子标签复用的标签沿用原 code，无法复用的生成新 code，不在文件内的旧普通规则归档。
- 文件内普通规则全部写入 priority `2`，并用 `sort_order` 保留文件顺序；`内部往来款` 仍是固定系统规则 priority `1`。
- 被归档标签若被待找发票规则或免 OA 批量标签选择引用，后端同步移除引用并审计。
- 成功后触发 `bank_auto_tag_rules_changed` 生命周期事件，并返回受影响范围供页面直接重读银行明细。

错误响应保持 JSON envelope：

```json
{
  "error": {
    "code": "invalid_bank_auto_tag_rules_request",
    "message": "自动标签规则无效。",
    "details": {
      "field_errors": [
        { "field": "active_rules[0].rules.match_fields", "message": "匹配字段不能为空。" }
      ]
    }
  }
}
```

## 工作台 DTO

工作台 DTO 必须保留稳定的分页、summary、group、relation、exception 和 source version 字段，不再把 legacy status fields 作为页面合同。新增字段只能向后兼容添加；删除、重命名或改变含义需要同步更新前端 DTO、测试和本文档。

Workbench row payload 可包含可选对象身份字段：`object_identity`、`object_identity_key`、`object_identity_kind`、`object_identity_source`、`object_identity_confidence` 和 `identity_alias_rows`。这些字段用于后端投影审计、跨区重复治理和详情解释；前端不得依赖它们替代 row id 执行动作，旧客户端未读取这些字段时响应仍必须可用。

Workbench row payload 还可包含可选来源 OA 字段：`source_oa_id`、`source_oa_row_id`、`derived_from_oa_id` 和 `oa_row_id`。这些字段是多 OA active relation 内做横向子分段的后端事实证据；银行流水或发票行有确定归属时应由 direct query/relation distribution 写入，前端只消费这些字段做同源同排展示。无法确定归属时后端不得臆造 source OA，应通过 `special_metadata.row_alignment.unresolved_row_ids` 和审计工具暴露。

## 发票生命周期状态

待找发票、进项发票使用情况、OA 待付款核对、销项发票收款情况和税金抵扣的 lifecycle 字段保持原响应 shape：

- 待找发票：`invoice_acquisition_status`
- 进项发票使用情况：`paymentStatus`
- OA 待付款核对：`paymentStatus`
- 销项发票收款情况：`collectionStatus`
- 税金抵扣：`certified_status` / `is_locked_certified`

这些字段的规则来源必须是 `InvoiceLifecyclePolicy`；各页面通过自己的 direct query/service 组装 lifecycle 字段。新增页面不得在 API、query service 或 worker 中新增 `invoice_lifecycle` read model、SQL projection 或私有生命周期状态规则。

## 待找发票 API

`/api/pending-invoices*` 维护支出/收入流水发票获取状态、候选进项发票、规则建议、选择已有发票关系、收入状态覆盖和导出。

契约要求：

- 列表响应必须包含 rows、summary、filters 和可解释的业务状态字段；不得包含页面级 read model 状态。
- filter-options 必须来自后端事实，前端不能根据当前页 rows 自行构造全局选项；表头下拉筛选通过 `filters` JSON 提交，字段之间按 AND 组合，同一字段内多值按 IN 组合。
- `filters` 支持四区表字段：`counterparty_name`、`transaction_tag`、`bank_account`、`direction`、`seller_name`、`oa_applicant`、`oa_application_type`、`project_name` 等；direct query service 是页面字段语义事实源，legacy SQL projection 只能跟随该语义。
- rows 中 `bank_transactions`、`input_invoices` 和 `oa` 都可以携带 `primary`、`relation_count`、`linked_relation_count`、`has_multiple`、`detail_mode` 和 `summaries`。同一 linked 或 candidate relation 下多笔银行流水、多张进项/销项发票或多张 OA 必须来自统一 `workbench_relation` distribution 并聚合为一条待找发票行；多项时前端用 `+N` 表达该类型全部成员，不再同时展示任一成员作为 primary，且同一多流水 relation 的其它成员不得再作为 standalone 行重复出现。
- `bank_transactions.payment_summary.paid_total` 表示 relation 下 linked 流水合计；`input_invoices.payment_summary` 继续表达发票合计、已付合计、待付金额和差额。候选 relation 可以作为证据展示，但业务状态和 linked-only 金额判断仍只能使用 linked 成员。
- 关系详情和候选发票接口必须返回来源、匹配原因、冲突原因和可操作权限；关系详情必须能表达同一关系中的全部付款流水、发票、OA 和 relation case id。`GET /api/pending-invoices/rows/{transaction_id}/relation-detail` 可接收 `kind=all|bank|invoice|oa`，默认 `all` 保持全量兼容；`bank`、`invoice`、`oa` 只返回对应类型列表，供 `+N` 分栏展开。
- `requires_invoice` 在列表、filter-options 和导出中是“需要开票”状态桶，不是 `filter_group='requires_invoice'` 的 SQL/规则分组条件。支出状态桶包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`；收入状态桶包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只用于解释规则命中和表头规则列筛选。
- 支出状态下拉中的 `已支付待开票` / `已支付已开票` 是 `requires_invoice` 状态桶下的状态快捷筛选，前端通过 `filter=requires_invoice` 加 `filters=[{"field":"status_code","operator":"in","values":[...]}]` 提交，不把状态码伪装成规则组。
- `POST /api/pending-invoices/invoice-candidates/batch` 接收 `transaction_ids` 和候选发票筛选/排序/分页字段，返回 `selection_summary.transaction_count`、`selection_summary.bank_total`、候选发票 rows 和 pagination。该接口按选中流水合计金额计算 `amount_difference_abs`，只支持支出流水选择进项发票。候选 rows 继续保留 `remaining_amount` 兼容旧调用方，但用于“流水关联”展示的事实字段是 `bank_relation_status` 和 `linked_bank_transaction_count`；`bank_relation_status` 可为 `unlinked`、`linked`、`already_selected`、`conflict`，不得由前端用剩余金额推断。
- `POST /api/pending-invoices/attach-existing-invoices/preview` 接收 `transaction_ids`、`invoice_ids` 和可选 request id，返回 `transaction_summaries`、`invoice_summaries`、`selection_summary.bank_total`、`selection_summary.invoice_total`、`selection_summary.difference_amount`、`payment_impact`、`warnings`、`conflicts` 和 `can_confirm`。`selection_summary.difference_amount` 是本次选择差额；关联后待付使用 `payment_impact.remaining_amount_after`。preview 不写最终 relation；当 `can_confirm=false` 时，`conflicts` / `warnings` 必须足以向前端解释确认按钮不可用的原因，`conflicts` 可以是结构化 relation 冲突对象。
- `POST /api/pending-invoices/attach-existing-invoices` 接收 preview id、`transaction_ids`、`invoice_ids` 和 request id；confirm 必须幂等写入一条 Workbench active pair relation，返回 `affected_transaction_ids`、`affected_invoice_ids`、`affected_months`、`relation_case_id` 和 `relation_mode`。若选中发票已处于兼容的 bank+invoice 或 OA+invoice active relation，confirm 必须把既有 rows 和本次选择合并到同一个 active case；后续通过关联台 withdraw 该 active case 时应恢复 confirm 前上一 active 状态。
- `PUT /api/pending-invoices/income-statuses` 接收 `transaction_ids`、`status_code` 和 request id；`status_code` 只允许 `income_no_invoice_required` 或 `cash_income`。后端必须在写入前一次性校验重复 ID、非收入流水、已关联销项发票、非法状态和不可标记状态；任一失败时整体拒绝，不允许部分成功。成功后写一条 income status command/audit/finalizer，返回 `affected_transaction_ids`、`affected_months` 和更新后的 rows。
- `POST /api/pending-invoices/manual-invoices/preview` 和 `POST /api/pending-invoices/manual-invoices` 不属于当前待找发票 HTTP contract；新写入口必须保持不可达并返回 `not_found`。历史 manual invoice command 只作为旧数据恢复/迁移兼容留在 service 层。
- 写入类接口需要返回 affected months/objects、version 或 job，供页面局部刷新和跨页事件使用；mutation 成功响应返回 `affected_scope_keys` 时不得同时返回 `read_model_scope_keys`。
- 导出字段应与当前筛选和权限一致，不能绕过列表口径。
- rows、filter-options、export-preview 和 export 是 direct business payload/file contract，不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_key(s)` 或 `refresh_enqueued`。legacy 投影的 missing/stale/source mismatch 只属于后端下线前诊断；页面只呈现 direct loading/error/empty 和业务 rows。

## 进项发票使用情况 API

`/api/input-invoice-usage*` 维护进项发票、付款状态、OA 和银行流水的列表、详情、筛选、导出、支付规则和反提 OA 工作流。

契约要求：

- rows、filter-options、export-preview、export 和 relation-details 是 direct business payload/file contract，不返回 `read_model_status`、`readModelStatus`、`read_model_scope_key`、`refresh_enqueued` 或等价旧同步字段；legacy 投影的 missing/stale/source mismatch 只属于后端下线前诊断。关系详情不可用时返回 `200` 和 `detailAvailable=false`。
- 表头筛选通过 `filters` JSON 提交。字段之间按 AND 组合，同一字段内多值按 IN 组合；两列组合筛选仍按字段 AND 组合，例如 `oa_applicant` + `oa_application_type`、`bank_account` + `bank_direction`。
- filter-options 必须由后端返回，前端不能根据当前页 rows 推导全局选项。当前页面可筛选字段包括 `seller_name`、`payment_status`、`oa_applicant`、`oa_application_type`、`oa_project_name`、`bank_counterparty_name`、`bank_account`、`bank_direction`。
- `seller_name` 的前端列名为 `销方名称`。`bank_account` 展示为银行名称加账号后四位；`bank_direction` 原始值保持后端事实值，前端展示为 `收入` 或 `支出` chip。
- 发票号码列表头只提供开票日期排序，不提供下拉筛选。排序通过 `sort_field=invoice_date` 和 `sort_direction` 提交。
- 支付状态列表只展示状态标签；规则原因和自动闭环解释不在列表行内展示。
- rows 中 `oa`、`bankTransactions` 和 `invoiceRelations` 都可以携带 `relationCount`、`hasMultiple`、`detailMode`、`relationStatus` 和 `summaries`。同一 linked 或 candidate relation 下多条 OA、银行流水或进项发票必须聚合为一条发票使用情况行，金额字段返回各自合计；前端用 `detailMode=list` 显示 `+N` 并通过 `/rows/{row_id}/relation-details?kind=oa|bank|invoice` 展开全部明细。
- `relationStatus="candidate"` 表示来自关联台未配对区 open/proposed 候选，只能展示为候选证据；支付状态、已支付判断和 confirmed relation 判断只能使用 `relationStatus="linked"`。后端不得把 candidate 映射为 active。
- `/rows/{row_id}/relation-details` 由 direct query service 返回当前业务 detail payload；不可用时只返回业务 `detailAvailable=false` 诊断，不得把 legacy sync diagnostics 透传到页面合同。
- 反提 OA 工作流按 `preview -> one-step create OA draft -> staged draft -> user submission confirmation -> submitted history / local rollback` 推进。前端只暴露 `创建 OA 草稿` 一个创建动作；后端可以继续保存内部 batch，但不得把 `创建本地批次` 作为用户概念暴露。创建 OA 草稿只表示外部 OA 草稿已生成，状态为 `oa_draft_created`，该状态在 UI 中展示为 `暂存`，不得直接等同于已提交 OA 流程。
- `/api/input-invoice-usage/oa-reverse/preview` 必须把可创建候选和 rejected invoice 明确分开。已有 active/linked OA 关系的发票不得进入候选或创建草稿 payload，rejected row 必须带 `reasonCode=already_has_active_oa`、`oaRelationStatus=linked` 以及发票号、销方、开票日期、价税合计、支付状态等展示字段，供前端显示 `已关联oa`、禁用勾选和按 OA 关联状态筛选。关联台未配对区 open/proposed OA candidate 也不得进入候选或创建草稿 payload，rejected row 必须带 `reasonCode=already_has_candidate_oa`、`oaRelationStatus=candidate` 和同样的展示字段，供前端显示 `候选oa`、禁用勾选和筛选。可创建候选前端展示为 `未关联oa`，对应 `oaRelationStatus=unlinked` 或缺省值。
- 进项发票反提 OA 草稿使用支付申请 form `2` 的标准草稿 payload：顶层包含 `formId`、`isDraft`、`data`，`data.userName`/`data.applicant` 来自用户选择的目标 OA 申请人，`data.cause` 必须包含本地反提批次 ID，供 OA 投影回扫识别。
- `POST /api/input-invoice-usage/oa-reverse/oa-draft` 是当前一键创建入口。请求必须携带 preview id/hash、幂等 key、目标申请人和选中发票；后端重新校验候选、权限和目标申请人凭据后，用目标申请人凭据/token 创建 `isDraft=true` OA 暂存草稿。不得使用当前操作人的请求 token 创建目标申请人草稿。
- `GET /api/input-invoice-usage/oa-reverse/staged-drafts` 返回状态为 `oa_draft_created` 的暂存批次，供用户在关闭确认弹窗、刷新或重新打开 drawer 后恢复二选一。前端暂存列表不得展示 OA 草稿链接，只展示批次摘要和两项处理动作。
- 用户在 OA 页面处理草稿后，前端必须让用户选择 `submitted` 或 `not_submitted`。`submitted` 对应 `我已在OA系统提交该草稿 / OA正在进行中`，进入本地 `submitted_confirmed` 历史；`not_submitted` 对应 `OA提交内容需修改 / 删除本次提交内容`，只清理 FinOps 本地当前草稿字段并回到可重新创建状态，不展示为已提交历史，也不调用 OA 删除外部草稿。关闭确认弹窗不得调用该接口或清理 batch。
- `GET /api/input-invoice-usage/oa-reverse/submitted-history` 只返回业务可读字段，例如目标申请人、确认时间、金额、发票张数和发票摘要；不得返回 `batchId`、`oaDraftId`、`previewHash`、英文内部状态、密码、密文或 token。

## OA 待付款 API

`/api/oa-pending-payments*` 维护 OA 待付款、付款流水和进项发票关系核对。

契约要求：

- rows、filter-options 和详情接口使用同一 direct query service 事实源。
- rows 和 filter-options 接受 `view_mode=completed|in_progress`，默认 `completed`。`completed` 读取普通 `app.oa_applications` / completed OA projection 中已完成或历史未知 workflow status 的 OA；`in_progress` 才由 OA 待付款专用 payment-admitted projection 提供，先由 OA MySQL `t_payment_simple.flow_id` 准入，再匹配 OA Mongo `form_data._id`。未匹配到准入 flow_id 的进行中 OA 不进入正常列表。
- `t_payment_simple.id` 不是 OA ID，不能作为 OA 匹配 key；OA 匹配和写回 key 必须使用 `flow_id` 对应的 OA Mongo 文档 ID。
- rows、filter-options 和 detail drawer 是 direct business payload contract，响应不返回 `read_model_status`、scope key、stale reasons 或 refresh job；legacy missing/stale/source mismatch 只属于后端下线前诊断。detail 不可用时返回 `200` 和 `detailAvailable=false`。
- rows `summary` 必须包含 `viewCounts.completed/in_progress`，用于页面展示切换按钮数量；该统计使用同一搜索、月份、交易日期和 column filters，但不受当前 `view_mode` 限制。
- rows 中 `oa` 必须携带 `workflowStatus`；`oa`、`bankTransaction`、`invoice` 都可以携带 `relationCount`、`detailMode` 和 `summaries`；同一 Workbench active relation 下多条 OA、支出流水或进项发票必须聚合为一条核对行，金额字段展示各自合计。
- `paymentStatus` 不返回 `overpaid` 或 `merged_paid`；支出流水合计大于 OA 合计时返回 `pending_review`，多 OA 合并付款按 relation group 合计后判定。
- rows 可返回 `oaPaymentWriteback`，用于表达 OA MySQL `t_payment_simple` 写回状态。`oaPaymentWriteback.code` 至少支持 `written` / `not_written`，`syncStatus` 表达 `ready`、`unavailable`、`flow_id_missing` 或 `not_required` 等同步语义。
- 详情接口返回 OA、付款流水、发票、候选关系和异常原因；`/rows/{row_id}/relation-details` 支持 `kind=oa|bank|invoice`。
- `filterConfig`/`filter-options` 至少包含 OA 申请人、项目名称、支付状态、对方户名、银行账户、收支、发票方和开票日期等表头筛选/排序字段；银行账户字段使用“银行名称 + 账号后四位”，收支字段使用 `outflow`/`inflow` 值并显示“支出”/“收入”。
- 外部依赖或详情数据源不可用时返回明确业务错误或 stale 状态，不返回 HTML 或空 body。

### OA 自动匹配和自动写回

`POST /api/oa-pending-payments/auto-reconcile-bank-transactions`

请求 body：

```json
{
  "month": "2026-06"
}
```

契约要求：

- 后端必须用写权限校验 actor，不接受前端仅隐藏按钮作为权限事实。
- `month` 可省略，省略时按当前页面 all scope 扫描；有值时必须是 `YYYY-MM`。
- 自动匹配只用于 `workflowStatus=in_progress` 的 OA 与未配对支出流水，规则必须复用关联台 OA-bank 精确金额/精确合计规则。不得在该接口中新增模糊匹配、名称相似度猜测或收入流水匹配。
- completed 和 in-progress 只要已经存在有效 Workbench active 支出流水 relation，且支出流水合计等于 OA 金额，也必须由该接口自动写回。
- 写回前必须校验银行流水存在且方向为支出、支出合计等于 OA 金额、可解析 OA Mongo 文档 ID，并将 `t_payment_simple.flow_id` 对应记录写成 `pay_status=1`；缺记录时可插入一条已支付记录。Flowable 流程实例 ID 和流程请求 ID 不作为 `t_payment_simple.flow_id` 写回 key。
- 成功响应返回 `success`、`action`、`month`、`autoMatchedCount`、`writebackCount`、`autoMatchedRelations`、`oaPaymentWritebacks` 和 `affected_scope_keys`；页面写成功后直接重读 rows，不读取旧 `readModelRefresh` 或旧 operation barrier target。
- 失败时返回可展示业务错误；金额、方向或 `flow_id` 校验失败不得半写 `t_payment_simple`。

`GET /api/oa-pending-payments/bank-transaction-candidates`

该接口为进行中 OA 的“关联支出流水”抽屉提供候选支出流水。

查询参数：

- `relation_status=all|unmatched|matched|linked_in_progress`，默认 `all`。
- `keyword`，可选，按候选 payload 做关键字筛选。
- `page` / `page_size`，默认 `1` / `100`，`page_size` 上限为 `200`。
- repeated `oa_row_ids`，可选。抽屉从已选 OA 打开时必须传入；后端按这些 OA 的 `month` 限定候选支出流水月份并去重。没有 OA 上下文的旧调用才保留全部支出流水语义；有 OA id 但无法解析月份时返回空候选，不得退回全量历史扫描。

响应 `filters` 必须回显 `relationStatus`、`keyword`、`oaRowIds` 和 `monthScopes`，便于诊断候选池是否按 OA 月份收敛。

`POST /api/oa-pending-payments/link-bank-transactions`

该接口是自动匹配失败后的人工兜底。请求仍由前端传入选中的 `oa_row_ids` 和 `bank_transaction_ids`，后端只允许未配对支出流水创建 Workbench active relation。关联成功后必须沿用同一写回校验；支出合计等于 OA 金额且可解析 `flow_id` 时，响应必须携带 `autoWriteback` 和 `oaPaymentWritebacks`，并把 `t_payment_simple.pay_status` 写为已支付。前端不再提供人工 `confirm-paid` 写回按钮。

### 工作台 row detail

`GET /api/workbench/rows/{row_id}?month=all`

该接口返回单条 OA、银行流水或发票 row 的详情 payload，用于三栏详情弹窗。`row_id` 必须 URL encode；`month` 可为 `all` 或 `YYYY-MM`，作为 direct query scope hint。

契约要求：

- 读取优先级是 live service / in-memory cache / 明确的 legacy row-detail fallback；live/cache miss 后不得只依赖从 row id 解析月份。
- 公开页面合同不得通过 Workbench legacy active generation 或 read-model facade 暴露旧同步字段。该接口只读详情，不写 relation，也不接入 `WorkbenchRelationCommandService`。
- 找不到 row 返回 `404`；detail source 暂不可用时返回 `200`、`detailAvailable=false`，不触发页面刷新队列，不返回 HTML、空 body 或 legacy sync diagnostics。

### 工作台后台刷新状态

公开 `GET /api/workbench/refresh-status` 和 `GET /api/workbench/events` 已移除。关联台页面读取 `/api/workbench*` direct payload，写后通过 operation projection 或直接重读业务 GET 更新；后台 matching worker、outbox、matching diagnostics 和 worker lag 只通过 App Health、日志、数据库巡检或运维工具诊断，不作为页面 API 合同或默认 SSE SLO。

## ETC 业务批次 API

ETC 对账任务、ZIP 导入和 OA 草稿提交统一使用 `/api/etc/business-batches*` 作为新增契约层。它取代前端直接拼接 `EtcImportBatch` 和 `EtcBatch` 的展示口径，旧 `/api/etc/batches*` 只作为过渡兼容入口，不应继续扩展。

契约要求：

- 响应必须区分导入批次、业务批次、OA 草稿和人工提交确认状态；ETC 专用 OA 自动检测状态不再作为业务批次 API 合同输出。
- `GET /api/etc/business-batches` 的 `month` 参数按 ETC 发票开票日期、通行开始日期和通行结束日期任一月份匹配业务批次。响应中的 `counts.active`、`counts.submitted` 必须先应用同一组 scope、`month`、`plate`、`keyword` 筛选，再按状态 bucket 统计；`items` 在同一筛选结果上继续应用请求的 `status` 和分页。
- 用户可见批次列表必须以 `/api/etc/business-batches*` 为事实源；`/api/etc/reconciliation-tasks` 只承载导入、核对、source file 和 workflow 状态，前端不得把 task-only 记录无条件混入批次列表或批次计数。
- `POST /api/etc/business-batches` 可以省略 `taskId`。省略时后端 application service 必须复用现有 reconciliation task service 先创建任务，再通过 business batch service 创建 active 业务批次，并返回统一 `businessBatch` payload；若业务批次创建失败，必须通过 reconciliation task service 删除/tombstone 本次新建任务，避免留下 task-only 空批次。传入 `taskId` 时仍按既有绑定任务语义校验 active business batch 约束。
- 幂等 key、重复提交、撤销草稿和释放发票规则必须由后端校验。
- 权限不足、状态冲突、发票占用、OA 草稿失败和撤销失败需要返回稳定错误码。
- dry-run、迁移和人工确认动作要返回 affected batches、affected invoices、affected months 和审计信息。
- ETC 页面创建 OA 草稿后，业务批次状态为 `oa_confirmation_pending`，使用 `POST /api/etc/business-batches/{id}/manual-oa-status` 确认 `submitted` 或 `not_submitted`。
- ETC 专用 OA 自动检测入口已移除：后端不再提供 `/api/etc/business-batches/{id}/oa-status/refresh`，不再输出 `oaDetection*` 字段，也不再注册 ETC OA 检测 worker 或 detector adapter。
- `submitted` 人工确认成功后，后端必须同时闭环该业务批次绑定的 ETC 对账任务，并在关联台 open 区投影一条 `source_kind=etc_invoice_summary` 的折叠汇总发票行。该行金额优先使用业务批次上报金额，不使用散票合计覆盖；散票继续作为折叠明细，不直接散落展示。
- `etc_invoice_summary` 在没有 OA 和银行流水三项完全匹配前必须保持 open/pending 状态，关系标签显示待匹配 OA/流水；只有关联台普通配对逻辑确认三项关系后，才进入已配对区。
- `DELETE /api/etc/business-batches/{id}` 对任意阶段业务批次执行本地删除/reset，不撤销 OA。请求可带 `expectedVersion` 做并发保护，不要求删除原因；成功响应至少包含 `deleted=true`、`businessBatchId`、`kind`、`releasedInvoiceCount` 和关联删除结果。后端必须删除该批次本地创建/导入的 ETC 对账任务、导入来源、核对结果、提交批次元数据和 ETC 发票；若已提交批次存在 `etc_invoice_summary`，必须释放 ETC 发票合并关系并刷新 Workbench，使原 `etc_invoice_summary` 消失。若该 summary 已参与 active relation，删除时通过 canonical relation command 取消包含该 summary 的 relation，OA 和银行流水不得恢复成二栏 active relation。`workbench_relation` distribution/direct payload unavailable 不得阻断该删除/reset；写安全以权限、expected version、canonical relation 状态、持久化和 outbox/affected-scope diagnostics 为准，失败时返回对应稳定错误码。
- ETC 对账任务和业务批次源文件上传必须先落对象存储，再追加 source file 元数据。对象存储不可写时返回稳定错误码 `reconciliation_file_storage_unavailable` 和 HTTP 503，上传不得留下半写入的 source file、版本号或审计事件。`/api/etc/reconciliation-tasks/{task_id}/credit-card-statement`、`/ticket-root-files`、`/ticket-root-texts`、`/supplement-evidences` 使用直接错误结构 `{ "error": "...", "message": "..." }`；`/api/etc/business-batches/{id}/source-files` 使用 business batch envelope `{ "ok": false, "error": { "code": "...", "message": "..." } }`。

## AppHealth 运维 Dashboard API

`GET /api/operations/app-health-dashboard`

权限：

- 复用 OA session。
- 仅 `can_admin_access=true` 的管理员可访问。
- 未登录或登录态失效返回现有 `401 invalid_oa_session`。
- 非管理员返回 `403 admin_only`。

该接口独立于 `/api/app-health`。`/api/app-health` 仍用于全局健康状态、SSE、多标签页同步和写操作 gating。

响应结构：

```json
{
  "generated_at": "2026-05-23T10:00:00+08:00",
  "data_inventory": {
    "bank": {
      "total_count": 128,
      "latest_synced_at": "2026-05-23T09:50:00+08:00",
      "status": "available",
      "sources": []
    },
    "invoice": {
      "total_count": 256,
      "latest_synced_at": "2026-05-23T09:48:00+08:00",
      "status": "available",
      "sources": []
    },
    "oa": {
      "total_count": 72,
      "latest_synced_at": "2026-05-23T09:45:00+08:00",
      "status": "available",
      "sources": []
    }
  },
  "request_performance": {
    "window": {
      "type": "process_rolling_window",
      "sample_limit_per_endpoint": 512,
      "reset_on_restart": true
    },
    "endpoints": []
  },
  "runtime_performance": {
    "outbox": {},
    "queues": [],
    "workers": []
  },
  "freshness": {
    "warnings": []
  }
}
```

契约要求：

- Dashboard 只返回页面需要的聚合读数据，不返回业务 payload、snapshot、raw payload、token、数据库 URL 或 RabbitMQ URL。
- `data_inventory.invoice.sources` 固定包含 `standard_import`、`oa_attachment`、`etc`、`manual`。
- `request_performance.endpoints[*]` 包含 `duration_ms`、`database_duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_query_count` 的 p50/p95/p99。
- `runtime_performance.queues[*]` 基于已知 RabbitMQ route 输出，即使 RabbitMQ Management API 不可用也保留行，数值为 `null`。
- `runtime_performance.workers[*]` 展示 required/optional worker heartbeat、missing/stale/mismatch 和 transport 配置事实；页面 legacy projection readiness 不再进入 operations dashboard payload。
- Dashboard API 可返回短 TTL 缓存 payload。缓存刷新失败但已有旧 payload 时，响应仍为 `200`，并在 `freshness.warnings` 中包含 `dashboard_cache_stale_after_error`。
- unknown 指标用 `null` 和 `status="unknown"` 表示。前端显示 `--`，不得把 unknown 当成 `0`。

## 版本和兼容

当前项目仍保留部分旧接口。新增能力应优先接入 `/api/*` 契约层；旧接口只用于兼容测试或历史页面，不应继续扩展。

## 销项发票收款情况 API

`/api/output-invoice-collections/*` 由 Invoices 模块承接。`server.py` 只做 HTTP dispatch、统一 JSON/error 包装和 route object 装配；参数解析、权限 gate 与业务调用在 `app/routes_output_invoice_collections.py`，业务事实写入在 service/repository 层。

读接口：

- `GET /api/output-invoice-collections/rows`：返回 direct business payload；route 直接调用 query service 并叠加 lifecycle facts，不读取 SQL read-model provider。响应不返回 `read_model_status`、`readModelStatus`、`read_model_scope_key`、`refresh_enqueued` 或等价旧同步字段，包含 `summary`、统一关系 `oa`、`bankTransactions`、`invoiceRelations`、手动状态/提醒、人工红蓝票关系和正式收据摘要。
- `GET /api/output-invoice-collections/filter-options`：基于同一行集生成筛选项。
- `GET /api/output-invoice-collections/status-rules`：返回 Sheet6 静态规则、手动状态选项和权限。
- `GET /api/output-invoice-collections/receipts/history?invoice_id=...`：返回正式收据 lifecycle facts，不再伪造空历史。
- `GET /api/output-invoice-collections/rows/{row_id}/relation-details?kind=oa|bank|invoice|red_invoice|receipt`：返回当前 row 对应关系摘要。`kind=oa|bank|invoice` 必须来自 `workbench_relation` 统一分发事实源；`summaries` 展示该 relation 下全部 OA、收入流水或销项发票项，`relationCount` 为该类对象总数。前端在 `detailMode=list` 且 `relationCount>1` 时以 `+(relationCount-1)` 展开全部明细；销项发票栏必须同时展示当前行发票主信息和 `invoiceRelations.totalWithTax` 多张发票合计，不能只显示展开入口。

rows 中统一关系字段要求：

- `oa`、`bankTransactions`、`invoiceRelations` 都携带 `primary` 或兼容 primary 字段、`relationCount`、`hasMultiple`、`detailMode`、`summaries`；多项时 `detailMode=list`。
- `bankTransactions.receivedTotal` 只统计 linked 收入流水；`relationStatus="candidate"` 的流水可作为候选证据展示，但不得计入已收款和 confirmed relation 判断。
- SQL payload 缺少 `oa`、`bankTransactions`、`invoiceRelations`、`redInvoiceRelation` 或 `receipt` 任一结构字段时只属于后端 legacy projection 治理；页面 rows/filter/export/detail contract 不读取该 payload，不能因此返回 `202 refreshing` 或旧同步字段。relation detail 不可用时只返回 `detailAvailable=false`。

写接口：

- `PUT /api/output-invoice-collections/rows/{row_id}/collection-status`
- `PUT /api/output-invoice-collections/rows/{row_id}/collection-reminder`
- `DELETE /api/output-invoice-collections/rows/{row_id}/collection-reminder/{reminder_id}`
- `POST /api/output-invoice-collections/rows/{row_id}/red-invoice-relations`
- `DELETE /api/output-invoice-collections/red-invoice-relations/{relation_id}`
- `POST /api/output-invoice-collections/rows/{row_id}/receipts`
- `POST /api/output-invoice-collections/receipts/{receipt_id}/void`
- `POST /api/output-invoice-collections/receipts/{receipt_id}/reissue`
- `GET|PUT /api/output-invoice-collections/receipt-settings`

写接口必须使用 OA session 派生的 `actor_id`、tenant 和权限布尔值；service 不读取 headers。PostgreSQL 模式下 lifecycle facts 和真实 outbox side effects 必须在同一事务内提交；不得恢复页面 read-model dirty scope。正式收据创建必须提供 `Idempotency-Key` 或 body `idempotencyKey`。
