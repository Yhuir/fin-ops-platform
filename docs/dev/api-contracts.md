# API 契约

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
- `/api/bank-flow-rule-batches/*`：流水规则批量处理。
- `/api/no-oa-bank-batches/*`：免 OA 批次 legacy。
- `/api/etc/business-batches*`：ETC 用户可见业务批次、补充导入、OA 草稿和 OA 提交人工确认。
- `/api/tax-offset*`：税金抵扣和已认证导入。
- `/api/cost-statistics*`：成本统计、下钻和导出。
- `/api/bank-details*`：银行明细、自动分类展示和 XLSX 导出。
- `/api/pending-invoices*`：待找发票列表、筛选、关系明细、候选进项发票、规则和导出。
- `/api/background-jobs*`：后台任务。
- `/api/app-health*`：健康状态。
- `/api/operations/app-health-dashboard`：管理员只读运维观测 Dashboard。
- `/api/operations/app-health/page-audit?page=input-invoice-usage`：管理员只读进项 canonical/shared/consumer 对账审计。
- `/api/operations/app-health/page-audit?page=output-invoice-collections`：管理员只读销项 canonical/shared/consumer 对账审计。
- `/api/operations/app-health/page-audit`：管理员只读页面业务 read model / relation 全量对账审计。
- `/api/operations/history`、`/api/operations/history/actors`、`/api/operations/history/{operation_key}`：仅 005 可读的逻辑操作列表、操作人选项与详情。
- 进项使用、销项收款和待找发票的旧 AppHealth refresh routes 已删除并返回 `404`；统一 page audit 保持只读。

### 操作历史 API

`GET /api/operations/history` 只返回 `audit.coverage_started` 覆盖点后的记录，先按 `request_id` 将 requested/completed 及同请求领域事件聚合为一条逻辑操作，再执行 `limit<=200`、cursor、时间、actor、page、action、outcome 和 search；响应为 `{rows,next_cursor}`，每行包含稳定 `action_code/action_label/action_description/object_label`。`GET /api/operations/history/actors` 返回操作人下拉选项。`GET /api/operations/history/{operation_key}` 返回用户可读的固定 `detail`：`target`、`artifacts[]`、`records[]`、`changes[]`、`failure` 与 `legacy_evidence_missing`；文件仅在 `availability=available` 时提供受保护 `preview_url`，删除/失败不提供预览；不返回 raw payload 或审计 event/request/trace/object 内部 ID。三个接口仅允许固定权限管理员 005，普通账号返回 `403 admin_only`。

生产 unsafe HTTP 请求在业务 mutation 前追加 `operation.requested`，请求结束后追加同一 `request_id` 的 `operation.completed`。requested 持久化失败时返回 `503 operation_audit_unavailable` 且业务写不得执行；completion 失败保留 requested 事实并输出不含敏感数据的结构化错误。领域 service 继续记录业务 before/after；银行流水和发票受保护事实修正还必须在同一数据库事务提供 actor/reason，由数据库追加 correction/audit。

### 银行流水文件预览与字段映射

- `POST /imports/files/preview` 的银行文件只使用 `template_code=bank_statement`。成功文件返回 `preview_ready`；已定位表头但核心字段不完整时返回 `unrecognized_template`，同时返回 `header_signature`、`mapping_candidates[{key,label}]`、`mapping_fields[{key,label,selected,required}]`、`field_mapping` 和 `mapping_source`，且不生成可确认 rows。
- `POST /imports/files/retry` 可在 `overrides[file_id].field_mapping` 提交 canonical 字段到源列 key 的映射。服务端必须校验列存在、核心日期/金额组合完整和方向合同；失败仍保持不可确认，成功重新生成 preview。
- `GET /api/import-facts/files?page&page_size` 与 `GET /api/import-facts/batches?page&page_size` 是运行探针和导入事实审计使用的只读摘要合同；不得返回完整预览 payload。`GET /imports/batches/{batch_id}/errors.csv` 只输出错误/需复核行的用户可读字段，下载文件名不得暴露内部 ID。
- 相同文件内容以 SHA-256 判断，不受文件名影响；同批或历史已确认文件命中时返回 `duplicate_file`。银行来源控制合计不一致返回 `source_control_mismatch` 且不可确认。
- 字段映射仅属于 import file/session 的解析审计信息，不是 canonical 银行交易事实；confirm 仍只接受 `preview_ready` 文件，并继续执行去重、preview stale 和账户冲突合同。

### 银行流水手工录入预览

`POST /imports/bank-transactions/manual/preview`

- 需要数据写权限并经过共享 mutation guard；操作人只取认证 session，不接受 body 中的身份字段。
- 请求为 `{ "transactions": [...] }`，数组长度 1–50。每项必须包含 `bank_mapping_id`、完整 `account_no`、`direction=inflow|outflow`、正数 `amount`、`balance`、秒级 `trade_time`、三位 `currency`、`counterparty_name`，以及 mapping 对应的官方参考号字段：建行 `account_detail_no`，光大 `enterprise_serial_no`，其余当前银行为 `bank_serial_no`。
- mapping 不存在、银行未登记明确手工字段合同、完整账号尾号不匹配、字段缺失/非法或本批出现相同强 identity 时返回明确 `400/409`，不创建 preview session。未知银行不得套用通用流水号字段兜底；服务端对整批 canonical identities 做有界批量预载，不逐笔查询数据库。
- 成功返回 `{values,file_ids,import_session}`。`import_session.files` 与输入顺序一一对应并携带逐笔 row decision；`file_ids` 只包含 `created` 项。`duplicate_skipped`、`suspected_duplicate` 和错误项可展示但不可确认。
- 返回修改或关闭抽屉调用现有 `POST /imports/files/discard`；正式提交调用现有 `POST /imports/files/confirm`，继续复用 durable `file_import` job、preview stale、幂等、审计和 canonical 写入合同。

## 页面标题完整性统计契约

银行明细、OA 待付款、外部往来款、ETC 业务批次、税金抵扣、待找发票、进项发票使用、销项发票收款、关联台和成本统计的现有页面主响应可以携带 additive `statistics` 对象。前端默认复用该对象；只有本文件明确登记的首屏热路径可以用同一 endpoint 的非阻塞统计请求，禁止新增跨页统一统计接口。

- `statistics` 由当前 endpoint 所属页面的主查询或已发布 read model 计算，不从 Page Audit 或跨页统一统计接口回填。
- `statistics` 始终覆盖页面未应用 month/search/filter/sort/page 前的完整范围，因此同一已发布版本下改变这些参数不会改变统计对象。
- read model 页面只有在完整范围 freshness 可证明时返回数字；否则 `statistics=null`。请求的月份或当前页 fresh 不能替代 all/parent 统计 freshness。
- direct-canonical ETC 页面在业务批次列表主查询中同时计算未筛选统计；成功响应不增加另一条浏览器请求。
- 所有计数均为非负整数。业务对象按页面合同的稳定身份去重，不能使用当前页行数或折叠组行数代替 OA、流水或发票数量。
- 该字段为 additive contract，不改变原 `rows/items/groups`、`summary/counts`、pagination、filter、sort、ETag 和权限语义。
- 管理员 Page Audit 独立读取 canonical facts 和页面投影做集合、关系与统计重算；Audit 结果不得作为 `statistics` 的输入。

各模块的字段名和恒等式以对应 `docs/modules/<module>/boundary-io.md` 为准。前端对缺失、负数、非整数或超出安全整数范围的值按不可用处理；合法零值必须保留。

## 税金抵扣 API

`GET /api/tax-offset?month=YYYY-MM`

- 每个请求在一个 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 内批量读取 `app.invoices`、`app.tax_certified_import_records` 和最新 saved `app.tax_offset_plans`，再返回 rows、认证匹配分组、默认选择、`summary`、`statistics` 与 `canonical_snapshot_version`。
- 成功固定返回 `200`；空月份返回完整空集，不返回 `read_model_status`、`source_versions`、refresh/polling 字段或 `202`。
- 页面不消费 `read_model.tax_offset*`、Workbench relation、成本统计或其它页面 read model；浏览器刷新重新执行 canonical 查询。

`POST /api/tax-offset/calculate`

- 使用与月查询相同的 canonical repository 计算所选发票金额；非法月份或选择返回 `400`，不会触发 read-model refresh。

`POST /api/tax-offset/plans`

- 请求必须携带 `expected_canonical_snapshot_version` 和 `idempotency_key`。canonical 发票/认证事实已变化时返回 `409 tax_offset_canonical_version_conflict`；成功保存后前端重新 GET。
- 计划写入保持原事务、审计与幂等合同；成功响应只返回 `affected_scope_keys` 与 plan，不返回 freshness target 或 operation barrier。

认证导入的文件解析仍由 import job 完成。job 成功并提交 canonical 认证事实后，税金抵扣页面直接重新 GET；页面请求热路径不解析文件，也不等待 Tax Offset read model。

## 成本统计 API

`GET /api/cost-statistics/explorer`

- `view` 接受 `time|bank_tag|project|expense_type|bank_account`。旧原始 `bank` 返回 `400 invalid_cost_statistics_query`。
- 共用 query 为 `scope`、`view`、可选 `query`、`cursor`、`page_size` 与 `include_statistics`。`query` 折叠空白、最长 200 字符，并参与 cursor identity。
- `project` 可接受 `project_name` 和其后的 `expense_type`；`expense_type` 可接受 `expense_type`；`bank_account` 可接受 `bank_account_label` 和其后的 `project_name`；`bank_tag` 可接受 `bank_tag_primary_label` 和其后的 `bank_tag_sub_label`；`time` 无额外下钻参数。旧 `payment_account_label`、`tag_code`、`primary_tag`、`sub_tag` 不是 explorer 合同。
- 每个请求从一个 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 读取 canonical facts，再返回 `summary`、`statistics`、`facets`、`rows`、`row_count` 与 `next_cursor`。`time|bank_tag` 只读取范围内银行流水和一次批量有效标签投影，并在 OA、active relation、人工分配查询前返回；三个项目成本 view 才生成唯一成本事件集合。
- 三个根 view 的 `summary.total_amount` 与 `transaction_count` 在相同 scope/query 下必须相等；只改变聚合维度。三个项目成本 view 的 `statistics` 包含 `project_count`、`expense_type_count`、`bank_account_count`、`cost_transaction_count`，并在同一只读 snapshot 输出 `transaction_count`、`expense_transaction_count`、`income_transaction_count`。未配置无 OA 项目时，repository 只加载关系成员并通过一次无标签分类的基础聚合读取流水方向数；不得为页头统计加载完整无关流水或触发银行标签分类。两个银行流水 view 继续附带其标签覆盖统计。
- `bank_account` 分面按成本事件 `bank_account_label` 聚合。OA 关系的支出账户恰好一个时归该账户；零个或多个不同支出账户归`银行账户未确定`；收入/退款账户忽略。无 OA 成本使用来源支出账户。
- `time|bank_tag` 使用同一真实银行流水人口。`summary.total_amount=expense_amount-income_amount`；金额保持正数、方向单独返回。`bank_tag` 的主/子标签 facets 同时返回支出、收入、净支出和方向交易数。
- 对已完成 OA 的 active relation，`O=N` 时按 canonical OA 单元原金额形成成本；`O!=N` 时在有效人工分配前不进入成本人口。`N=0` 不形成成本或任务，`N<0` 返回完整性错误，不使用绝对值、旧值或其它 fallback。
- `include_statistics=false` 时 `statistics=null`；内容请求不被辅助全局统计阻塞。
- 成功固定返回 `200`；不返回 `read_model_status`、`statistics_status`、Cost scope/version，也不返回 `202/409 read model not fresh`。
- 数据库或业务计算失败必须返回明确错误；浏览器刷新会重新执行完整请求，不读取旧 payload 伪装成功。

`GET /api/cost-statistics/bank-transactions/{transaction_id}`

- 服务 `time|bank_tag` 的真实流水行和三个项目成本 view 中无 OA `row_kind=bank_transaction` 的成本行。必须携带当前 `view` 与 `scope`；非法参数返回 400，未找到返回 404。

`GET /api/cost-statistics/allocations/{allocation_id}`

- 服务 `project|expense_type|bank_account` 中 `row_kind=oa_allocation` 的行，返回 OA 单元成本、同一正式关系组的支出/付错退款证据和金额核对。银行账户分组是关系层观察维度，不得暗示 OA 单元到具体流水的资金来源归属。
- 两个详情接口都从同一 canonical snapshot 计算，按请求的 `scope`、`view` 有界读取且不加载全局 statistics；不跨页面 API/read model fallback。

`GET /api/cost-statistics/manual-allocations`

- 从一次 relation-only canonical snapshot 全量识别人工任务，不依赖用户浏览过哪些成本项，也不读取 read model、worker 或 cache。`status=pending|allocated` 必填；`query` 规范化后最长 200 字符；`page_size` 为 1..50；cursor 绑定状态、搜索条件和稳定排序。
- 响应返回全局 `pending_count`、`allocated_count`、当前页 `items` 和 `next_cursor`。每个 item 包含关系级 OA 合计、支出、付错退款、净支出、canonical OA 单元、银行流水证据、当前人工分配、可选不计入成本金额、version 与事实指纹；不展示内部 relation ID，但写接口继续使用稳定 `relation_case_id`。
- `bank_events[*]` 固定返回 `transaction_id`、`event_kind`、`amount`、`trade_time`、`counterparty_name` 和 canonical `tags` 标签路径；不返回旧 `summary`，也不从 OA 费用类型、摘要或备注推导标签。关系内全部流水在同一 snapshot 中使用一次批量有效分类投影，不做逐流水查询。
- `pending` 只包含 `O!=N` 且 `N>0` 的已完成 OA active relation；`allocated` 只包含当前事实指纹仍有效的人工记录。`O=N` 任意拓扑自动归因，`N=0` 不产生任务，`N<0` 返回完整性错误。

`PUT /api/cost-statistics/manual-allocations/{relation_case_id}`

- 请求体固定为 `{expected_version, source_fingerprint, allocations, non_cost_amount, non_cost_reason}`。`allocations[]` 每个 canonical OA 单元恰好一项，只接受 `{unit_id, amount}`；不得提交流水来源字段或同一 OA 单元的多格金额。
- 记 `C=sum(allocations.amount)`、`X=non_cost_amount`、`N=关系净支出`。未使用“不计入成本金额”时 `X=0`、原因必须为空且 `C=N`；使用时 `0<X<=N`、原因必填且 `C+X=N`。金额必须为非负、有限、最多两位小数，OA 单元集合必须完整且无重复。
- 保存前在同一事务内重新读取并锁定当前关系，校验关系仍 active、OA 已完成、事实指纹与 `expected_version` 未变化；成功同时写 `app.cost_statistics_manual_allocations` 和 `audit.events`，返回新 version。非法 payload 返回 `400`，无写权限返回 `403`，关系/版本/事实变化返回 `409`，不得部分写入、自动比例分配或沿用 stale 值。

`GET /api/cost-statistics/export-preview` 与 `GET /api/cost-statistics/export`

- 接受 `time|bank_tag|project|expense_type|bank_account`。两个流水 view 导出真实方向、标签、账户并使用净支出汇总；三个项目成本 view 复用成本事件、银行账户归属与筛选口径。preview 最多 8 行，download 受 `COST_STATISTICS_EXPORT_ROW_LIMIT` 保护。
- 导出不入队、不等待 worker，也不读取旧 Cost 投影。

`GET|PUT /api/cost-statistics/no-oa-rules`

- 控制三个成本 view 的无 OA 例外。默认 `projects=[]`；每项包含稳定 `id`、非空 `display_name` 与 `tag_codes`。
- GET 候选仅来自当前全历史实际无 active OA 关系的支出流水标签。PUT 由服务端校验项目 ID/名称、候选范围与 tag→project 全局互斥；已保存但当前不可用的 code 仍可返回并由用户显式取消。
- 保存不触发 Cost read-model refresh；页面重新 GET 后从 canonical snapshot 直接应用。

旧 `/api/cost-statistics/time-tag-rules` endpoint 已删除并返回 404；旧 `cost_statistics_time_tag_selection` 不参与 runtime settings normalization 或 persistence。

## Workbench 设置 API

### 会话与直接 API 授权

`GET /api/session/me` 保留 OA identity、roles 和 permissions 作为信息字段，但 `allowed` / `can_access_app` / `can_admin_access` / `allowed_page_keys` 只由固定 `YNSYLP005` 或当次 canonical Settings ACL snapshot 派生。除 `YNSYLP005` 外，ACL 缺席、页面集合为空、payload 非法或 provider 失败均返回 denied；OA role/permission（包括 `finops:app:view`）不能 grant APP 访问。

全局 route policy 和模块自有 guard 消费同一 normalized session。账号即使保留 `finops:app:view` 或业务角色，调用未授权页面 API 仍返回 `403 permission_denied`。ACL 删除后下一次 session/API 判断立即使用新 snapshot，不从 OA identity cache 复用 APP page set。

用户名比较使用 casefold key，对外保留 OA `sys_user.user_name` canonical spelling。等值重复、空值/控制字符、空/未知/重复 page keys 或 protected-admin 输入在 OA role 写入前返回 `400`。

`GET /api/workbench/settings`

返回关联台和设置页共享的平台设置 payload。响应可包含 `bank_transaction_tags`，用于前端展示当前银行明细标签事实和配置待找发票、流水规则批量处理、免 OA legacy、往来款等下游规则候选。

`POST /api/workbench/settings`

- 普通 GET response 和 POST request/response 都不得包含 `access_control`、`allowed_usernames`、`readonly_export_usernames`、`full_access_usernames`、`admin_usernames`、`access_control_version`。POST 出现任一历史 ACL key 返回 `400 access_control_write_forbidden`，不静默忽略。
保存项目范围、银行账户映射、OA 导入/留存、列布局、待找发票规则等普通设置项。该接口不写 ACL，也不是银行明细自动标签规则写入口。

- 请求体不得包含 `bank_transaction_tags`。只要出现该字段，后端返回 `400 bank_transaction_tags_write_forbidden`，不得部分保存其它设置。
- `AppSettingsService.update_settings(...)` 不暴露 `bank_transaction_tags` 写参数；银行明细自动标签规则只能通过银行明细自动标签 API 或复用该 application service 的恢复工具保存。
- 前端 settings/workbench API mapper 不得把 GET 得到的 `bank_transaction_tags` 原样回传到该接口，避免把规则内部元数据洗成只剩 label/path/status 的展示字典。
- 银行明细标签定义、自动匹配规则、外部往来 `turnover_action_type` / `turnover_role` 等元数据只能通过 `/api/bank-details/auto-tag-rules`、`/api/bank-details/auto-tag-rules/file-replacement` 或相关银行明细规则 service 保存。
- 待找发票、流水规则批量处理、免 OA legacy、往来款标签选择等下游规则只能引用当前 active 银行明细标签 code；保存这些下游规则不得递增 `bank_transaction_tags.version`。

### Settings access-control 专用 API

- `GET /api/workbench/settings/access-control` 仅 `can_admin_access=true` 可用，返回 `{version, administrator, accounts}`；`administrator` 固定为 `{username: "YNSYLP005", display_name, protected: true}`，普通 account 返回 `username/display_name/oa_status/page_keys`。
- `GET /api/workbench/settings/access-control/users?q=...&limit=...` 仅管理员可用，从 OA `sys_user` 有界搜索账号与姓名。
- `PUT /api/workbench/settings/access-control` 仅接受 `{expected_version, accounts}`。`accounts[]` 只有 `username` 与非空 `page_keys`；页面 key 必须来自可分配 registry。删除条目表示 denied，不接受 protected admin、重复账户、body actor 或额外字段。actor 只来自当前后端 session，request ID 只来自受信 HTTP adapter。
- stale `expected_version` 返回 `409 access_control_version_conflict` 和 `current_version`。semantic no-op 返回 `200 changed=false` 且零 PostgreSQL/audit/OA I/O。
- 真实变化先把目标 membership 投影到 `finops_app_user` / `finops_admin` 两个专用 OA 角色，再在 PostgreSQL ACL critical section 内以 CAS 同事务提交 canonical ACL 和 durable audit；audit 记录 session actor、version、变更账号摘要和 request ID，不记 token 或完整 ACL payload。
- OA 未配置、超时或专用 role/menu exact-set 验证失败返回 `502 oa_role_sync_failed`，且不写 PostgreSQL/audit。OA 目标成功后 PG 失败会补偿到旧 membership；补偿或 commit outcome 无法确认返回 `503 access_control_sync_inconsistent`，普通持久化失败返回 `503 access_control_persistence_failed`。
- `finops:app:view` 只是 OA menu selector。APP evaluator 不读 OA role/permission/env authority；部署前 migration/preflight 负责旧角色 cutover，runtime API 只验证严格投影目标并同步两个专用角色成员。

### OA 草稿预填专用 API

- `GET /api/workbench/settings/oa-draft-prefill/etc` 与 `GET /api/workbench/settings/oa-draft-prefill/input-invoice-usage` 对已授权 APP 账号可读，返回 `{family, version, configuration, dynamic_fields, options, can_save}`；`can_save` 只对 admin 为 true。
- `PUT` 同路径仅 admin 可用，只接受 `{expected_version, configuration}`；`expected_version` 必须为正整数，`configuration` 必须提交当前合同的完整且精确字段集合，缺失或未知字段返回 400。stale version 返回 `409 oa_draft_prefill_version_conflict`；semantic no-op 返回 200 且不推进 version/audit。
- 两个 family 在 `app.app_settings` 中独立 CAS 保存；ETC/反提 OA 在 prepare/create batch 时保存配置快照，锁外 OA I/O 不重读配置。申请人、当天日期、批次金额、反提唯一销方等运行时值不写死在配置中。
- 新 OA 草稿的可见申请事由不得包含 ETC Batch ID、Business Batch ID 或 input-invoice reverse batch ID；这些关联键只写结构化 payload。历史 OA 文本 ID 解析只作为旧数据只读兼容保留。

## 日常报销批量账务管理 API

`GET /api/batch-accounting?bank_year=YYYY&bucket=unsubmitted|submitted`

可选参数：

- `page/page_size` 同时作用于银行和 OA 列表。
- `bank_page/bank_page_size`、`oa_page/oa_page_size` 分别作用于银行列表和 OA 列表。
- `oa_search` 在 canonical OA 查询中匹配申请人、项目、金额和事由。
- 页码和页大小必须为正数，页大小上限 200；`oa_search` 最长 200 字符。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `summary.unsubmitted_count` | 当前银行年份下未提交候选银行流水数量。 |
| `summary.submitted_count` | 当前银行年份下已提交批量账务关系数量。 |
| `summary.bank_year` | 后端实际使用的银行流水年份；OA 候选不再按年份过滤。 |
| `bank_rows` | 当前 bucket 的服务端分页银行流水列表。 |
| `bank_rows[].tag_*` | 当前 canonical effective tag 的 code/label/主子标签/source；页面不得自行推断。 |
| `oa_rows` | `unsubmitted` bucket 的可选 OA 日常报销单据列表；候选必须没有关联银行流水，只有发票关系或无流水候选关系时仍可进入右侧 OA 栏。 |
| `relations_by_bank_row_id` | `submitted` bucket 中按银行流水 ID 索引的 active batch relation 及 canonical OA/发票成员详情。 |
| `pagination` | 银行分页；`unsubmitted` 同时包含 OA 分页。 |
| `tag_selection_version` | 本次未提交候选使用的标签规则版本；submit 必须回传。 |

该响应不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`source_versions`、`refresh_enqueued`、refresh targets 或 operation barrier targets。loading、empty 和 error 由一次普通页面请求的真实结果决定。

列表由页面专属 query repository 在一个显式 `REPEATABLE READ / READ ONLY` PostgreSQL snapshot 内读取 canonical facts：

- `unsubmitted` 读取指定年份、对方户名为“批量账务集中处理”、支出的 `app.bank_transactions`，复用银行明细 current effective-category classifier，并只保留规则已选且没有 active relation 的流水；无标签/待分类/待确认/未选标签不进入。OA 读取已完成日常报销 `app.oa_applications`，不按年份过滤，且没有包含 canonical 银行成员的 active relation。
- 附件发票只按当前 OA page IDs 查询 `app.invoices.source_links` / `app.oa_attachments`。
- `submitted` 只读取 `app.workbench_pair_relations` 中 `status='active' and relation_mode='batch_accounting'` 且包含指定年份 canonical 银行成员的关系，再一次批量读取其 canonical OA/发票成员。
- submitted relation 的成员唯一事实源是对齐、去重的 `row_ids + row_types`；API 不读取或返回 `special_metadata.bank_row_id`、`oa_row_ids`、`invoice_row_ids`、旧 `year` alias，也不透传 raw relation metadata。
- rows、summary、counts 和 pagination 使用同一 snapshot；固定查询次数、服务端分页，禁止 Workbench payload、12 月循环、逐 row relation lookup 和全量附件扫描。

成功或结构化错误响应可带 `Server-Timing` 头，记录 canonical snapshot、payload assembly 和 serialization；该头不属于业务 JSON。

`POST /api/batch-accounting/submit`

`POST /api/batch-accounting/{relation_id}/withdraw`

`GET /api/batch-accounting/tag-rules`

返回实际批量账务业务流水中出现的 `active_tags`、完整 active `selected_tag_codes`、`version` 和 `can_save`；暂时未出现的已选 stable code 继续保留，保存其它选项时不得被隐式删除。读取权限可查看；read-export 的 `can_save=false`。

`PUT /api/batch-accounting/tag-rules`

请求为完整 `selected_tag_codes[] + expected_version`。仅 full/admin 可写；未知/非 active code 返回 400，stale version 返回 409，持久化失败返回 503，semantic no-op 返回 200 且 version 不变。保存后页面只重新 GET 当前列表一次。

写操作通过同一页面 query repository 的窄 snapshot 读取 `bank_row_id + oa_row_ids` 及所选 OA 附件发票，并重新校验 current effective tag、`expected_tag_selection_version` 和 selected status，再由 canonical `WorkbenchRelationCommandService` 校验 active relation/version/idempotency/owner 状态并持久化 relation/history/audit。query repository 或 command service 缺失返回 `503 batch_accounting_canonical_query_unavailable` / `503 batch_accounting_relation_command_unavailable`；canonical conflict/version conflict 返回 409。

成功响应返回业务结果和信息性 `affected_months` / `affected_scope_keys`，不返回 freshness 或 operation barrier targets。写成功后当前页面恰好重新调用一次普通 GET；不轮询、不等待 read model、不触发跨页面刷新。后置 GET 失败不能回滚或改写已成功 command。

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

成功响应只返回新的规则 payload 和权限。普通规则保存不投递页面 read-model refresh，不返回 `read_model_status`、lifecycle、scope、job 或 barrier target；待找发票及其它 direct-canonical 页面在下一次普通 GET 中读取最新规则和 canonical facts。

## App Health 全局状态 API

`GET /api/app-health` 保留既有字段，并新增 `app_status` 作为 Global Runtime Status Plane 的用户可见投影。前端通过有界 polling/focus refresh 重读该 snapshot；旧 `/api/app-health/stream` 已删除并返回 `404`。

`app_status` 字段：

| 字段 | 说明 |
| --- | --- |
| `version` | app status contract 版本，当前为 `1`。 |
| `generated_at` | 后端生成时间。 |
| `overall.level` | `ok`、`busy` 或 `blocked`。 |
| `overall.color` | `green`、`yellow` 或 `red`，供全局 icon 使用。 |
| `overall.reason` | 全局状态原因。 |
| `overall.blocks_mutations` | 当前全局状态是否应阻断写入；该字段由 `overall.write_safety.blocks_mutations` 派生，不能由普通 read model freshness 失败直接推导。 |
| `overall.write_safety` | 写操作安全闸门，至少包含 `status`、`reason`、`blocks_mutations` 和 `blockers`。只有 session/auth、runtime/DB、关键依赖或目标写模型不可用等写安全 blocker 才应进入 `blockers`。 |
| `domains[]` | 所有页面数据域状态。 |
| `background_tasks[]` | 用户可见后台任务进度投影。 |
| `alerts[]` | 当前 active 运行告警摘要。 |

`domains[*]` 至少包含 `key`、`label`、`route`、`level`、`status`、`reason`、`details`、`read_models`、`read_model_scopes`、`historical_read_model_scopes`、`workers`、`job_ids` 和 `updated_at`。`status` 必须来自后端规则集：`ready`、`fresh`、`loading`、`pending`、`processing`、`refreshing`、`stale`、`missing`、`schema_mismatch`、`source_mismatch`、`failed` 或 `unavailable`。页面切换不能改变这些字段；只有后端 runtime facts 变化才改变全局状态。

`overall.level="blocked"` 表示全局运行状态红色，不等价于所有写操作都必须禁用。页面和 mutation hook 必须使用 `overall.write_safety.blocks_mutations` / `overall.blocks_mutations` 作为全局写闸门，并继续在具体写 API 内执行权限、审计、幂等、version conflict 和 operation-level read/write precondition。read model failed/unavailable 仍要让对应 domain blocked/red，避免假同步；但不应让无关页面按钮全局 disable。

read model readiness details 可以放入 `domains[*].details`，用于 hover 面板展示 schema/source/readiness 错误、missing readiness 或 dependency 缺失原因。空业务结果不等于 missing；只有 readiness 记录缺失、schema/source mismatch、dirty scope/outbox/worker/dependency 事实才改变全局状态。

`domains[*].read_model_scopes[]` 是状态平面的 scope 诊断，至少包含 `read_model_key`、`scope_type`、`scope_key`、`status`、`last_error` 和 `updated_at`。该字段来自 `read_model.app_status_readiness` 和 `job.read_model_dirty_scopes` 的归一化事实，不能由前端根据当前路由推断。成本统计必须使用该字段区分 `active:all` / `all:all` 父 scope 与 `active:YYYY-MM` / `all:YYYY-MM` 月份 shard：父 scope failed/unavailable 才阻断成本统计主体验；月份 shard failed/unavailable 只把域级状态推导为 busy，并在面板里暴露失败 scope 与 last error。父 scope 等待缺失或 stale 月份 shard 时应记录为 `refreshing`，表示 durable queue 正在收敛，不等同于 `failed`。

`domains[*].historical_read_model_scopes[]` 只用于诊断，不参与 `level/status/reason/details` 的 current-effective 判定。它至少包含 `read_model_key`、`scope_type`、`scope_key`、`status`、`last_error`、`updated_at`、`current_effective` 和 `history_reason`。当前用于暴露已被 scope contract 废弃的成本统计 legacy scope，例如 `all` 和裸 `YYYY-MM`；这些历史失败不能把已有 canonical fresh scope 重新拖成 busy/blocked，也不能被当作 fresh 证明。

outbox failures 只有在没有后续同 scope `done` 事件、且没有后续同 scope fresh readiness 证明时，才作为当前 blocker 参与 App Status。被后续真实后端完成事实覆盖的 `failed/dead_lettered/publish_failed` 事件属于历史诊断和后续 repair/审计对象，不应污染用户当前页面同步状态。

`background_tasks[*]` 至少包含 `job_id`、`type`、`status`、`label`、`short_label`、`message`、`phase`、`current`、`total`、`percent`、`affected_domains`、`affected_scopes`、`affected_months`、`route`、`attention` 和 `updated_at`。没有真实百分比的 worker/read model refresh 不得伪造 percent，可返回 `null`。`file_import` 等泛化类型必须优先使用 payload 中的 `affected_domains`，否则按 source/import type 映射到单一 import domain，不能默认影响所有导入页。

前端必须对 `overall.level/color/reason`、domain `key/level/status/reason`、task `job_id/status` 做 fail-closed 校验。关键字段缺失或非法时，不能把 payload 默认解释为 `ok/green/ready`。

## Bank Transaction Paired Policy / 流水规则批量处理 API

状态：close。当前生产前端和公开 API 使用 `bank-flow-rule-batches`；HTTP route、application service、页面专属 PostgreSQL canonical query repository、relation command/delta writer 和 `app_settings.bank_flow_rule_batch_tag_rules` 使用 `bank_flow_rule_batch`。未提交列表由同一只读 snapshot 的银行流水、有效分类、paired policy 和 active relation 实时推导；批次/事件表只提供正式状态与历史。API 不读取页面 read model 或 persisted draft，不返回 freshness/status/version，不 enqueue 或 polling。迁移 `0082`、`0083`、`0111` 仅保留既有数据迁移语义；运行时不把 no-OA 物理表、settings family 或旧 `selected_tag_codes` 作为 fallback。

`GET /api/bank-flow-rule-batches/tag-rules`

返回流水规则批量处理右侧抽屉所需的标签和 OA/发票闭环要求。该接口只读取银行明细 active 标签作为左侧事实，不创建或修改银行标签。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 本模块规则版本，用于保存时乐观锁。 |
| `bank_auto_tag_rules_version` | 当前银行明细自动标签规则版本；前端可用它判断左侧标签事实是否变化。 |
| `active_tags` | 银行明细 active 标签，只读展示 `收支类型 / 流水主标签 / 流水子标签`。 |
| `rules` | 当前可用标签的闭环要求列表。每行包含 `tag_code`、`requires_oa`、`requires_invoice`。 |
| `requirements_by_tag_code` | `rules` 的 code map 形式。 |
| `permissions` | 当前用户读取、保存、提交和撤回权限。 |

`active_tags[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 银行明细标签稳定身份。 |
| `direction` | `income`、`expense` 或 `all`。 |
| `primary_label` | 流水主标签。 |
| `sub_label` | 流水子标签；为空时前端可显示主标签。 |
| `status` | 当前只返回 `active`。 |

`rules[*].requires_oa` / `requires_invoice` 表示该标签业务闭环所需的单据类型。未提交批次只接纳 active 且两者都为 `false` 的标签；任一项为 `true`、规则缺失或标签归档时，该标签流水完全退出本页面未提交区。新 relation 创建时把当时规则冻结到 `special_metadata`；已提交/历史读取冻结事实，不回查当前规则。active relation 仍决定跨页面 linked ownership。

`PUT /api/bank-flow-rule-batches/tag-rules`

请求示例：

```json
{
  "expected_version": 3,
  "rules": [
    { "tag_code": "bank_fee", "requires_oa": false, "requires_invoice": false },
    { "tag_code": "project_payment", "requires_oa": true, "requires_invoice": true }
  ]
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 bank_flow_rule_batch_tag_rules_version_conflict`。
- 请求和 service 边界都不能包含 `selected_tag_codes`；旧字段不得作为新规则事实写入。
- 只能提交当前 `active_tags` 中存在且可用的标签 code；未知、停用、重复 code 返回业务错误。
- 语义变化后返回与 GET 相同结构，version +1，写一次审计动作 `bank_flow_rule_batch_tag_rules_updated`；不能递增 `bank_transaction_tags.version`。
- 后端比较保存前后未提交资格集合。只有资格实际变化的 tag code 才通过单条集合查询解析信息性受影响月份，并在同一 PostgreSQL 事务中完成 settings 乐观锁写入与审计；普通保存不写 dirty scope/outbox。禁止 `all` fallback。OA-only 改为 invoice-only 等资格不变的语义更新同样只保存 canonical 规则。
- 响应额外返回 `eligibility_changed`、`eligibility_changed_tag_codes`、`affected_months` 和信息性的 `affected_scope_keys`；不返回 `read_model_scope_keys`、freshness/operation-barrier targets 或 `refresh_enqueued`。当前页面随后执行一次正常 GET。
- 提交与当前有效规则相同的 payload 是 no-op：version 不变，不写 settings/audit。
- 保存规则不得读取或改写 existing Workbench/turnover relation；existing metadata 保持历史快照，关联台按各 relation 自己的快照分区。
- 保存 API 在 durable transaction 提交后立即返回；前端清空旧选择并重跑当前页面的正常列表 GET，不启动 operation barrier。
- HTTP 输出边界只返回 `bank_flow_rule_batch_*` 错误码。共享 bank-batch core 必须根据显式 bank-flow relation mode 直接产生正式错误码；route 不保留 legacy translation map 或 no-OA fallback。

`GET /api/bank-flow-rule-batches`

查询流水规则批量处理列表。常用查询参数：

| 参数 | 说明 |
| --- | --- |
| `month` | 可选；`YYYY-MM` 表示精确月份，省略表示全部月份。 |
| `bucket` | `unsubmitted`、`submitted`、`withdrawn` 或 `all`。 |
| `account_key` | 银行账户筛选。 |
| `type` | 银行标签/批次类型筛选。 |
| `status` | `draft`、`submitted`、`withdrawn` 或 `all`。 |
| `page` / `page_size` | 分页；`page_size` 上限由后端固定。 |

响应只包含 `summary`、`batches`、`pagination`。标签规则、total、当前页 batches 和 summary aggregates 必须位于同一个显式 `REPEATABLE READ / READ ONLY` snapshot；查询数固定，服务端过滤、固定排序和分页。精确月份查询使用内部转账 ±2 天窗口；省略 `month` 时以一次集合式 canonical 查询读取全部 non-deleted 银行流水、当前分类、正式历史和 active relation，禁止前端或后端按月份循环拼接。summary 对完整 summary filter 范围聚合，并为总计和每个 category 返回 draft/submitted/withdrawn 的 batch count 与 `*_row_count`，历史 category 携带冻结 label/primary/sub label，不能由当前页推算。默认页面 `page_size=50`。未提交标签只展示当前 OA/发票双 false 的 active tags，已提交/历史只展示对应状态 count > 0 的 summary categories。空 batches 是 canonical snapshot 的真实空集；查询错误返回错误，不以 read-model stale/missing 伪装。正式关系只读取 `app.workbench_pair_relations.status='active'`，不得读取 Workbench page projection。详情 payload 可保留 `relation_case_ids` 供机器诊断，但页面只显示“已有未撤回关联”和 OA/发票数量。

`GET /api/bank-flow-rule-batches/{batch_id}`

返回一个批次的银行流水明细、分类、标签、方向统计和 events。正式 submitted/withdrawn/stale 批次直接读取持久化正式事实。列表中的 live candidate 不是 persisted draft，前端必须把列表项月份作为 `scope_month=YYYY-MM` 查询参数；后端使用列表、提交 guard 和 Audit 共用的 canonical builder 按 `batch_id + scope_month` 确定性重算详情。非法月份返回 `400 invalid_bank_flow_rule_batch_month`；候选已变化、被占用或不再存在时不得返回旧 draft。

`POST /api/bank-flow-rule-batches/submit-selection`

提交当前页面选中的银行流水，生成一个流水规则批量处理批次并通过 relation command service 创建 active relation。

请求示例：

```json
{
  "transaction_ids": ["bank-row-001", "bank-row-002", "bank-row-003", "bank-row-004"],
  "scope_month": "2026-07",
  "note": ""
}
```

提交规则：

- `transaction_ids` 必填、不能为空、不能重复。
- `scope_month` 必填且必须为 `YYYY-MM`；禁止回退到当前月份、`all` 或进程启动时快照。
- 实现初期要求所有流水来自同一月份、同一银行账户、同一当前有效银行标签；后续放宽必须更新本 API 和模块状态机。
- 提交前必须在同一个 canonical source 中重查银行流水、当前有效分类、标签规则、OA/发票 requirement 和 active relation 占用；最终 `SERIALIZABLE` 写事务重新锁定并比较 selected-row proof 与 rule proof。目标行已被任一 active relation 占用时返回 `409 bank_flow_rule_batch_selection_occupied` 和结构化冲突信息；不能把领域冲突映射为 500。
- active relation rows 必须来自 canonical PostgreSQL source bundle；提交与页面查询不得使用 Workbench relation read model 或启动时全量 relation snapshot 作为占用事实源。
- 成功后写入 `relation_mode=bank_flow_rule_batch`，并在 relation `special_metadata` 写入 `source_batch_id`、`flow_rule_tag_code`、`flow_rule_version`、`requires_oa`、`requires_invoice`、`source_row_count`、`collapsed_bank_rows`。
- 关联台按 active 正式关系判断 ownership，再按该批次 relation 冻结的 OA/发票 requirement 判断 paired/unpaired；`source_row_count > 3` 时默认折叠。
- Workbench 折叠摘要必须输出 `source_kind=bank_flow_rule_batch_summary`、summary id prefix `bank_flow_rule_summary:`、`invoice_relation.code=bank_flow_rule_batch` 和 `流水规则` display tag；不得输出 `no_oa_bank_batch_summary` 或 `免OA` tag 作为 bank-flow 摘要 I/O。
- 成功响应返回 batch/relation receipt、`case_id` 和 `affected_months`；不返回 read-model/freshness/operation-barrier envelope。当前页面随后执行一次正常 GET。

## 免 OA 流水批量处理 API

状态：legacy。新通用功能应实现 `流水规则批量处理 API`，不要继续扩展本节为新的通用规则合同。

`GET /api/no-oa-bank-batches/tag-selection`

返回免 OA 页面的全局标签准入范围。该接口只读取银行明细自动标签规则中的可用标签作为候选，不创建独立标签事实源。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 免 OA 标签准入配置版本，用于保存时乐观锁。 |
| `bank_auto_tag_rules_version` | 当前银行明细自动标签规则版本；前端可用它判断标签事实源是否已变化。 |
| `selected_tag_codes` | 兼容字段：当前仍可用、且 `OA/发票` 都不需要的标签 code 列表。首次为空数组；新调用方应以 `rules` 为准。 |
| `inactive_selected_tag_codes` | 历史配置中已停用或不可用的标签 code；不参与候选生成，保存后会被清理。 |
| `active_tags` | 银行明细自动标签规则中的可用标签，供抽屉以只读 grid 展示 `收支类型 / 流水主标签 / 流水子标签`。 |
| `rules` | 当前可用标签的闭环要求列表。每行包含 `tag_code`、`requires_oa`、`requires_invoice`；字段影响未来 relation 的冻结 requirement，不追溯改写 existing relation。 |
| `requirements_by_tag_code` | `rules` 的 code map 形式，便于后端服务和前端 draft 合并。 |

`active_tags[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 银行明细标签稳定身份。 |
| `label` | 标签显示名称。 |
| `path` | 标签路径，可用于审计或调试。 |
| `status` | 当前只返回 `active`。 |
| `direction` | 银行自动标签规则收支方向；前端显示为收入、支出或全部。 |
| `output_primary_label` / `output_sub_label` | 免 OA 页面展示的主/子标签。`output_sub_label` 可为空，前端显示为“主标签本身”。 |

免 OA 标签准入不返回第三层流水分类字段。外部往来流水的“个人往来 / 公司往来 / 银行往来 / 业务往来”只属于银行明细候选确认或人工补分类时选择的流水级分类，不作为免 OA 自动规则保存或展示。

`PUT /api/no-oa-bank-batches/tag-selection`

请求示例：

```json
{
  "expected_version": 3,
  "rules": [
    { "tag_code": "fee", "requires_oa": false, "requires_invoice": false },
    { "tag_code": "salary", "requires_oa": true, "requires_invoice": false }
  ],
  "selected_tag_codes": ["fee"]
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 no_oa_bank_batch_tag_selection_version_conflict`。
- `rules` 是当前主合同；`selected_tag_codes` 只用于旧调用方兼容。旧调用方只传 `selected_tag_codes` 时，后端解释为这些标签 `requires_oa=false, requires_invoice=false`。
- `rules[*].requires_oa=true` / `requires_invoice=true` 表示该标签业务闭环要求 OA / 发票；关联台按 relation 创建时冻结的值判定 paired/unpaired。
- 只有 `requires_oa=false` 且 `requires_invoice=false` 的标签会派生到 `selected_tag_codes`，并进入免 OA 未提交候选。新增银行自动标签若没有保存过规则，默认 `requires_oa=true, requires_invoice=true`，避免新增标签自动放行到免 OA 候选。
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

接口在请求内按有效月份（否则 `all`）刷新 canonical no-OA 候选，再从 `app.no_oa_bank_batches/events` 读取列表、汇总和分页结果。响应不包含 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued`、source versions 或 operation barrier target；GET 不写 dirty scope/outbox，不读取历史 `read_model.no_oa_bank_batch_rows`。不在当前 canonical snapshot 中的旧 draft/conflict 候选必须清理，已提交/撤回历史按业务状态保留。

`POST /api/workbench/actions/confirm-link`

关联台确认两条银行流水时，如果选中流水当前分类全部为 `internal_transfer`，后端必须委托免 OA 批次统一提交入口：刷新免 OA 候选，优先复用完全匹配这组 `row_ids` 的 submitted no-OA internal transfer batch；若不存在 submitted fact，再找到完全匹配的内部往来 draft batch 并按批次提交。成功响应仍保持关联台 `confirm_link` 兼容结构，但最终事实必须是一个 `status=submitted` 的内部往来免 OA 批次，以及一条 `relation_mode=no_oa_bank_batch` 的 Workbench active pair relation；关联台已配对区消费该 relation，免 OA 已提交区域消费同一批次。免 OA 页面先提交或关联台先提交同一组流水都必须返回同一个 `case_id`，不得创建第二条 active relation。

存量 active `manual_confirmed` 关系只有在 `internal_transfer` 已纳入免 OA 标签准入，且两行、全银行流水、同金额、不同账户、收支成对、有效分类均为 `internal_transfer` 时，刷新 no-OA 批次时才迁移为 submitted no-OA internal transfer batch；其他普通 `manual_confirmed` 关系保持关联台语义，不由 no-OA 模块接管。Workbench active pair relation 对 row 是独占事实，不同 active case 不允许复用同一 row。

如果选中银行流水中只有部分为 `internal_transfer`，接口返回 `400 no_oa_bank_batch_selection_internal_transfer_conflict`，不得静默写入 `manual_confirmed`。非内部往来的银行-only 平衡确认保持原有关联台普通确认语义，可写入 `relation_mode=manual_confirmed`。

### Workbench OA/发票异常 API

`GET /api/workbench/groups` 使用 month/zone/search/filter/sort/opaque-cursor 合同，并支持可选 `exception_bucket=unpaired|paired`。bucket 必须等于 zone，返回该展示区内携带当前异常的关系组。异常 bucket 可再传 `exception_view=amount|document_only`；金额视图可传七分类白名单 `exception_code`，其它 view 传 code 返回参数错误。过滤发生在 exact total/row counts 与 keyset 分页之前，不读 page generation 或 legacy WEX bucket。

异常 bucket 响应 additive 返回：

```json
{
  "selected_exception_code": "oa_bank_equal_invoice_less",
  "exception_counts": {
    "total": 8,
    "amount_total": 7,
    "document_only": 1,
    "by_code": {
      "oa_bank_equal_invoice_more": 1,
      "oa_bank_equal_invoice_less": 1,
      "oa_invoice_equal_bank_more": 1,
      "oa_invoice_equal_bank_less": 1,
      "bank_invoice_equal_oa_less": 1,
      "bank_invoice_equal_oa_more": 1,
      "all_amounts_different": 1
    }
  }
}
```

`exception_counts` 基于当前 bucket 和其它 search/filter 条件按唯一关系计算，但不受当前 view/code 自身过滤影响；`page.total` 是当前筛选列表总数。金额与资料异常并存的关系只进入它的唯一金额分类，资料异常保留在同一 bundle；`document_only` 只包含没有金额分类但至少有一种附件异常的关系。多个资料 item 不增加关系计数。金额视图未显式传 code 时，服务端按固定七分类顺序选择首个非零分类并返回 `selected_exception_code`；这一自动结果不属于调用方 query，但会封存在 opaque cursor 内，后续请求继续省略 code 并由服务端强制复用该分类。显式点击分类后才把 code 写入新查询和新 cursor hash。

关系组可携带 additive `workbench_anomaly`：`{code="workbench_anomaly",fingerprint,review_decision="pending|accept_paired|keep_unpaired",review_note,reviewed_by_account,reviewed_by_name,reviewed_at,items[]}`。`reviewed_by_account` 是审阅时已认证 OA 账户快照，`reviewed_by_name` 是同一时点的可选姓名快照；内部 actor id 不属于用户可见 API。用户可见 item code 支持七种互斥三栏金额分类和三种附件状态，并返回三栏 totals、`amount_delta`、来源 IDs 及 `display_scope/display_pane/display_row_id`。`display_scope=group` 使用 `display_pane=group` 且不伪造 row id。付款方向 `bank_total` 是同一正式关系内支出减收入/退款的净额。三栏缺失、金额无效、方向未知/冲突或三栏总额完全一致时不生成金额分类；费用子项局部差异只能辅助定位已成立的七分类，不额外生成第八种金额异常。缺失 bundle 表示当前关系无异常。

OA row 的 additive `expense_items[]` 同步返回 `attachment_file_count`。前端只把异常 item 绑定到一个可证明的比较单元：`display_scope=row|expense_item` 时落到指定 pane/row 或 OA 子付款项；无法唯一证明、目标当前不可见或 `display_scope=group` 时落在既有关联组边界，不得塞到任意一张发票。附件未解析/缺失使用既有三栏状态操作区，不创建可选择的 synthetic canonical row，也不能把展示占位提交到 relation mutation。

`POST /api/workbench/exceptions/review` 接受 `{month,zone,group_id,detail_key?,fingerprint,decision,note?}`；`detail_key` 在列表返回时原样回传，用于同一 `group_id` 的精确详情定位。`decision` 只允许 `accept_paired|keep_unpaired`。后端重取当前 canonical detail，并自行推导 evidence fingerprints 与 detected codes；客户端提交的旧人工分类、逐项 fingerprints 或 actor 不参与决定。后端必须同时固化 session actor id、OA 账户和姓名快照；账户缺失时写入失败，不按 actor id 做页面运行时反查或兜底。权限、400/403/409、fingerprint/topology 冲突和幂等审计合同不变。成功后页面执行一次 canonical direct GET，并只读取目标异常 bucket；不修改正式关系、canonical 金额、附件或发票事实。单月关系把决定绑定到该月；跨月关系绑定全局作用域。旧人工分类与 amount-mismatch ignore/restore routes 不得恢复。

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
- 成功后写入 `relation_mode=no_oa_bank_batch`，并在 relation `special_metadata` 保留 no-OA 专属冻结要求与规则版本。该显式批次合同继续由 no-OA owner 解释，不允许通用 Workbench 读路径回查当前规则。接口返回信息性 `affected_months`，两个 target 数组为空；当前 no-OA 页面用正常 GET 收敛，关联台只在被访问时收敛自身。旧 `workbench_rebuild_queued` 字段已删除，避免把访问时 freshness 收敛误表述成写后重建。

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
| `closed_amount` | 已闭合兼容字段，固定为字符串 `0.00`；不得再累计历史 principal 或 settlement。主页面不作为页头 block 展示。 |
| `suggested_count` / `conflict_count` / `row_count` | 兼容计数字段。 |

`family_summaries[*]` 每个类别都应稳定返回：

| 字段 | 说明 |
| --- | --- |
| `family` / `label` | 类别 code 和展示名。 |
| `pending_repayment_amount` | 该类别当前待还款余额。 |
| `repaid_amount` | 该类别累计已还款发生额。 |
| `pending_collection_amount` | 该类别当前待收款余额。 |
| `collected_amount` | 该类别累计已收款发生额。 |
| `pending_amount` / `closed_amount` / `row_count` | 兼容字段；`pending_amount` 等于待还款与待收款余额合计，`closed_amount` 固定为 `0.00`。 |

`view=grouped` 响应中的 `groups[*]` 还应稳定输出 `pending_repayment_amount`、`repaid_amount`、`pending_collection_amount`、`collected_amount`、`closed_amount`、`cash_pair_linked`、`cash_pair_case_id`、`paired_unsettled` 和 `cash_closure_linked`。页面响应保留 `summary_row` 和 `flow_rows[*]`，不返回浏览器未消费的 `allocation_lots` / `lot_rows`；导出内部 grouped payload 仍保留这两组明细。`summary_row` 和 `flow_rows[*]` 应携带 `bank_account_labels`、`category_primary_label`、`category_sub_label`、`category_third_label`、`category_label_path` 和 `repayment_remark`；flow row 还应输出 `cash_pair_linked` / `cash_pair_case_id`。金额列归属以 `turnover_action_type` 归一后的 `borrow_amount` / `repayment_amount` 为准，不得仅按现金流入/流出判断。前端表头应将 `borrow_amount` 展示为“往来发生”、`repayment_amount` 展示为“结清发生”；金额 chip 使用 `borrow_direction` / `repayment_direction` 展示“收”或“支”，并按实际现金方向着色。余额为零但没有 active case 时，`pending_direction=none`，且不得输出闭环状态。

页面直接读取 canonical facts，响应不携带 `read_model_status`、source version、refresh job 或 barrier。写操作是否允许只由权限、当前 canonical relation 前置条件和业务校验决定，不得恢复 read-model polling/fallback。

外部往来款 `deterministic` 只表示系统识别到零差额计算结果，不表示已闭环，也不形成关联台关系组。外部往来闭环的共同事实源是 Workbench active pair relation；来源可以是外部往来页人工确认闭环，也可以是关联台已经把同一往来组内的银行收入/支出配成同一个零差额 case。单个 active case 只有在银行成员完整且唯一、至少一收一支、业务语义一致、现金差额和业务余额都为 `0.00` 时才输出 `cash_closure_linked=true`；active case 余额非零时输出 `cash_pair_linked=true`、`paired_unsettled=true`，并保留真实待还/待收余额。不同 active case 必须分别结算，禁止组级净额抵消。relation mode/source/provenance 只作诊断，不参与闭环资格判断。`view=grouped` 的 `summary_row` 和 `flow_rows[*]` 必须输出 `linked_oa`、`linked_invoice`、`cash_closure_linked`、`cash_closure_case_id`、`cash_closure_source`、`cash_closure_relation_id`；前端只能据此显示“已关联 OA”“已关联 发票”“收支闭环”三个正向 chip，并可据 `cash_pair_linked && !cash_closure_linked` 显示“已配对未结清”。`cash_closure_relation_id` 只用于兼容历史上显式携带 `special_metadata.turnover_relation_id` 的旧闭环，不得从 `cash_closure_case_id` 猜测；现代闭环该字段为空，撤回按 canonical case id 执行。若所选银行流水已存在 OA + 银行 active relation，确认闭环应把新增流水原子扩展进同一个 `turnover_manual_closure` case。active relation 继续决定外部往来闭环 ownership；关联台展示区由该 relation 的显式 completion contract 判定。

`POST /api/turnover-ledger/closures/confirm`

人工确认同一往来组内多笔外部往来流水闭环。请求示例：

```json
{
  "bank_row_ids": ["bank-income-001", "bank-income-002", "bank-expense-001"],
  "expected_versions": {
    "turnover_bank_row_selection:bank-income-001": "v1|2026-08-14T02:00:00+00:00|1|bank-auto-tag-rules:7|external_turnover_collection|external_turnover|collected|business"
  },
  "idempotency_key": "closure-20260605-001",
  "note": "人工确认零差额闭环"
}
```

校验规则：

- `bank_row_ids` 必须至少两条且不能重复；不再限制为正好两条。
- 页面 grouped flow row 为每条可提交流水输出 `selection_version`；正式前端必须逐条以 `turnover_bank_row_selection:<id>` 提交。缺失 token 时前端不得发 POST；旧 `turnover_bank_row:<id>` category-only key 返回 409 并要求刷新。
- 后端必须在同一写事务内按精确 IDs 一次重新读取当前 canonical 银行流水、有效分类、规则版本和往来语义，并复用页面 GET 的分类/行映射；全部流水必须属于同一往来台账组、同一往来语义、同一对方，并同时包含收入和支出。
- 收入金额与支出金额差额必须为 `0.00`；否则返回 `400 turnover_closure_amount_mismatch` 或方向/语义相关业务错误。
- 流水不得已被其他 active Turnover confirmed relation 占用。若所选流水已被 Workbench active relation 占用，只有 row types 子集为 `{oa, bank}` 的 relation 可被本次闭环合并；包含 `invoice` 或其他业务 row type 时返回 `409 turnover_closure_requires_workbench` 或 `409 turnover_relation_conflict`，并提示去关联台处理完整关系。已确认后如需补选流水，必须先撤回原闭环关系，再重新选择完整流水确认。
- `expected_versions` 进入写 UoW 的 stale precondition；版本冲突必须在写 canonical Workbench relation 前失败。
- `idempotency_key` 进入写 UoW 的幂等边界；相同 payload 重放返回第一次结果，不同 payload 返回 `409 idempotency_key_conflict`。

成功响应至少包含：

| 字段 | 说明 |
| --- | --- |
| `status` | 固定为 `confirmed`。 |
| `workbench_pair_relation` | 同一写事务内创建的 Workbench active pair relation，`relation_mode=turnover_manual_closure`，作为共同事实源。可为 bank-only，也可在合并既有 OA-bank relation 时包含 `oa` + `bank` rows；active 后完整成员进入关联台 paired。 |
| `affected_months` | 受影响月份，用于刷新外部往来和关联台 relation context。 |

确认入口仍复用 Turnover domain 校验方向、语义、对方和零差额，但该校验无副作用。成功写入只持久化 canonical Workbench relation/history，不写 `app.turnover_relations`、`app.turnover_relation_events`，响应不得返回伪造的 `turnover_relation` / `relation`。普通写入不写 `turnover_ledger`、`workbench`、`workbench_relation` 或 Cost 的 dirty/outbox；当前外部往来页面重新调用正常 GET，其他页面在访问时各自执行 freshness gate。不得在页面或 Workbench 查询层用 `turnover_relation` 重新拼 open 分组。

`POST /api/turnover-ledger/relations/{relation_id}/withdraw` 仅保留给显式存在 `app.turnover_relations` 事实的通用 relation 和历史手动闭环；现代 `/closures/confirm` 不创建这类 relation，因此不得调用该接口撤回新闭环。历史闭环对应 Workbench active relation 仍是 `turnover:{relation_id}` 的 `relation_mode=turnover_manual_closure` 且 row types 只包含 `oa` 与 `bank` 时，后端在同一写事务中撤回旧 Turnover relation，并通过 Workbench relation command service 撤回对应 active case。若 relation 已补齐发票或其他业务 row type，接口必须返回 `409 turnover_closure_withdraw_requires_workbench`，提示用户到关联台撤回完整关系。

`POST /api/turnover-ledger/closures/withdraw` 是现代外部往来闭环和关联台来源同组银行收支闭环的统一撤回入口。请求体使用 `cash_closure_case_id`（或 camelCase `cashClosureCaseId`），后端必须通过 `TurnoverLedgerWriteFacade` -> `TurnoverLedgerWorkbenchPairPort` -> `WorkbenchRelationCommandService.withdraw_relation(case_id=...)` 撤回同一个 Workbench active case，不得由外部往来页直接改 pair snapshot，也不得回退到 legacy pair service cancel。事务内必须重新读取 active relation，只允许 row types 子集为 `{oa, bank}` 且至少包含两条 bank rows；若已补齐发票或其他业务 row type，返回 `409 turnover_closure_withdraw_requires_workbench`。成功响应返回 `status=withdrawn`、`workbench_pair_relation` 和信息性 `affected_months`；不返回 freshness/barrier target，当前外部往来页面通过正常 GET 收敛。缺少 case id 返回 `400 invalid_cash_closure_case_id`；case 已变化或不存在返回结构化 precondition error。

## 银行明细自动标签规则 API

`GET /api/bank-details/accounts`

返回银行明细页左侧账户列表和总余额。后端在显式 `REPEATABLE READ READ ONLY` snapshot 中，以有界账户级 SQL直接聚合 canonical `app.bank_transactions` 和账户映射；不读取 `read_model.bank_account_balances` 或 `read_model.bank_detail_rows`，不在 Python/浏览器全量聚合。

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
| `account_key` | 前端筛选流水使用的稳定 key；与 transactions direct query 中的 `account_key` 对齐。 |
| `bank_name` / `account_last4` / `display_name` | 账户展示字段。 |
| `account_no` / `account_name` | 可选账户原始字段；完整账号只用于身份区分和必要展示，不参与前端自造 key。 |
| `latest_balance` | 该账户按交易时间排序的最新一笔非空 `balance`。 |
| `latest_balance_at` | 贡献最新余额的流水时间。 |
| `latest_balance_transaction_id` | 贡献最新余额的流水 ID，用于审计和排查余额变化。 |
| `currency` | 币种，缺省为 `CNY`。 |
| `has_balance` | 是否有可用最新余额。 |
| `transaction_count` | 当前日期范围内该账户流水数量；只影响列表徽标，不参与余额计算。 |
| `transaction_total_count` | 该账户全部流水数量。 |

日期筛选只影响 `transaction_count`，不改变 `latest_balance`、`total_balance` 或 `total_balances_by_currency`。关键字、分类筛选和自动标签规则变化不调用该接口；银行流水导入、删除、重导或原始余额字段变化在事务提交后由下一次 accounts GET 直接可见。响应不携带 read-model status/source/job/barrier。

`GET /api/bank-details/transactions`

返回银行明细流水列表。除基础流水字段、自动标签字段和关系标签外，自动标签候选确认相关字段如下：

rows、`statistics`、`category_counts`、pagination 和当前目标行关系标签来自同一个显式 `REPEATABLE READ READ ONLY` canonical snapshot。筛选、排序和分页在 PostgreSQL 完成；page 从 1 开始，page size 最大 500。正式关系只读取 `app.workbench_pair_relations status=active`，且只按当前页 legacy/canonical bank row IDs 做 bounded overlap；不得读取 Workbench raw payload、`read_model.bank_detail_rows` 或 `read_model.workbench_relation*`。响应不携带 read-model status/source/job/barrier，空 rows 即当前筛选真实空集。

| 字段 | 说明 |
| --- | --- |
| `category_resolution_status` | 分类解析状态：`auto_matched`、`needs_confirmation`、`internal_transfer`、`manual_confirmed` 或 `unmatched`。 |
| `category_rule_version` | 生成该自动标签或候选集时使用的自动标签规则版本。 |
| `manual_confirmed_category_code` | 用户从自动候选集中确认后的标签 code；未确认时为 `null`。 |
| `auto_candidate_category_codes` | 当前自动规则命中的候选标签 code 列表；只有 `needs_confirmation` 时用于页面选择。 |
| `auto_candidate_categories` | 候选标签展示对象列表，包含 `category_code`、`category_label`、`category_primary_label`、`category_sub_label`、`category_third_label`、`category_label_path`、`category_path`、`turnover_role`、`turnover_action_type`、`turnover_family`、`rule_code` 和 `reason`。 |

当 `category_resolution_status=needs_confirmation` 时，前端展示 `auto_candidate_categories` 作为候选确认项，并额外提供系统 `内部往来款` 人工覆盖项；不得回退到其它未命中的标签。选择候选调用 confirmation API，选择 `内部往来款` 调用 assignment API。确认后接口返回的行应表现为 `manual_confirmed`，`effective_*` 字段按确认标签填充；撤销后回到当前自动规则重新计算结果。外部往来规则命中但缺少第三层标签时，候选项为同一规则展开出的 `个人往来`、`公司往来`、`银行往来`、`业务往来` 四类第三层标签，`turnover_action_type` 来自规则。

当 `category_resolution_status=unmatched` 且没有 `effective_category_code` 时，前端展示 `待分类` 人工分类入口。该入口使用当前 active 自动标签并追加系统 `内部往来款`，按普通主/子标签和外部往来三层标签展示，不能调用自动候选确认接口。`effective_category_source=auto` 时，标签旁展示“撤销”；点击后打开同一人工分类菜单，保存新标签前不写数据。

列表 `bank_transaction_tags.definitions` 只返回 code/path/label/status/source 与输出/往来展示元数据；自动匹配 `rules`、account scope 和其它执行期字段不得下发。rows 以 `effective_*`、`auto_*`、candidate 和 relation 字段为展示事实，不再返回与 `effective_*` 重复的旧 `category_*`、`manual_category_*` 别名或 `auto_category_evidence`。

自动候选生成按优先级层级收敛：`内部往来款` priority `1` 先执行并命中即停止；普通规则按 priority 从小到大分桶执行。某个普通 priority 层级一旦存在命中，后端不再检查更低优先级层级；该层级命中一个标签返回 `auto_matched`，命中多个标签返回 `needs_confirmation`，候选列表只包含该层级命中的标签。

`GET /api/bank-details/transactions/export`

复用 transactions 的 canonical filter/category/relation 合同，`mode` 仅接受 `all` 或 `account`。导出不受页面 pagination 限制，但服务端最多读取 `BANK_DETAIL_EXPORT_ROW_LIMIT + 1` 行用于超限判断；超限返回结构化业务错误，不把全量 rows 先发送到浏览器。XLSX 中的 relation 字段只来自目标导出 row IDs 的 active canonical relation overlap。

`POST /api/bank-details/transactions/{transaction_id}/category-confirmation`

从当前自动规则命中的候选标签中确认一个标签。请求体：

```json
{
  "category_code": "external_payment",
  "category_third_label": "个人往来"
}
```

后端必须按当前流水和当前自动标签规则重新计算候选集，并校验请求标签存在、启用且属于当前候选集；同一 `category_code` 有多个外部往来第三层候选时，必须同时校验 `category_third_label`。不满足时返回 `400 invalid_category_confirmation_candidate`，不得接受前端伪造的非候选标签。成功后写来源为 `auto_confirmation` 的确认记录和审计记录；不创建页面 read-model dirty/outbox，当前页面随后重新 GET。

`DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`

撤销该流水当前自动候选确认。撤销后写来源为 `auto_confirmation_revoked` 的记录和审计记录，当前页面随后重新 GET。该接口只撤销候选确认，不恢复旧版“任意人工分类”能力。

`POST /api/bank-details/transactions/{transaction_id}/category-assignment`

为流水保存持久人工分类，可用于待分类、自动分类、候选确认或系统内部往来结果的人工覆盖。请求体：

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

请求标签必须是当前 active 自动标签或系统 `internal_transfer`；外部往来人工分类必须携带第三层标签和可由规则解析的动作语义。写入在同一事务中 supersede 旧 active category、revoke 旧 active confirmation，并写 `source=manual, manual_assignment=true` 的新 fact/event/audit；重复保存相同人工语义幂等。该人工 fact 在银行明细、共享 effective-category provider 和下游 canonical query 中优先于当前自动规则。成功审计记录 `selected_category_code`、`previous_resolution_status` 和 `assignment_source=manual`；有效标签变化时同事务重冻结受影响 active 普通关系 requirement，不创建页面 RM fan-out，当前页面随后重新 GET。

`DELETE /api/bank-details/transactions/{transaction_id}/category-assignment`

只清除该流水当前 `source=manual, manual_assignment=true` 的人工覆盖。成功后原 category fact 进入 `cleared`，不得创建 active `unknown` 标签；下一次 GET 重新计算当前自动规则，结果可能是 `unmatched`、`needs_confirmation`、`auto_matched` 或 `internal_transfer`。成功响应包含 `changed` 和精确 `affected_months`，不返回 freshness target 或 operation barrier；银行明细页面通过正常 GET 收敛，并写审计动作 `bank_detail_category_manual_assignment_cleared`。该接口不撤销 `auto_confirmation` 候选确认；候选确认仍调用 `/category-confirmation` 的 DELETE。

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
- 停用已被待找发票规则、流水规则批量处理或免 OA legacy 批量标签选择引用的标签时，后端同步移除或标记这些引用、写入审计，并在保存成功后触发相关 read model 刷新。
- 成功后返回与 GET 相同结构，并写审计动作 `bank_auto_tag_rules_updated`。
- 成功保存提交 settings CAS/version/audit，不创建银行明细页面 dirty/outbox，也不在 API 请求热路径同步扫描全量银行流水或其它页面；当前页面随后重新 GET。

重新应用当前规则：

`POST /api/bank-details/auto-tag-rules/reapply`

- 需要银行明细写权限。
- 不读取请求体，不修改 `bank_transaction_tags`，不递增 `version`。
- 使用服务器当前已保存的自动标签规则，不修改设置、不入队 read model。
- 成功返回 `200`，响应主体与 GET 规则结构一致，不包含 read-model status、scope、job、freshness target 或 operation barrier。
- 成功后写审计动作 `bank_auto_tag_rules_reapply_requested`，metadata 包含当前规则 `version` 和 `reason=canonical_query_reapplied`。
- 当前页面收到成功后重新 GET transactions；同优先级规则命中多个标签时仍进入待确认，不强制选择任一标签。

文件规则替换：

`POST /api/bank-details/auto-tag-rules/file-replacement`

- 需要银行明细写权限。
- 请求体为空时使用仓库内 `fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json` 作为生产基准规则；也可提交同结构 JSON 或 `{ "source": ... }`。
- 后端用文件内普通规则替换当前普通自动标签规则，保留 `内部往来款` 系统规则；能按主标签+子标签复用的标签沿用原 code，无法复用的生成新 code，不在文件内的旧普通规则归档。
- 文件内普通规则全部写入 priority `2`，并用 `sort_order` 保留文件顺序；`内部往来款` 仍是固定系统规则 priority `1`。
- 被归档标签若被待找发票规则、流水规则批量处理或免 OA legacy 批量标签选择引用，后端同步移除或标记引用并审计。
- 成功后提交 settings CAS/version/audit；不创建银行明细页面 read-model refresh，当前页面重新 GET。

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

工作台 DTO 是 direct canonical 页面合同，保留稳定的 summary、group、relation、exception 和 opaque cursor；不返回 page read-model status/version、generation、source-version freshness 或 refresh job。响应列表只包含 compact summary rows，raw payload、OCR、附件全文和完整 detail 只能经惰性详情端点读取。

`GET /api/workbench?month=...`

- 该接口是 Workbench 唯一首屏读入口，在一个短生命 PostgreSQL `REPEATABLE READ READ ONLY` 快照内返回 `month`、`scope_key`、`summary`、`statistics`、`paired` 和 `unpaired`。`statistics` 直接基于 canonical OA、流水和统一发票事实计算，其中发票字段固定为 `invoice_total_count`、`input_invoice_count`、`output_invoice_count`、`manual_import_invoice_count`、`oa_parse_created_invoice_count`；不返回 Workbench 可见数、ETC 隐藏数/额外数/折叠批次数或宽泛的 OA 附件来源数。summary、精确计数和两区首页 keys 必须来自同一 candidate spine/snapshot，不得串行重建三次全 scope 事实。
- 每区 shape 固定为 `groups,total,row_counts,page_size,has_more,next_cursor`。首屏 `page_size=10`，候选 SQL 返回 `page_size+1` keys 判定 `has_more`，再 set-based hydration 只完整装配当前页的 groups。精确 total 与跨未加载页搜索合同不变。
- compact summary group 保留唯一的组级 `amount_check`；列表行不重复传输同一 `relation_amount_check`、对象身份仲裁字段、来源 identity aliases 或 detail-only `special_metadata`。前端可把组级金额判断继承到可见行用于 chip，完整行级诊断只由 detail 端点返回。
- `GET /api/workbench/groups` 使用 `month,zone,search,filters,sort,cursor,page_size,exception_bucket,exception_view,exception_code` 的明确白名单合同。`exception_bucket` 必须与 zone 相同；`exception_view` 必须与 bucket 同时使用，`exception_code` 只允许用于金额视图。`cursor` 绑定 scope/zone/search/filter/sort/异常筛选和上一行完整稳定排序 tuple，是不透明的 keyset 位置，不是读快照版本或写 CAS。不提供 `page/OFFSET` fallback；服务端自动选中的金额 code 封存在 cursor 中，不得由客户端在同一次分页链中回填，也不得在续页时重新自动选择。
- `GET /api/workbench/filter-options` 提供 paired/unpaired 三栏完整表头候选。必填 `month`、`zone`、`pane`、`facet`；`facet=column` 时必填白名单 `column`，`facet=time_year` 时不传 column。可选 `option_search` 最长 100 字符，`page_size` 默认 100、最大 200，使用 opaque `cursor`；响应固定为 `options[{value,label,missing,group?}],page_size,has_more,next_cursor`，其中 `group` 只用于复合菜单分组展示。候选来自完整 eligible group domain，目标列自己的 filter（或目标 pane 自己的 time filter）在候选查询中移除，其余 search/filter 继续生效。
- 复合列只接受带类型前缀的 option value：银行 `amount` 使用 `direction:`、`account:`、`bankTag:`；OA `applicant` 使用 `oaType:`、`workflow:`、`applicant:`；OA `projectName` 使用 `expenseType:`、`project:`。同一前缀多值 OR，不同前缀 AND；银行三类条件必须命中同一 bank member，OA 类型/流程/申请人必须命中同一 OA member，项目/费用类型必须命中同一 `expense_items[]` 元素。没有子项的 OA 才可使用顶层项目/费用类型。旧无前缀值返回参数错误，不保留并行兼容路径。
- 银行账户候选/过滤以 `app.app_settings.bank_account_mappings` 对账号后四位的映射为展示事实；未配置时才保留现有银行前缀解析。`bankTag:` 候选和过滤复用 `PostgresBankDetailsCanonicalQueryRepository` 的 canonical 分类投影，并且只分类当前 eligible bank id 集合，不新增关联台标签规则、read model 或逐行查询。
- `exception_bucket=unpaired|paired` 必须与请求 zone 相同，并在 PostgreSQL eligible group spine 上结合 fingerprint-bound anomaly decision 精确筛选/计数；异常抽屉一次只读当前 bucket/view/code，展开单组时再惰性读 detail。异常响应的 `by_code` 固定包含全部七个 code 与零值，`amount_total=sum(by_code)` 且 `total=amount_total+document_only`。
- 旧独立 summary HTTP、`/api/workbench/refresh-status`、page Redis cache、refresh enqueue 和 generation/version 参数均不是当前 API。

关系分区只允许 `paired` / `unpaired`：

- `paired.groups[*]` 必须一一对应冻结要求已满足且无 pending/keep 异常，或当前服务端异常 bundle 已 `accept_paired` 的 active 正式关系；完整包含 relation 成员，感叹号与具体异常 Chip 不因接受风险而消失。
- `unpaired.groups[*]` 可以是一个未被 active relation 占用的 canonical singleton，也可以是冻结要求未满足的 active relation group；后一种必须返回 `completion.is_complete=false` 和精确 `missing_row_types`，不能拆散 relation ownership。
- 普通 relation 含 OA 但缺银行流水时必须位于 `unpaired`，并返回 `missing_row_types=["bank"]`；OA 附件发票 immutable binding 只表达 ownership，不等于付款链路完整。显式 batch-accounting/ETC batch relation 继续使用各自登记的完整性豁免。
- `summary` 使用 `paired_count` / `unpaired_count`；不得返回 `open_count` 或把 candidate/decision 作为第三种关系状态。
- 历史 row `case_id`、来源 section、display tag 或 candidate/decision metadata 不能合并未配对行，也不能隐藏 canonical fact。
- 未知 zone/group type 必须返回结构化 contract error，不能静默映射为 unpaired 或 paired。

Workbench detail row payload 可包含可选对象身份字段：`object_identity`、`object_identity_key`、`object_identity_kind`、`object_identity_source`、`object_identity_confidence` 和 `identity_alias_rows`。这些字段用于 canonical 审计、跨区重复治理和详情解释；compact summary rows 不重复输出它们。前端动作仍以 typed canonical identity 和 preview proof 为准，不得用展示字段推测身份。

Workbench row payload 还可包含可选来源字段：单值兼容字段 `source_kind`、复数来源证据 `source_kinds[]`，以及 `source_oa_id`、`source_oa_row_id`、`derived_from_oa_id` 和 `oa_row_id`。`source_kinds[]` 从 canonical `source_links[]` 稳定去重得到，可同时包含 `manual_invoice_import`、`oa_attachment_invoice`、`oa_expense_item_invoice`；它保留完整 provenance，但页面主来源只按 OA附件优先、人工导入其次显示一个 Chip，`oa_expense_item_invoice` 另显示“明细归属”，未知值不得默认映射为人工导入。OA 来源字段是多 OA active relation 内做横向子分段的 canonical 事实证据；银行流水或发票行有确定归属时由 page hydration 批量组装，前端只消费 `source_oa_*` 与 `source_expense_item_ids[]` 做同源同排展示，不得用 `source_kind(s)`、金额或标签猜 owner。无法确定归属时后端不得臆造 source OA，应通过 `special_metadata.row_alignment.unresolved_row_ids` 暴露。

日常报销 OA row 可以额外返回 `expense_items`：

```json
[
  {
    "id": "oa-exp-2035:item:0:...",
    "row_index": "0",
    "project_name": "曲靖项目",
    "amount": "33",
    "fee_content": "住宿费",
    "fee_description": "曲靖住宿"
  }
]
```

该数组只包含复合行展示所需字段，不返回附件正文或把 item 变成独立 relation member。`fee_content` 与 `fee_description` 分别对应 OA 来源的“费用内容”与“费用说明”，不得互相覆盖。附件状态只以 `attachment_file_count` 和是否存在精确绑定到当前子付款项的可用正式发票判定：无附件且没有该正式发票来源证明时为“发票附件缺失”，有附件但没有解析出可用正式发票为“发票附件未解析”。`oa_attachment_invoice` 与 `oa_expense_item_invoice` row 都返回去重后的 `source_expense_item_ids[]`；只有数组成员与 `expense_items[*].id` 精确相等时前端才可同带对齐。APP 内手工录入/选择发票不会改写 OA 原始附件数。同一发票连接多个付款项时前端把这些付款项与该发票渲染为一个连通展示段，发票不得复制。父 OA 仍是唯一 action/selection ID，付款项不得独立确认、撤回或参与金额配对。

`POST /api/workbench/oa-invoice-supplements/manual/preview` 接收与普通手工发票预览相同的 `invoices[]`。它只为用户从明确 OA 子付款项发起的录入生成完整 batch preview：新强身份发票返回 `created`；强身份唯一命中的现有 canonical invoice 可返回 `duplicate_skipped` 并在后续确认时复用；疑似重复、多个候选或身份不足必须整批失败，禁止按金额推断。普通 `/imports/invoices/manual/preview` 继续拒绝 duplicate，不因 Workbench 专用合同改变。

`POST /api/workbench/oa-invoice-supplements/manual` 接收该用户完整 preview 的 `session_id`、全部 `file_ids`，以及精确 `case_id`、`oa_row_id`、`expense_item_id`。确认在一个业务事务内创建或复用 canonical invoice、追加 `oa_expense_item_invoice` 来源边并创建/扩展正式关系；任一步失败全部回滚。已有 `oa_attachment_invoice` 继续保留为审计来源，但只要存在显式 expense-item 来源边，展示和异常归属就只消费显式来源。成功返回最终 `case_id` 与 `invoice_row_ids[]`，页面随后只执行一次 canonical Workbench 回读。

`GET /api/workbench/oa-invoice-supplements/gallery?page_size=9&cursor=...` 是补充凭证 owner 的全局只读列表。`page_size` 为 `1..9`，opaque cursor 绑定上一页末尾 `(created_at,id)`；响应为 `documents,page_size,has_more,next_cursor`，不返回 total、文件二进制或 raw payload。document 输出 `id,relation_case_id,oa_row_id,expense_item_id,file_name,content_type,sha256,size_bytes,created_by,created_at,content_url,thumbnail_url`。只列出 active 且 file object 未 tombstone 的记录。

`GET /api/workbench/oa-invoice-supplements/documents/{id}/thumbnail` 返回有界 JPEG 缩略图：图片按最长边 360px 缩放，PDF 只渲染第一页；返回私有 immutable cache 与内容 SHA ETag。缩略图失败返回 `422 supporting_document_preview_unavailable`，客户端必须降级为文件类型图标；原文件仍由既有 `/content` 端点内联返回。两个 GET 都不产生业务写、queue、matching 或 read-model I/O。

`POST /api/workbench/actions/assign-invoice-expense-items` 把已属于同一 active relation、但缺少有效费用明细来源边的一张 canonical invoice 显式归属到一个或多个 OA 费用明细。请求为：

```json
{
  "case_id": "CASE-1",
  "invoice_row_id": "invoice-1",
  "targets": [
    {"oa_row_id": "oa-1", "expense_item_id": "oa-1:item:0"}
  ],
  "anomaly_fingerprint": "<该发票行 oa_invoice_attachment_unassigned item fingerprint>",
  "idempotency_key": "<client-generated key>"
}
```

- `targets` 必须包含 1～100 个不重复目标；invoice、每个 OA 及其 expense item 必须仍属于请求中的同一 active case。服务端 actor/tenant 来自已认证 session，请求受 Workbench 写权限、global mutation block 与 OA sync safety gate 约束。
- 服务端在一个 Workbench UoW 中锁定 relation members 与 invoice source links，并重验 canonical rows、现有显式/历史来源、item fingerprint、幂等键及 source-links CAS。金额、项目名称和展示顺序不参与归属判断。已有不同或不完整的显式 `oa_expense_item_invoice` 边、其它有效 item ownership、成员/item/fingerprint/CAS 漂移均返回冲突且零写；不得静默覆盖旧归属。
- 成功返回 `200` 与 `success=true`、`changed`、`case_id`、`invoice_row_id`、排序后的 `targets`；实际写入时还返回 `previous_anomaly_fingerprint`。精确相同 targets 的幂等重放可返回 `changed=false`。写入只保留原有非显式来源并追加所选 `oa_expense_item_invoice` 边和 operation audit，不修改 relation topology 或 canonical amounts。
- 前端成功后只执行一次 canonical Workbench GET；不得在浏览器本地删除异常、移动分区或拼装同行。失败不得自动重试 mutation。该 action 不新增 schema、read model、worker、queue 或 cache。

`POST /api/workbench/actions/receipt-draft` 为收据编辑器读取当前草稿。请求体只含 `case_id`。目标必须是 active relation，且没有 OA、全部银行成员为正数 `inflow`、全部发票成员为 `output`、币种唯一且为 CNY，银行交易日期、付款方和发票号完整；关系位于 paired/unpaired 不影响资格，无 active relation 的 singleton 不可调用。成功响应包含：

```json
{
  "case_id": "CASE-1",
  "relation_version": 7,
  "source_fingerprint": "<sha256>",
  "total_amount": "182400.00",
  "can_print": true,
  "receipts": [
    {
      "receipt_key": "<stable group key>",
      "payer": "付款单位",
      "date": "2026-08-30",
      "currency": "CNY",
      "income_amount": "182400.00",
      "line_total": "182400.00",
      "balanced": true,
      "handler": "",
      "supervisor": "",
      "bank_transaction_ids": ["bank-1"],
      "lines": [{"summary": "技术服务费", "amount": "182400.00", "note": "", "invoice_no": "26532000000809302712", "source_invoice_ids": ["invoice-1"]}]
    }
  ],
  "reversal_adjustments": [],
  "issues": []
}
```

- 一个 active relation 固定生成一张收据；多条收入流水必须属于同一规范化付款方，否则明确返回 `receipt_payer_ambiguous`，不得按发票购买方或日期猜测拆分。收据日期默认取该关系最新收入交易日期；`income_amount`/`total_amount` 是全部正收入流水合计，也是提交时的固定核对金额。`receipt_key` 绑定该关系全部银行成员，不允许客户端增加、删除或替换收据。
- 销项红票只解析备注中精确的 `被红冲蓝字数电发票号码：<20位号码>`；服务端一次批量精确查询蓝票号码。目标必须唯一、为正数销项发票且冲销额不超过剩余蓝票金额。全额冲销后红蓝票都不生成行，部分冲销只输出蓝票净额；其它情况写入 `issues[]`，不得用号码片段、金额、购方、日期或文本相似度兜底。
- draft 是直接 canonical read，不持久化草稿，不创建 file/audit/read-model/cache/queue/worker；但入口只向拥有 Workbench 写权限且通过全局/OA 安全 gate 的用户开放，因为它只能从后续打印动作进入。

`POST /api/workbench/actions/print-receipt` 接收 draft 的并发证据和用户确认后的收据内容：

```json
{
  "case_id": "CASE-1",
  "relation_version": 7,
  "source_fingerprint": "<draft sha256>",
  "issues_acknowledged": false,
  "receipts": [
    {
      "receipt_key": "<stable group key>",
      "payer": "编辑后的付款单位",
      "date": "2026-08-30",
      "handler": "经手人",
      "supervisor": "主管",
      "lines": [{"summary": "技术服务费", "amount": "182400.00", "note": ""}]
    }
  ]
}
```

- 服务端先重读 active relation 并重建 draft；`relation_version` 或 `source_fingerprint` 变化返回 `409`。存在 `issues[]` 时必须显式提交 `issues_acknowledged=true`，否则拒绝。
- receipts 必须与服务器返回的唯一收据 exact-set 一致。付款单位、有效 ISO 日期、至少一条明细、非空摘要和正数两位小数金额必填；明细合计必须精确等于 `income_amount`。客户端平衡提示不是安全边界，服务端重复验证。
- 成功按 `银行收据!A1:J12` 生成 A5 横向一联 PDF；超过五条明细分页，合计只在末页。最终快照包含原始草稿、编辑后文档、冲销结果/异常和确认状态；相同编辑快照按文档指纹复用 `app.workbench_relation_receipts`/`app.file_objects`，不同编辑内容生成新快照。
- 响应为 `application/pdf` blob，header 携带收据 id/count/reused 事实。成功首次生成写 `receipt_generated`，每次请求写 `receipt_print_requested`；二者只表示生成和请求打印，不表示浏览器或物理打印机已完成。该动作不修改 relation、canonical invoice、统计、分区或其它页面 read model。

## 发票生命周期状态

待找发票、进项发票使用情况、OA 待付款核对、销项发票收款情况和税金抵扣的 lifecycle 字段保持原响应 shape：

- 待找发票：`invoice_acquisition_status`
- 进项发票使用情况：`paymentStatus`
- OA 待付款核对：`paymentStatus`
- 销项发票收款情况：`collectionStatus`
- 税金抵扣：`certified_status` / `is_locked_certified`

这些字段的规则来源必须是 `InvoiceLifecyclePolicy`；跨页面分发使用 `invoice_lifecycle` read boundary。新增页面不得在 API、query service 或 worker 中私有定义发票生命周期状态。

## 待找发票 API

`/api/pending-invoices*` 维护支出/收入流水发票获取状态、候选进项发票、规则建议、选择已有发票关系、收入状态覆盖和导出。

契约要求：

- 列表响应必须包含 rows、summary、statistics、pagination、稳定筛选字段定义和可解释的状态字段；直接 canonical read 不返回 read model 状态、source version 或 refresh job。`include_statistics` 默认 `true`；显式传 `false` 时 `statistics=null`，repository 只计算当前 direction 的内容依赖。页面首屏先渲染该响应，再用同一 `/rows` endpoint 的 `direction=all&page_size=1&include_statistics=true` 请求非阻塞加载全期间统计；统计失败不得清空或重新锁住已返回内容。
- filter-options 必须来自后端事实，前端不能根据当前页 rows 自行构造全局选项。`/rows` 不执行高基数 option 聚合；页面渲染 rows 后调用 `/filter-options`，每字段最多 50 项。表头下拉筛选通过 `filters` JSON 提交，字段之间按 AND 组合，同一字段内多值按 IN 组合。
- `filters` 支持四区表字段：`counterparty_name`、`transaction_tag`、`bank_account`、`direction`、`seller_name`、`oa_applicant`、`oa_application_type`、`project_name` 等；SQL read model 和 query service 必须保持同一字段语义。
- rows 中 `bank_transactions`、`input_invoices` 和 `oa` 都可以携带 `primary`、`relation_count`、`linked_relation_count`、`has_multiple`、`detail_mode` 和 `summaries`；单成员事实放在 `primary`，`summaries` 只在多成员时承载列表。旧重复字段 `bank_transaction`、`invoices`、`oa_applicant` 不再返回。同一 linked relation 下多笔银行流水、多张进项/销项发票或多张 OA 必须来自 active canonical relation distribution 并聚合为一条待找发票行；多笔银行流水时前端用 `bank_transactions.summaries` 展示真实对方户名列表，详情入口继续按 `kind=bank` 展开，不用 `+N` 替代户名，也不在户名下显示交易时间。多张发票或多张 OA 时前端仍用 `+N` 表达该类型全部成员，不再同时展示任一成员作为 primary，且同一多流水 relation 的其它成员不得再作为 standalone 行重复出现。
- OA primary/summary 必须返回 canonical `workflow_status=completed|in_progress`。OA 栏显示真实申请类型和“已完成/进行中” HeroUI chip，不再显示 OA “已配对” chip；relation 状态仍用于领域判断和详情，不得冒充 workflow status。
- `bank_transactions.payment_summary.paid_total` 表示 relation 下 linked 流水合计；`input_invoices.payment_summary` 继续表达发票合计、已付合计、待付金额和差额。未被正式化为 active relation 的自动匹配 decision 不进入下游 relation distribution，也不能作为开票、付款或已关联状态证据。
- 关系详情和候选发票接口必须返回来源、匹配原因、冲突原因和可操作权限；关系详情必须能表达同一关系中的全部付款流水、发票、OA 和 relation case id。`GET /api/pending-invoices/rows/{transaction_id}/relation-detail` 可接收 `kind=all|bank|invoice|oa`，默认 `all` 保持全量兼容；`bank`、`invoice`、`oa` 只返回对应类型列表，供 `+N` 分栏展开。
- `requires_invoice` 在列表、filter-options 和导出中是“需要开票”状态桶，不是 `filter_group='requires_invoice'` 的 SQL/规则分组条件。支出状态桶包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`；收入状态桶包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只用于解释规则命中和表头规则列筛选。
- 支出状态下拉中的 `已支付待开票` / `已支付已开票` 是 `requires_invoice` 状态桶下的状态快捷筛选，前端通过 `filter=requires_invoice` 加 `filters=[{"field":"status_code","operator":"in","values":[...]}]` 提交，不把状态码伪装成规则组。
- `POST /api/pending-invoices/invoice-candidates/batch` 接收 `transaction_ids` 和候选发票筛选/排序/分页字段，返回 `selection_summary.transaction_count`、`selection_summary.bank_total`、候选发票 rows 和 pagination。该接口按选中流水合计金额计算 `amount_difference_abs`，只支持支出流水选择进项发票。候选 rows 继续保留 `remaining_amount` 兼容旧调用方，但用于“流水关联”展示的事实字段是 `bank_relation_status` 和 `linked_bank_transaction_count`；`bank_relation_status` 可为 `unlinked`、`linked`、`already_selected`、`conflict`，不得由前端用剩余金额推断。
- `POST /api/pending-invoices/attach-existing-invoices/preview` 接收 `transaction_ids`、`invoice_ids` 和可选 request id，返回 `transaction_summaries`、`invoice_summaries`、`selection_summary.bank_total`、`selection_summary.invoice_total`、`selection_summary.difference_amount`、`payment_impact`、`warnings`、`conflicts` 和 `can_confirm`。`selection_summary.difference_amount` 是本次选择差额；关联后待付使用 `payment_impact.remaining_amount_after`。preview 不写最终 relation；当 `can_confirm=false` 时，`conflicts` / `warnings` 必须足以向前端解释确认按钮不可用的原因，`conflicts` 可以是结构化 relation 冲突对象。
- `POST /api/pending-invoices/attach-existing-invoices` 接收 preview id、`transaction_ids`、`invoice_ids` 和 request id；confirm 必须幂等写入一条 Workbench active pair relation，返回 `affected_transaction_ids`、`affected_invoice_ids`、`affected_months`、`relation_case_id` 和 `relation_mode`。若选中发票已处于兼容的 bank+invoice 或 OA+invoice active relation，confirm 必须把既有 rows 和本次选择合并到同一个 active case；后续通过关联台 withdraw 该 active case 时应恢复 confirm 前上一 active 状态。
- `PUT /api/pending-invoices/income-statuses` 接收 `transaction_ids`、`status_code` 和 request id；`status_code` 只允许 `income_no_invoice_required` 或 `cash_income`。后端必须在写入前一次性校验重复 ID、非收入流水、已关联销项发票、非法状态和不可标记状态；任一失败时整体拒绝，不允许部分成功。成功后写一条 income status command/audit/finalizer，返回 `affected_transaction_ids`、`affected_months` 和更新后的 rows。
- `POST /api/pending-invoices/manual-invoices/preview` 和 `POST /api/pending-invoices/manual-invoices` 不属于当前待找发票 HTTP contract；必须保持不可达并返回 `not_found`，其旧 service 实现也已删除。
- `POST /imports/invoices/manual/recognize` 接收 multipart `files`，只读取第一份 JPG/JPEG/PDF，返回 `{values}` 作为可编辑预填；该接口不创建发票、session 或关系。
- `POST /imports/invoices/manual/preview` 接收 `invoice_direction`、`invoice_nature`、购销双方名称/识别号、`invoice_number`、条件式 `invoice_code`、`invoice_date`、`net_amount`、`tax_rate`、`tax_amount`、`total_with_tax`。成功返回 `{values,file_id,import_session}`；精确重复返回 `409 manual_invoice_duplicate`，疑似重复返回 `409 manual_invoice_suspected_duplicate`。最终确认只使用现有 `POST /imports/files/confirm`。
- 写入类接口需要返回 affected months/objects、version 或 job，供页面局部刷新和跨页事件使用。
- 导出字段应与当前筛选和权限一致，不能绕过列表口径。

## 进项发票使用情况 API

`/api/input-invoice-usage*` 维护进项发票、付款状态、OA 和银行流水的列表、详情、筛选、导出、支付规则和反提 OA 工作流。读路径由页面专属 canonical query service/repository 承接，只访问已同步到 PostgreSQL 的 canonical facts。

契约要求：

- `GET /api/input-invoice-usage/rows` 在一个显式 `REPEATABLE READ READ ONLY` snapshot 中返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig` 和全局 `filterOptions`。旧 `/filter-options` 不是前端运行时合同。
- 页面读路径只读取 canonical input invoices、PostgreSQL OA/bank snapshot、支付规则、OA reverse facts 和 `app.workbench_pair_relations status='active'`；不得读取 input/workbench/invoice-lifecycle read model，也不得访问外部 OA/Mongo/MySQL/对象存储。
- rows、详情、导出和 OA reverse preview 使用同一 canonical query service/repository 边界；响应不含 `read_model_status`、source version、refresh enqueue、scope 或 polling 字段。
- 表头筛选通过 `filters` JSON 提交。字段之间按 AND 组合，同一字段内多值按 IN 组合；两列组合筛选仍按字段 AND 组合，例如 `oa_applicant` + `oa_application_type`、`bank_account` + `bank_direction`。
- `filterOptions` 必须由后端根据完整筛选结果生成并随 rows 返回，前端不能根据当前页 rows 推导。当前页面可筛选字段包括 `seller_name`、`payment_status`、`oa_applicant`、`oa_application_type`、`oa_project_name`、`bank_counterparty_name`、`bank_account`、`bank_direction`。
- `seller_name` 的前端列名为 `销方名称`。`bank_account` 展示为银行名称加账号后四位；`bank_direction` 原始值保持后端事实值，前端展示为 `收入` 或 `支出` chip。
- 发票号码列表头只提供开票日期排序，不提供下拉筛选。排序通过 `sort_field=invoice_date` 和 `sort_direction` 提交。
- 支付状态列表只展示状态标签；规则原因和自动闭环解释不在列表行内展示。
- rows summary 中的 `invoiceCount` 按唯一进项发票 ID 统计，用于页面表头展示“进项票 N”。`pagination.total` 是表格行数/配对组行数；同一 linked relation 下多张进项发票折叠到一行时，`invoiceCount` 必须计入所有 `invoiceRelations.summaries` 成员。
- rows 中 `oa`、`bankTransactions` 和 `invoiceRelations` 都可以携带 `relationCount`、`hasMultiple`、`detailMode`、`relationStatus` 和 `summaries`。同一 linked relation 下多条 OA、银行流水或进项发票必须聚合为一条发票使用情况行，金额字段返回各自合计；前端用 `detailMode=list` 显示 `+N` 并通过 `/rows/{row_id}/relation-details?kind=oa|bank|invoice` 展开全部明细。
- rows 的每条 OA summary 必须返回 canonical `workflowStatus=completed|in_progress`；OA 申请人总览列只显示申请人、真实申请类型、多 OA 数量和合计金额，不显示流程状态。单条 OA 详情与多 OA 关联详情只使用 `workflowStatus` 显示“已完成/进行中”，不得从 relation `status/section` 推断流程状态。
- `relationStatus="linked"` 是唯一已关联关系状态；没有 active relation 的行按未关联处理。历史 `relationStatus="candidate"` 只作为旧 payload 兼容值，调用方必须归入未关联/非证明口径，不得展示独立“候选 OA”筛选，也不得参与支付状态、已支付判断或 confirmed relation 判断。
- `/rows/{row_id}/relation-details` 按 `row_id` 在 canonical snapshot 中定向读取并展开 summaries；不存在返回 404。不得回退页面 read model、全量 live rebuild 或返回 202 refreshing。
- 反提 OA 工作流按 `preview -> one-step create OA draft -> staged draft -> user submission confirmation -> submitted history / local rollback` 推进。前端只暴露 `创建 OA 草稿` 一个创建动作；后端可以继续保存内部 batch，但不得把 `创建本地批次` 作为用户概念暴露。创建 OA 草稿只表示外部 OA 草稿已生成，状态为 `oa_draft_created`，该状态在 UI 中展示为 `暂存`，不得直接等同于已提交 OA 流程。
- `/api/input-invoice-usage/oa-reverse/preview` 必须把可创建候选和 rejected invoice 明确分开，并同时返回 `permissions.canCreateDraft`（当前操作人的创建能力）和顶层 `canCreateDraft`（当前 preview 集合满足权限、候选与唯一非空销方后的最终状态）。已有 active/linked OA 关系的发票不得进入候选或创建草稿 payload，rejected row 必须带 `reasonCode=already_has_active_oa`、`oaRelationStatus=linked` 以及发票号、销方、开票日期、价税合计、支付状态等展示字段，供前端显示 `已关联oa`、禁用勾选和按 OA 关联状态筛选。无 active OA relation 的发票展示为 `未关联oa`，对应 `oaRelationStatus=unlinked` 或缺省值；历史 `already_has_candidate_oa` / `oaRelationStatus=candidate` 兼容 payload 也必须按 `未关联oa` 处理，不再提供独立候选 OA 筛选。前端对用户当前勾选子集只能做轻量同销方判断；创建前必须用精确发票 ID 重跑 preview，并以返回的权限、最终状态和 hash 为准。
- 进项发票反提 OA 草稿使用支付申请 form `2` 的标准草稿 payload：顶层包含 `formId`、`isDraft`、`data`，`data.userName`/`data.applicant` 来自用户选择的目标 OA 申请人，`data.cause` 必须包含本地反提批次 ID，供 OA 投影回扫识别。
- `POST /api/input-invoice-usage/oa-reverse/oa-draft` 是当前一键创建入口。请求必须携带 preview id/hash、幂等 key、目标申请人和选中发票；后端重新校验候选、权限和目标申请人凭据后，用目标申请人凭据/token 创建 `isDraft=true` OA 暂存草稿。不得使用当前操作人的请求 token 创建目标申请人草稿。
- `GET /api/input-invoice-usage/oa-reverse/staged-drafts` 返回状态为 `oa_draft_created` 的暂存批次，供用户在关闭确认弹窗、刷新或重新打开 drawer 后恢复二选一。前端暂存列表不得展示 OA 草稿链接，只展示批次摘要和两项处理动作。
- 用户在 OA 页面处理草稿后，前端必须让用户选择 `submitted` 或 `not_submitted`。`submitted` 对应 `我已在OA系统提交该草稿 / OA正在进行中`，进入本地 `submitted_confirmed` 历史；`not_submitted` 对应 `OA提交内容需修改 / 删除本次提交内容`，只清理 FinOps 本地当前草稿字段并回到可重新创建状态，不展示为已提交历史，也不调用 OA 删除外部草稿。关闭确认弹窗不得调用该接口或清理 batch。
- `GET /api/input-invoice-usage/oa-reverse/submitted-history` 只返回业务可读字段，例如目标申请人、确认时间、金额、发票张数和发票摘要；不得返回 `batchId`、`oaDraftId`、`previewHash`、英文内部状态、密码、密文或 token。

## OA 待付款 API

`/api/oa-pending-payments*` 维护 OA 待付款、付款流水和进项发票关系核对。

契约要求：

- 首屏唯一聚合入口是 `GET /api/oa-pending-payments/rows`；旧 `GET /api/oa-pending-payments/filter-options` 不存在。`filterConfig` 和全局 `filterOptions` 随 rows 响应返回，前端不得根据当前页 rows 推导。
- rows、summary、facets、pagination 和详情由 `OaPendingPaymentQueryService` / `PostgresOaPendingPaymentQueryRepository` 在同一 `REPEATABLE READ READ ONLY` snapshot 中读取 `app.oa_applications`、`app.oa_pending_payment_admissions`、canonical 银行/发票和 active relations。页面/API 不读取 `oa_pending_payment` read model，也不直接访问外部 Mongo/MySQL。
- 成功固定返回 `200`；响应不含 `read_model_status`、source version、ETag、refresh enqueue、scope 或 operation-barrier target。页面只处理 loading、empty、error、手工刷新和写后一次普通 GET。
- `t_payment_simple.id` 不是 OA ID，不能作为 OA 匹配 key；OA 匹配和写回 key 必须使用 `flow_id` 对应的确定性 OA 支付身份。当前身份可能是 Mongo 文档 ID，也可能是历史已存在的 `flowRequestId/processId` 业务流程号；两者必须由同一 current canonical OA 文档导出，禁止按金额或文本猜测。
- rows `summary` 必须包含 `viewCounts.completed/in_progress`，用于页面展示切换按钮数量；该统计使用同一搜索、月份、交易日期和 column filters，但不受当前 `view_mode` 限制。
- rows 中 `oa` 必须携带 `workflowStatus`；`oa`、`bankTransaction`、`invoice` 都可以携带 `relationCount`、`detailMode` 和 `summaries`；同一 Workbench active relation 下多条 OA、支出流水或进项发票必须聚合为一条核对行，金额字段展示各自合计。
- `paymentStatus` 只返回 `paid` 或 `unpaid`。active linked付款关系驱动 `paid`；金额差异、缺失银行事实或非支出边保留在reason/amount/writeback校验中，不产生 `pending_review`、`partially_paid`、`overpaid` 或 `merged_paid`。
- rows 可返回 `oaPaymentWriteback`，用于表达 OA MySQL `t_payment_simple` 写回状态。`oaPaymentWriteback.code` 至少支持 `written` / `not_written`，`syncStatus` 表达 `ready`、`unavailable`、`flow_id_missing` 或 `not_required` 等同步语义。
- 详情接口返回 OA、付款流水、发票、正式关系和异常原因；`/rows/{row_id}/relation-details` 支持 `kind=oa|bank|invoice`。
- `filterConfig`/`filterOptions` 至少包含 OA 申请人、项目名称、支付状态、对方户名、银行账户、收支、发票方和开票日期等表头筛选/排序字段；银行账户字段使用“银行名称 + 账号后四位”，收支字段使用 `outflow`/`inflow` 值并显示“支出”/“收入”。
- canonical repository 不可用时返回明确业务错误，不返回旧 projection、HTML 或空 body。

### OA 事实源导出

`GET /api/oa-pending-payments/export?sources=completed,in_progress`

- `sources` 必填，可重复或逗号分隔，只允许 `completed` / `in_progress`，至少一种；响应按固定来源顺序生成 `已完成OA` / `进行中OA` sheet。
- 导出范围是该 tenant 的全部选中 OA canonical facts，不读取也不继承 rows 的月份、关键字、日期、列筛选、排序、分页或 view mode。
- 固定 OA-only 列为：`OA ID`、`OA单号`、`流程状态`、`归属月份`、`申请人`、`申请类型`、`申请时间`、`完成时间`、`项目名称`、`申请金额`、`往来单位`、`申请事由`、`费用类型`、`费用内容`。不得输出流水、发票、关系、支付 read model 或 raw payload。
- 成功返回 XLSX MIME、UTF-8 `Content-Disposition`、`Cache-Control: no-store`，空来源 sheet 保留表头；总 OA 行数上限 20,000，超限返回结构化 `400`。
- read-export-only 与 full/admin 可以下载，未认证或 denied 用户拒绝；成功审计只记录 actor、来源、数量和文件名，不记录 OA 内容。

### OA 支付状态自动同步

`POST /api/oa-pending-payments/writeback-paid` 已退役并固定返回 `404`；页面不再展示人工“写回”按钮，也不存在 GET 触发写回的路径。

- 唯一触发事实是 `app.workbench_pair_relations` 的正式关系变更：目标 OA 只要位于至少一条 active 且含 canonical 支出流水的关系中，就通过 durable `oa.payment_status.reconcile` 事件将 `t_payment_simple.pay_status` 同步为 `1`。OA 与流水金额是否相等只保留为关系异常，不阻断支付状态同步。
- 只有收入流水、candidate/decision、inactive/withdrawn 或历史 pending relation/claim 都不能触发“已支付”。
- 关系撤回或拓扑变化后，worker 以最新 active topology 重算；目标 OA 没有任何 active canonical 支出流水时固定写回 `pay_status=0`（待支付）。不保留 App ownership 门禁，也不区分原支付状态由 App 还是外部系统写入。
- `pay_status=2`（支付失败）必须 fail closed，禁止自动覆盖；缺 OA、缺 canonical 流水或无法解析 `flow_id` 必须形成明确失败事件，禁止猜测字段或静默跳过。
- 同一 OA ID 同时存在 completed 与 in-progress 快照时 completed 优先；多个 canonical OA row 解析到同一 `flow_id` 时每个事件只写一次外部状态。
- handler 由现有 `oa-sync` worker 承担，采用 at-least-once 幂等处理；外部状态成功后必须同步记录 PostgreSQL payment-status snapshot。Migration `0160` 删除旧 ownership 状态，并为全部已完成 OA 与已准入进行中 OA 的并集只登记 reconcile event，不直接批量修改外部支付状态。
- 支付状态从属于 OA 源生命周期。只有完整 `all` OA 权威扫描以 lifecycle arbitration 后、local retention 过滤前的 current canonical OA 支付身份集合（Mongo document ID + `flowRequestId/processId`）确认 MySQL status flow 已消失时，snapshot 事务才删除 PostgreSQL payment-status row 并登记 `oa.payment_status.reconcile(operation=remove_missing_oa_statuses, removed_flow_ids=[...])`。worker 删除 MySQL `t_payment_simple` 前必须按候选确定性身份定位两个配置 OA 表单内的原始文档，再按其业务编号重读同组流程并执行相同的 lifecycle arbitration；只有候选仍属于当前 canonical OA 时才保留，同时合并 completed projection 与 pending admission。历史原始文档仍存在但已被同业务编号的新流程取代，不得阻止删除。源读取失败或 canonical flow 重现时不删除。month sync、精确附件刷新和 retention 裁剪不能声明外部 OA 删除。

`GET /api/oa-pending-payments/bank-transaction-candidates`

该接口为进行中 OA 的“关联支出流水”抽屉提供候选支出流水。

查询参数：

- `relation_status=all|unmatched|matched|linked_in_progress`，默认 `all`。
- `keyword`，可选，按候选 payload 做关键字筛选。
- `page` / `page_size`，默认 `1` / `100`，`page_size` 上限为 `200`。
- repeated `oa_row_ids`，可选。抽屉从已选 OA 打开时必须传入；后端不使用这些 OA id 推导候选月份，候选池始终读取全部支出流水。`oa_row_ids` 只作为后续提交关联的目标 OA 上下文和诊断回显；有 OA id 但无法解析月份时也不得返回空候选。

响应 `filters` 必须回显 `relationStatus`、`keyword` 和 `oaRowIds`。不得再输出 `monthScopes` 或其它暗示候选池按 OA 月份收敛的字段。

`POST /api/oa-pending-payments/link-bank-transactions`

该接口是进行中 OA 显式关联支出流水入口。请求由前端传入选中的 `oa_row_ids` 和 `bank_transaction_ids`；`case_id` 是服务端关系所有权标识，不属于本接口的客户端输入，服务端不得信任或采用请求中伪造的 `case_id` / `caseId`。后端必须通过 `WorkbenchRelationCommandService` 创建正式 active relation，或在目标成员只命中一个 active case 时原地扩展该 case并保留已有发票成员；多个 active owner、成员冲突或非法方向必须 fail closed。不得写历史 `app.oa_pending_payment_bank_relations` 或 `app.bank_transaction_relation_claims`，也不存在后续 promotion。关联成功响应返回 `paymentStatusSync.code=queued`；支付状态由 relation repository 同事务登记的 `oa.payment_status.reconcile` 事件异步收敛，不由页面 command 直接写 MySQL。前端和后端都不再提供人工 `confirm-paid` / `writeback-paid` 入口。

### 工作台 row detail

`GET /api/workbench/rows/{row_id}?month=all&row_type=oa|bank|invoice`

该接口返回单条 OA、银行流水或发票 row 的 latest-committed 详情 payload，用于三栏详情弹窗。`row_id` 必须 URL encode；`month` 可为 `all` 或 `YYYY-MM`；`row_type` 必须是列表返回的 typed identity，防止不同 pane 的同文本 ID 碰撞。

契约要求：

- 唯一生产链路是 `WorkbenchRowDetailApiRoutes -> WorkbenchQueryFacade -> PostgresWorkbenchPageQueryRepository`；按 typed identity 直查对应 canonical source 并用 active relation typed membership 复核，不读 page projection/cache，不构建全 scope group CTE，也不从 row id 猜 pane。
- 客户端不携带 `expected_read_model_version`。detail 默认采用 latest-committed 语义；如列表之后成员被撤回/删除，返回明确 404，前端不自动重放业务写入。
- typed canonical row 存在时返回 `200`；不存在返回 `404 workbench_row_not_found`；repository、migration 或查询超时返回 `503 workbench_query_unavailable`，不返回部分 payload。
- ETC 与流水规则批次 summary 只用于折叠展开，不提供 row detail 入口。该接口不写 relation，也不接入 `WorkbenchRelationCommandService`。

### 工作台退役接口

`GET /api/workbench/refresh-status` 和旧 `/api/workbench/events` 都不是当前合同，并返回 `404`。客户端不轮询 page freshness/generation；route entry、查询变更、显式重试或写成功后只执行 normal canonical GET。App Health、OA sync 和 background jobs 保留各自的独立状态 API，不得借用 Workbench 页面合同。

## ETC 业务批次 API

ETC 对账任务、ZIP 导入和 OA 草稿提交统一使用 `/api/etc/business-batches*` 作为契约层。它取代前端直接拼接 `EtcImportBatch` 和 `EtcBatch` 的展示口径；旧 `/api/etc/batches*` 已删除，不得作为兼容或测试 mock 入口恢复。

契约要求：

- 响应必须区分导入批次、业务批次、OA 草稿和人工提交确认状态；ETC 专用 OA 自动检测状态不再作为业务批次 API 合同输出。
- business batch summary payload 必须返回 `businessBatchId`、`taskId`、`title`、`status`、`version`、必要 OA 标识、`invoiceSummary` 和 `createOaDraftAction`；不得返回 `invoiceIds/importAttempts/auditEvents` 或 task 嵌套详情。精确 detail 才返回 invoice/import/audit 明细。
- ETC 票据管理页只按 `bucket=unsubmitted|staged|submitted` 与分页调用 `GET /api/etc/business-batches`，不发送 `month`、`plate` 或 `keyword`，并展示三个互斥 bucket。`oa_draft_creating` 与 `oa_confirmation_pending` 都只属于 staged；submitted statuses 只属于 submitted；其余 active statuses 属于 unsubmitted。API 仍保留可选 `month`、`plate`、`keyword` 作为兼容/运维查询合同；调用方显式传入时，响应中的 `counts.unsubmitted/staged/submitted` 必须先应用同一组 actor scope 与可选查询条件再统计，`items` 在同一筛选结果上继续应用请求 bucket 和分页。
- 用户可见批次列表必须以 `/api/etc/business-batches*` 为事实源；`/api/etc/reconciliation-tasks` 只承载导入、核对、source file 和 workflow 状态，前端不得把 task-only 记录无条件混入批次列表或批次计数。
- `GET /api/etc/reconciliation-tasks/ready-for-import` 是 ETC 导入页的窄摘要合同。`tasks[]` 与 `unavailableTasks[]` 只返回 `taskId/status/version/title/periodStart/periodEnd/oaTotalAmount/etcInvoiceCount/supplementCount/vehiclePlates`，后者额外返回 `importBlockers[]`；不得返回 source files、信用卡行、票根行、核对明细、解析问题或 audit events。repository 必须用一次摘要投影读取 ready 与 unavailable，禁止加载完整 reconciliation state 后二次序列化。
- `POST /api/etc/business-batches` 可以省略 `taskId`。省略时后端 application service 必须复用现有 reconciliation task service 先创建任务，再通过 business batch service 创建 active 业务批次，并返回统一 `businessBatch` payload；若业务批次创建失败，必须通过 reconciliation task service 删除/tombstone 本次新建任务，避免留下 task-only 空批次。传入 `taskId` 时仍按既有绑定任务语义校验 active business batch 约束。请求可带 `title`，未传时默认 `新建ETC批次`，并同步作为 linked reconciliation task title。
- `PATCH /api/etc/business-batches/{id}` 只用于修改未提交业务批次标题。请求体为 `{ "title": string, "expectedVersion"?: number }`；空标题返回 `422 invalid_business_batch_title`，版本冲突返回 `409 version_conflict`，已提交、人工确认已提交或 closed 批次返回 `422 business_batch_title_locked`。成功响应返回更新后的 `businessBatch`，版本递增，并同步 linked reconciliation task title；ETC 发票导入 ready task 下拉必须显示同步后的标题。
- `POST /api/etc/business-batches/{id}/oa-draft` 必须接收非空 `idempotencyKey` 和当前 `expectedVersion`。后端先持久化 creating attempt，再在 ETC 锁外上传附件/创建 OA，最后以 attempt/version CAS 完成；同 intent 重放不得创建第二个 submission，网络超时/响应丢失不得自动重试。
- `POST /api/etc/business-batches/{id}/oa-draft/recover` 是管理员专用的历史/技术恢复入口，请求必须带 `expectedVersion/reason/evidence`，并且二选一：提供完整 `oaDraftId+oaDraftUrl` 采纳已核实草稿，或 `confirmedNotCreated=true` 确认外部未创建。普通页面不调用该入口。
- 权限不足、状态冲突、发票占用、OA 草稿失败和撤销失败需要返回稳定错误码。
- dry-run、迁移和人工确认动作要返回 affected batches、affected invoices、affected months 和审计信息。
- 用户点击创建 OA 草稿后，批次立即以 `oa_draft_creating` 进入 staged；OA 返回草稿信息后可转为 `oa_confirmation_pending`，两种状态都使用 `POST /api/etc/business-batches/{id}/manual-oa-status` 确认 `submitted` 或 `not_submitted`。App 不查询或推断 OA 侧草稿状态，决定来自用户声明。
- `GET /api/etc/business-batches/{id}/invoice-pdf` 使用 read session，在业务批次已有 `oaDraftId` 或状态属于 submitted 集合时可用。成员必须来自该批次 `invoice_ids`，按开票日期、发票号、ID 稳定排序；每张来源 PDF 必须恰好一页且通过已记录 SHA-256 校验。成功返回 `application/pdf`、`Content-Disposition` UTF-8 文件名、`Cache-Control: private, no-store`、`X-ETC-Invoice-Count` 和 `X-PDF-Page-Count`，并记录下载审计；任一来源异常时不返回部分文件。未创建草稿且未提交/空批次返回 409，数量或总字节超限返回 413，文件不可读返回 503，损坏或非单页返回 422。
- `POST /api/etc/business-batches/{id}/invoice-pdf/repair` 是管理员专用的 submitted 历史附件恢复入口。multipart 请求包含一个或多个原始 ZIP、当前 `expectedVersion` 和非空 `reason`；只允许补回该批次已有发票当前不可读的 PDF/XML。既有 hash 存在时原始内容 SHA-256 必须完全相等；只有附件路径/hash、导入 batch/session 全空且 `zip_source_name=canonical_invoice:*` 的历史后补成员可以从原始来源 bootstrap，并且必须同时恢复单页 PDF/XML、核对发票号/日期/双方名称税号/金额税额合计/PDF 文本、校验 business/submission 成员一致。bootstrap 同步采用原始 XML 的通行日期、车牌、车型和来源并重算提交批次汇总；成功按 CAS 递增版本并写逐发票变更审计，持久化失败必须回滚元数据并删除本次新对象，重复执行不递增版本并返回零修复。该接口不得新增发票、改变批次成员、OA、relation 或 submitted 状态。
- ETC 专用 OA 自动检测入口已移除：后端不再提供 `/api/etc/business-batches/{id}/oa-status/refresh`，不再输出 `oaDetection*` 字段，也不再注册 ETC OA 检测 worker 或 detector adapter。
- ETC invoice list 只保留 `GET /api/etc/invoices` 读侧入口；旧 `/api/etc/invoices/revoke-submitted` 已删除，不得通过 invoice id 直接回退 submitted 状态。提交状态回退必须走 business batch `manual-oa-status`、`oa-draft/revoke` 或 delete/reset 状态机。
- `submitted` 人工确认成功后，后端必须同时闭环该业务批次绑定的 ETC 对账任务；关联台 direct query/hydration 将其作为 `source_kind=etc_invoice_summary` 的 canonical display fact。该行“ETC发票数量/合计”必须从批次实际 canonical ETC 发票明细重算；散票只在用户展开时作为同组明细批量读取，不写 `workbench_rows`。若 summary 已属于 active relation，则随完整关系进入 paired；否则作为 unpaired singleton 显示。
- `etc_invoice_summary` 不存在 pending/open 关系状态。没有 active relation 时是 unpaired；正式关系创建后进入 paired。
- `DELETE /api/etc/business-batches/{id}` 对任意阶段业务批次执行本地删除/reset，不撤销 OA。请求可带 `expectedVersion` 做并发保护，不要求删除原因；成功响应至少包含 `deleted=true`、`businessBatchId`、`kind`、`releasedInvoiceCount` 和关联删除结果。后端必须删除该批次本地创建/导入的 ETC 对账任务、导入来源、核对结果、提交批次元数据和 ETC 发票；若已提交批次存在 `etc_invoice_summary`，必须释放 ETC 发票合并关系并刷新 Workbench，使原 `etc_invoice_summary` 消失。若该 summary 已参与 active relation，删除时通过 canonical relation command 取消包含该 summary 的 relation，OA 和银行流水不得恢复成二栏 active relation。`workbench_relation` distribution/read model 非 fresh 不得阻断该删除/reset；写安全以权限、expected version、canonical relation 状态、持久化和 outbox/refresh enqueue 为准，失败时返回对应稳定错误码。
- ETC 对账任务和业务批次源文件上传必须先落对象存储，再追加 source file 元数据。对象存储不可写时返回稳定错误码 `reconciliation_file_storage_unavailable` 和 HTTP 503，上传不得留下半写入的 source file、版本号或审计事件。慢解析/OCR 的结果提交必须与 source file 删除互斥；提交前来源已删除时返回 HTTP 409、`{ "error": "source_file_deleted_during_parse", "message": "源文件在解析完成前已被删除，请重新上传。" }`，不得留下孤儿解析结果或明细。`/api/etc/reconciliation-tasks/{task_id}/credit-card-statement`、`/ticket-root-files`、`/ticket-root-texts`、`/supplement-evidences` 使用直接错误结构 `{ "error": "...", "message": "..." }`；`/api/etc/business-batches/{id}/source-files` 使用 business batch envelope `{ "ok": false, "error": { "code": "...", "message": "..." } }`。

## AppHealth 运维 Dashboard API

`GET /api/operations/app-health-dashboard`

权限：

- 复用 OA session。
- 仅 `can_admin_access=true` 的管理员可访问。
- 未登录或登录态失效返回现有 `401 invalid_oa_session`。
- 非管理员返回 `403 admin_only`。

该接口独立于 `/api/app-health`。`/api/app-health` 仍用于全局健康状态、有界轮询、多标签页同步和写操作 gating。

响应结构：

```json
{
  "generated_at": "2026-05-23T10:00:00+08:00",
  "data_inventory": {
    "bank": {
      "total_count": 128,
      "latest_synced_at": "2026-05-23T09:50:00+08:00",
      "status": "available",
      "sources": [
        {
          "key": "bank_transactions",
          "label": "银行流水",
          "count": 128,
          "latest_synced_at": "2026-05-23T09:50:00+08:00",
          "status": "available"
        }
      ]
    },
    "invoice": {
      "total_count": 256,
      "latest_synced_at": "2026-05-23T09:48:00+08:00",
      "status": "available",
      "sources": [
        {
          "key": "manual",
          "label": "手工导入",
          "count": 216,
          "latest_synced_at": "2026-05-23T09:44:00+08:00",
          "status": "available"
        },
        {
          "key": "input_invoice",
          "label": "进项发票",
          "count": 236,
          "latest_synced_at": "2026-05-23T09:46:00+08:00",
          "status": "available"
        },
        {
          "key": "output_invoice",
          "label": "销项发票",
          "count": 20,
          "latest_synced_at": "2026-05-23T09:42:00+08:00",
          "status": "available"
        },
        {
          "key": "oa_attachment",
          "label": "OA 解析",
          "count": 40,
          "supplementary_count": 5,
          "latest_synced_at": "2026-05-23T09:48:00+08:00",
          "status": "available"
        }
      ]
    },
    "oa": {
      "total_count": 72,
      "latest_synced_at": "2026-05-23T09:45:00+08:00",
      "status": "available",
      "sources": [
        {
          "key": "oa_records",
          "label": "单据",
          "count": 72,
          "latest_synced_at": "2026-05-23T09:45:00+08:00",
          "status": "available"
        },
        {
          "key": "oa_records_completed",
          "label": "已完成 OA",
          "count": 61,
          "latest_synced_at": "2026-05-23T09:45:00+08:00",
          "status": "available"
        },
        {
          "key": "oa_records_in_progress",
          "label": "进行中 OA",
          "count": 11,
          "latest_synced_at": "2026-05-23T09:45:00+08:00",
          "status": "available"
        },
        {
          "key": "oa_items",
          "label": "明细",
          "count": 316,
          "latest_synced_at": "2026-05-23T09:45:00+08:00",
          "status": "available"
        }
      ]
    },
    "import_events": [
      {
        "key": "bank-5",
        "source_key": "bank_transactions",
        "label": "流水导入",
        "source_name": "bank-5.xlsx",
        "imported_by": "admin.ops",
        "count": 42,
        "supplementary_count": null,
        "imported_at": "2026-05-23T09:58:00+08:00",
        "status": "completed"
      },
      {
        "key": "invoice-4",
        "source_key": "manual",
        "label": "手工导入",
        "source_name": "invoice-4.xlsx",
        "imported_by": "admin.ops",
        "count": 18,
        "supplementary_count": null,
        "imported_at": "2026-05-23T09:54:00+08:00",
        "status": "completed"
      }
    ]
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
    "read_models": [],
    "workers": []
  },
  "freshness": {
    "warnings": []
  }
}
```

契约要求：

- Dashboard 只返回页面需要的聚合读数据，不返回业务 payload、snapshot、raw payload、token、数据库 URL 或 RabbitMQ URL。
- `data_inventory.invoice.sources` 固定包含 `manual`、`input_invoice`、`output_invoice`、`oa_attachment`。`input_invoice` / `output_invoice` 按 active canonical 发票的 `invoice_type` 统计；`oa_attachment.supplementary_count` 表示 OA 解析来源且不在手工导入中的 active 发票数；unknown 时为 `null`。
- `data_inventory.oa.sources` 固定包含 `oa_records`、`oa_records_completed`、`oa_records_in_progress`、`oa_items`。`oa_records` 是 `app.oa_applications` 申请主表总数，`oa_items` 是 `app.oa_application_items` 明细行总数；已完成/进行中按 OA projection 的 `workflow_status` 完成态合同拆分。
- `data_inventory.import_events[*]` 是全量手工导入历史，只包含银行流水和发票导入批次。每条 `count` 必须来自 `app.import_batches.success_count`；OA 解析、OA 单据同步和其它 OA runtime facts 不进入该列表。前端主页面只显示最新 5 条，抽屉展示全量历史。
- `GET /api/operations/import-history` 的 row 额外返回 `batch_id`、`batch_type`、`withdrawal_allowed`、可用的 selected/detected bank metadata 以及 `withdrawal` 摘要；`status=withdrawn` 显示“已撤回”。这些字段不把 App Health 变成业务 owner。
- `POST /api/imports/bank-transaction-batches/{batch_id}/withdraw` 仅 admin + mutate 可用，请求为 `{ "reason": string }`。成功返回 `{status:"withdrawn", batch_id, withdrawn_count, idempotent_replay, withdrawal}`；找不到返回 `404 bank_import_batch_not_found`，updated/owner 不一致/已核销/被其它业务占用返回 `409 bank_import_withdrawal_conflict` 和有界 `blockers`。写入必须是单事务，保留 OA、发票、import provenance 和 append-only audit。
- `request_performance.endpoints[*]` 包含 `duration_ms`、`database_duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_query_count` 的 p50/p95/p99。
- `runtime_performance.queues[*]` 基于已知 RabbitMQ route 输出，即使 RabbitMQ Management API 不可用也保留行，数值为 `null`。
- Dashboard API 可返回短 TTL 缓存 payload。缓存刷新失败但已有旧 payload 时，响应仍为 `200`，并在 `freshness.warnings` 中包含 `dashboard_cache_stale_after_error`。
- `runtime_performance.read_models[*].historical_refresh_duration_ms` 是 bounded history，当前同时限制为最近 7 天、且每个 event type 最多 512 条完成事件，不代表永久全历史。
- unknown 指标用 `null` 和 `status="unknown"` 表示。前端显示 `--`，不得把 unknown 当成 `0`。

## AppHealth 页面业务审计 API

`GET /api/operations/app-health/page-audit?page=<page_key>`

权限：

- 复用 OA session。
- 仅 `can_admin_access=true` 的管理员可访问。
- 未登录或登录态失效返回现有 `401 invalid_oa_session`。
- 非管理员返回 `403 admin_only`。

`page_key` 与 frontend page registry 完全一致。当前 18 个页面全部为 `ready`；`app-health-operations` 是 system proof owner，其余 17 个页面分别由有限、显式的 proof owner 执行。任何新页面在进入 frontend registry 时都必须同时登记 Audit 合同；未完成 proof 时只能 fail closed，不能把登记本身解释为可证明。

该接口是只读页面业务审计入口，复用 App 后端已有 PostgreSQL 连接，不要求调用方提供 DB URL。无 PostgreSQL runtime connection 时返回 `503 postgres_required`；未知 `page` 返回 `400 unsupported_page_audit_page`；已登记但 proof 未实现返回 `409 page_audit_proof_unavailable` 和 `overall_status=unavailable`；审计 SQL 失败返回 `500 page_audit_failed`。该接口不得刷新 read model、不得自动修复 relation、不得写入业务表。

成功响应始终为 `200`，审计是否通过由 payload 判断：

```json
{
  "mode": "page-business-canonical-read-audit",
  "tenant_id": "default",
  "page_key": "bank-details",
  "domain_key": "bank_details",
  "label": "银行明细",
  "overall_status": "pass",
  "audit_status": { "integrity": "pass", "freshness": "fresh", "queue": "drained" },
  "summary": {
    "source_fact_count": 910,
    "active_relation_count": 196,
    "linked_relation_group_count": 196,
    "issue_sample_count": 0,
    "error_sample_count": 0,
    "warning_sample_count": 0,
    "blocking_issue_sample_count": 0,
    "issue_sample_counts_by_code": {},
    "issue_sample_limit_per_code": 50,
    "issue_samples_truncated": false,
    "detected_issue_code_count": 0
  },
  "issues": [],
  "audit_contract": {
    "source_tables": ["app.bank_transactions", "app.bank_transaction_categories"],
    "read_model_tables": [],
    "relation_tables": ["app.workbench_pair_relations"],
    "scope_types": [],
    "event_types": [],
    "contract_revision": "page-audit-contract.v29",
    "proof_availability": "ready",
    "registered_read_model_keys": [],
    "relation_proof_required": true,
    "pass_condition": "audit_status.integrity == 'pass' and audit_status.freshness == 'fresh' and audit_status.queue == 'drained' and audit_contract.database_snapshot == true",
    "guarantee_boundary": "页面在一个 repeatable-read snapshot 中直接读取 App canonical facts 和 active relations；页面链路没有 read model 或 refresh queue。",
    "write_policy": "read_only"
  },
  "generated_at": "2026-07-10T00:00:00+00:00"
}
```

页面 success gate 还要求 `audit_contract.database_snapshot=true` 和 `snapshot_consistency=repeatable_read_read_only`。当前文案只能声明该数据库快照内已登记的 canonical 事实与关系一致，不能扩张为外部来源系统实时完整。

契约要求：

- 关联台登记为 `registered_read_model_keys=[]`，是 direct-canonical 页面且不消费 `workbench_relation` distribution。其 Audit 必须在一个 RR/RO snapshot 中重算 canonical facts、typed active relation membership、paired/unpaired 覆盖、异常和 exact counts，并证明 page event/cache/projection I/O 为零。成本统计、银行明细、OA 待付款、流水规则批量处理、批量账务、外部往来款、ETC 票据、税金抵扣、待找发票、进项发票使用情况和销项发票收款情况同样登记为 `registered_read_model_keys=[]`；这些 direct 页面的通过状态不得依赖 page read model、dirty scope、refresh outbox 或 shared relation projection。
- `overall_status="pass"`、`audit_status.integrity="pass"` 且 `audit_contract.database_snapshot=true` 才能声明该页面在已登记的 App 内部 canonical facts 和 active relation 合同内一致。`freshness="fresh"` 与 `queue="drained"` 对 direct-canonical 页面表示本页没有待收敛的异步读链路，不是伪造 page read-model freshness。
- `overall_status="issues_found"` 时返回有上限的 `issues` 样本；样本字段不可解释为精确总数。
- 关联台 `workbench` 与共享 `workbench_relation` read model 由系统级运行时审计验证；Search 与 no-OA projection 已退休，不进入 direct 页面 GET 或页面成功合同。
- 该接口不能证明外部银行/OA/发票/ETC 来源系统没有漏同步。外部源完整性仍必须由对应 manifest、同步 runbook 和来源系统对账证明。
- `imports.bank-transactions` 是 direct-canonical 页面：`registered_read_model_keys=[]`、`relation_proof_required=false`。Audit 双向证明已登记 file/session/batch/row/canonical bank transaction 与当前 job/outbox；bank detail、account balance、Workbench、cost 是写后 impact targets，不是该页 consumer。文件对象 hash/size 不等于银行外部 statement control evidence。
- `imports.invoices` 是 direct-canonical 页面：`registered_read_model_keys=[]`、`relation_proof_required=false`。Audit 双向证明 input/output file/session/batch/row、canonical invoice、manual source-link 和精确归属 job/outbox；同一 batch/canonical invoice 的不同物理明细按整票金额比较，完全相同的重复行不二次加总。下游 read models 与业务配对关系不由本页通过状态推断。`POST /imports/files/confirm` 只允许 durable enqueue；queue 不可用返回 `503 import_queue_unavailable`，没有 inline 或 batch revert fallback。
- `imports.etc-invoices` 是 zero-own-read-model 的 direct-canonical workflow，并登记 ETC internal relation proof。`POST /api/etc/import/preview` 持久化当前认证用户拥有的 task-bound session、原始 ZIP file objects、counts/matches/fingerprint；`POST /api/etc/import/confirm` 只从 durable session 校验 owner/freshness 并 enqueue；`POST /api/etc/import/discard` 只允许 owner 幂等终结尚未确认且没有活跃或成功 job 的 preview。Audit 双向证明 session/file/task/requirement/business-import-batch/ETC-invoice/canonical bridge 与 job/outbox；历史 failed/preview session 仅在精确 task 已正式 `imported/closed` 时作为 covered warning，其它失败继续阻断；不推断下游 Workbench 配对或外部 ETC ZIP 完整性。
- `tax-offset` 是明确的 direct-canonical relation 非消费者：canonical expected-set 来自 active `app.invoices`、`app.tax_certified_import_records` 与最新 saved `app.tax_offset_plans`。Audit 独立重算 output/input/certified/matched/outside 五组 item、认证匹配优先级、锁定、默认选择、税额 summary 和结构化展示字段；`relation_proof_required=false`，成功文案必须显示“本页面不消费配对关系”，不得宣称已证明配对关系。页面成功不以 Tax Offset read model source versions、dirty scope 或 outbox freshness 为条件。
- `etc-tickets` 是 `registered_read_model_keys=[]` 的直接 canonical 页面；统一 executor 在一个只读 repeatable-read snapshot 内证明 business batch/task/file/ETC invoice/import/submission/canonical invoice bridge 的集合、字段与内部 typed edge，并以 `job.import_jobs(import_type=etc_invoice_import.confirm)` 判定 queue。只有 `pending/processing` job 属于 backlog；`failed/dead_lettered` 是终态，只有精确关联的 reconciliation task 已 `imported/closed` 才作为已覆盖历史失败并计入 additive `summary.covered_failed_import_job_count`，否则阻断 integrity。成功不能依赖伪造的 page read-model status；也不能把 Workbench、tax、cost 或 invoice-lifecycle 下游影响目标声称为本页 consumer。外部文件字节、ETC 归档和真实 OA 草稿状态不在此合同内。
- `settings` 是 `registered_read_model_keys=[]`、`relation_proof_required=false` 的 direct-canonical control-plane 页面。Audit 证明唯一 settings singleton、生产归一化合同、非敏感 credential summary 和 settings reset jobs；credential SQL 不解密也不选择密文，报告不得出现密码/token/secret。OA project provider、真实 credential 登录、manual OA search/import 和 reset 后多页面 smoke 属于 external gate。

### App Health System Audit 响应

`page=app-health-operations` 不打开第 18 个独立事务。后端只打开一个 outer `REPEATABLE READ READ ONLY` transaction，把同一 caller-owned Audit snapshot 传给其余 17 个页面 proof，并在该 snapshot 内独立重算 App Health inventory、read model manifest/status、required worker heartbeat 和 current durable queue。响应在普通 page Audit 字段之外至少包含：

- `database_system_snapshot`：`system_audit_id`、PostgreSQL `snapshot_identity`/时间、18 页合同 revision/version set、页面结果、registry/manifest/worker fingerprint 和 durable runtime 证明。
- `runtime_observation`：request metrics、RabbitMQ transport 等 point-in-time 观测；必须明确 `database_snapshot=false`，不能冒充数据库快照事实。
- `external_evidence`：银行、OA、发票和 ETC 四个独立 `complete_snapshot/all` manifest 与 App canonical facts 的精确双向证明。每个 domain 返回 evidence id/fingerprint、source snapshot、observed/valid time、missing/extra/field mismatch/control mismatch 和有上限的问题样本；页面覆盖来自 registry 的显式 domain keys，不从说明文字猜测。
- `page_projection`：与 database system proof 同一 snapshot 构建的 App Health dashboard payload。

System Audit 的 `overall_status=pass` 只证明该 immutable snapshot 内 18 页已登记的 App 内部合同完整一致。只有四个外部 domain 同时 `pass` 时，`external_evidence.status=pass` 与 `end_to_end_source_truth=proven_as_of_external_evidence` 才成立；该声明严格绑定 manifest 的 `observed_at/source_snapshot_id` 与当前 App immutable snapshot。缺 manifest 为 `unknown/unproven`，最新 manifest 被撤销、过期、覆盖不全或精确集合/字段/control 不一致为 `fail/unproven`，不得回退旧版本。它仍不证明 Audit 后发生的写入或外部实时状态。页面下一次普通 dashboard refresh 必须清除历史 Audit 绿色状态，避免把旧 snapshot 继续展示为当前结论。

## 已退休页面 Read Model 刷新 API

以下运维写入口已删除：

- `POST /api/operations/app-health/input-invoice-usage-refresh`
- `POST /api/operations/app-health/output-invoice-collection-refresh`
- `POST /api/operations/app-health/pending-invoice-refresh`

三个 route 统一返回 `404 not_found`，且不得写入 durable runtime queue。进项使用、销项收款和待找发票页面
按各自 API 合同直接读取 canonical facts；App Health 只保留
`GET /api/operations/app-health/page-audit?page=<page_key>` 只读证明入口，不承担页面刷新或修复。

## 版本和兼容

当前项目仍保留部分旧接口。新增能力应优先接入 `/api/*` 契约层；旧接口只用于兼容测试或历史页面，不应继续扩展。

## 销项发票收款情况 API

`/api/output-invoice-collections/*` 由 Invoices 模块承接。页面直接读取 canonical
销项发票、收入流水与 active Workbench 正式关系，不使用页面 read model。`server.py`
只装配 route object；`app/routes_output_invoice_collections.py` 只负责路径、session、
权限和 HTTP 映射；查询编排在 `OutputInvoiceCollectionCanonicalQueryService`，SQL
在 `PostgresOutputInvoiceCollectionQueryRepository`。

读接口：

- `GET /api/output-invoice-collections/rows`
- `GET /api/output-invoice-collections/filter-options`
- `GET /api/output-invoice-collections/export-preview`
- `GET /api/output-invoice-collections/export`
- `GET /api/output-invoice-collections/invoices/{invoice_id}/detail`
- `GET /api/output-invoice-collections/bank-transactions/{transaction_id}/detail`
- `GET /api/output-invoice-collections/rows/{row_id}/relation-details?kind=bank|invoice`

`rows` 每行只包含：

- `id`
- `invoiceId`
- `invoiceIdentityKey`
- `invoice`
- `collectionStatus`
- `bankTransactions`
- `invoiceRelations`

页面不返回 OA、收据、人工状态、提醒或手工红蓝票字段，也不返回
`read_model_status`、refresh enqueue、scope 或 polling 字段。页面表格只有
“销项发票 / 收款状态 / 收入流水”三个分组。

收款状态由 canonical 事实派生：

- `pending_collection`：待收款。
- `partial_collected`：部分收款。
- `collected`：已收款。
- `reversed_by_red`：正数蓝票已被红票冲销。
- `reverses_blue`：负数红票已冲销蓝票。
- `unmatched_red`：负数红票尚未找到唯一可证明的蓝票。

红蓝票关系由 Workbench 自动匹配并写入 active 正式关系，关系
`mode=output_invoice_reversal`。只有销方税号、购方税号、币种、税率以及价税、
不含税、税额绝对值全部一致，且候选集合唯一为一蓝一红、红票日期不早于蓝票时
才自动配对；模糊候选保持未配对，不做猜测。该关系同时驱动关联台分组和本页状态。

发票原始备注精确包含“被红冲蓝字数电发票号码：{20 位发票号}”时，`invoice`
输出 `reversalTargetInvoiceNos`，列表第四列展示该号码，发票详情保留完整备注，keyword
可搜索备注中的发票号。该字段是来源备注证据，不代替、不创建、不修改
`output_invoice_reversal` 正式关系。

导出固定为当前 canonical 查询的 16 列，新增“冲红蓝字发票号码”，不包含 OA、收据、人工状态、提醒或手工
红蓝票字段。

旧状态、提醒、手工红蓝票、正式收据、收据历史和收据编号设置端点均已删除并返回
`404 not_found`；不得重新添加兼容 fallback。
