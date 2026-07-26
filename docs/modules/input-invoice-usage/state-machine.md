# 进项发票使用情况 状态机


> 修改 `进项发票使用情况` 相关业务状态、UI 状态或 canonical query/command 状态前必须读取本文件。页面已于 2026-07-27 退出 read model 运行时；历史记录中的 read-model 描述不覆盖当前合同。

## 业务状态

- 当前状态：页面本身是只读查询页，业务状态主要来自行 payload 中的 `paymentStatus`、OA 关联、银行流水关联和发票生命周期判断。
- 状态事实源：页面 query repository 在一个 `REPEATABLE READ READ ONLY` snapshot 内读取 `app.invoices`、`app.oa_applications`、`app.bank_transactions`、`app.app_settings` 和 `app.workbench_pair_relations`；关系只接受 `status='active'`。
- OA 附件来源发票：正式发票的 `source_links[].source_type='oa_attachment_invoice'` / `source_workbench_row_id` 是 relation 等价 row key，canonical repository 必须与正式发票 id 一并解析。
- 允许流转：支付状态规则、OA 反提、workbench 关系确认或撤销写入 canonical facts 后，当前页面通过正常 GET 读取新状态。
- 禁止流转：页面列表查询不修改发票、OA 或银行流水事实；不得读取页面 read model、Workbench relation projection 或 invoice lifecycle read model，也不得使用 live fallback/双读。
- 支付状态规则：只有 active formal relation component 可参与已支付、完全关联或已确认关系判断；未正式化 candidate 不进入页面事实。

## 以发票反提 OA 本地状态机

`以发票反提 OA` 使用后端内部 batch 记录本地状态。batch 是内部状态对象，不作为前端用户概念暴露；前端只展示 `创建 OA 草稿`、确认弹窗和 `已提交` 历史。

OA reverse batch 只记录本地流程状态，不是 OA/发票 relation 事实源。检测到 OA evidence 后建立关系必须通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写 `input_invoice_oa_reverse`；command service 前置条件失败时，本地 batch 不得先推进到 detected。

### 目标申请人凭据状态

- `unconfigured`：目标 OA 申请人尚未配置可用于后端登录 OA 的账号密码，不能创建 OA 草稿。
- `configured`：管理员已保存目标 OA 申请人的 OA 登录账号和密码；后端只向前端返回 `已配置`，不返回密码、密文或 token。
- 状态事实源：PostgreSQL 为 `app.oa_applicant_credentials.credential_status` 与 `encrypted_password`；本地/测试模式为 `InMemoryOaApplicantCredentialRepository`。生产解密密钥来自 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。
- 允许流转：管理员保存/更新密码后 `unconfigured -> configured`；管理员删除/清空凭据后 `configured -> unconfigured`。
- 禁止流转：非 admin 用户不能维护凭据；普通 `/api/workbench/settings` 不能携带凭据；列表查询不能解密或返回密码材料。

### 状态

- `ready_to_create`：当前选择可创建 OA 草稿；前端显示 `创建 OA 草稿`。
- `creating_draft`：后端正在使用目标 OA 申请人凭据/token 创建 OA 暂存草稿；前端显示提交中状态。目标申请人登录使用 `FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_PATH` 和 RSA 加密后的密码，不能复用当前操作人的请求 token。
- `oa_draft_created`：OA 暂存草稿已创建，FinOps 已保存 `oaDraftId`/`oaDraftUrl`，等待用户确认是否已在 OA 手动提交；前端用户可见 bucket 为 `暂存`。
- `submitted_confirmed`：用户在 FinOps 选择 `我已在OA系统提交该草稿 / OA正在进行中`，本次进入已提交历史。

`未提交 OA` 不作为长期历史状态展示。用户选择 `OA提交内容需修改 / 删除本次提交内容` 后，FinOps 清理当前本地草稿字段并回到 `ready_to_create`。

### 流转

| From | Trigger | To | 规则 |
| --- | --- | --- | --- |
| `ready_to_create` | 点击 `创建 OA 草稿` | `creating_draft` | 必须有写权限、目标申请人凭据已配置、候选发票仍有效。 |
| `creating_draft` | OA 暂存草稿创建成功 | `oa_draft_created` | 保存草稿 id/url 和内部 batch 状态；用户可在 `暂存` bucket 继续处理，但不展示 OA 草稿链接。 |
| `creating_draft` | OA 登录、创建草稿、候选校验或权限失败 | `ready_to_create` | preview hash 校验失败、候选失效或凭据缺失时不创建内部 batch；已创建 batch 但 OA 失败时保留失败状态供诊断，前端仍返回明确错误。 |
| `oa_draft_created` | 用户选择 `我已在OA系统提交该草稿 / OA正在进行中` | `submitted_confirmed` | 进入 `已提交` 历史。 |
| `oa_draft_created` | 用户选择 `OA提交内容需修改 / 删除本次提交内容` | `ready_to_create` | 只回滚 FinOps 本地状态，不删除 OA 暂存草稿。 |
| `oa_draft_created` | 用户关闭确认弹窗 | `oa_draft_created` | 只关闭 UI 弹窗；batch 保留在 `暂存`，用户可稍后继续二选一。 |

### 禁止流转

- 不允许使用当前操作人的 OA token 创建目标申请人的 OA 草稿。
- 不允许在没有目标申请人凭据时创建 OA 草稿。
- 不允许只读或导出权限用户创建 OA 草稿。
- 不允许把 `创建本地批次` 暴露为前端按钮。
- 不允许把 `未提交 OA` 误记为已提交历史。
- 不允许在本地回滚时调用 OA 删除暂存草稿。
- 不允许在 API 响应、日志或前端状态中返回密码、密文或 token。

### 已提交历史

- 状态事实源：内部 `input_invoice_usage_oa_reverse_batches` 中状态为 `submitted_confirmed` 或历史兼容的手工已提交状态。
- 展示字段：目标 OA 申请人、确认时间、含税金额、发票张数和发票业务摘要。
- 禁止字段：前端历史列表不能展示 `batchId`、`invoiceIds`、`oaDraftId`、`previewHash`、英文状态或密码/token。

## UI 状态

- loading：前端请求 `/api/input-invoice-usage/rows` 时显示页面加载态；filter options 随 rows 同响应返回。
- empty：API `200` 且 `pagination.total=0` 时展示标准空态。
- error：API 或解析失败时展示“进项发票使用情况加载失败，请稍后重试。”。
- refreshing/polling：不适用。页面 API 不返回 `read_model_status`、`source_versions` 或 `202 refreshing`，前端不自动轮询；用户刷新只发起一次正常 GET。
- permission disabled/hidden：列表读取无独立权限状态；OA 反提、支付规则保存等 mutation 能力按对应接口权限和前端按钮状态控制。
- oa reverse pending tab：`待处理` 页签展示目标 OA 申请人、候选发票和 `创建 OA 草稿` 主动作；不展示 `创建本地批次`。
- oa reverse staged tab：`暂存` 页签展示状态为 `oa_draft_created` 的批次摘要和两项处理动作：`我已在OA系统提交该草稿 / OA正在进行中`、`OA提交内容需修改 / 删除本次提交内容`。暂存列表不展示 OA 草稿链接。
- oa reverse relation display：候选发票清单只展示 OA 关联二态。可反提发票展示 `未关联oa` chip 并可勾选；已有 active/linked OA 关系的发票展示 `已关联oa` chip、禁用勾选；历史 `candidate` 兼容值归入 `未关联oa`，不再提供独立“候选 OA”筛选。表头提供 drawer 内局部筛选：`全部`、`已经关联oa`、`未关联oa`，并支持发票清单搜索。
- oa reverse submitted tab：`已提交` 页签展示用户确认过的已提交历史，只显示申请人、时间、金额和发票摘要等业务字段。
- oa reverse confirmation：OA 草稿创建成功后显示确认弹窗，用户可以选择 `我已在OA系统提交该草稿 / OA正在进行中`、`OA提交内容需修改 / 删除本次提交内容`，也可以点击右上角取消只关闭弹窗。取消、页面刷新、父组件重渲染或 preview reload 都不能清空当前草稿 batch；未决批次必须可在 `暂存` 页签恢复处理。
- oa reverse local-state performance：创建草稿、确认 submitted、确认 not_submitted 都是本地 batch 状态动作，drawer 在 API 成功后立即释放按钮。evidence detected 后真正写入 relation 只提交 canonical relation/version/audit，当前页随后通过正常 GET 收敛。

## Read Model / Worker 状态

- 页面运行时：不适用。rows、summary、statistics、facets、详情和导出不读取页面/Workbench/invoice-lifecycle read model，不 enqueue refresh，也不等待 worker。
- 一致性：rows、summary、facets 和当前页 facts 在同一个只读可重复读事务内完成；active relation 按跨 case 连通 component 解析。
- 失败：canonical PostgreSQL 查询或 DTO 组装失败时返回结构化错误；不回退旧 projection。
- 共享遗留：`input_invoice_usage` projection、worker、manifest、scope policy 和 App Status 注册仍可能被全局代码引用，最终删除由主控合并后统一完成，不是页面状态。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-07-27 | 页面迁移为 canonical PostgreSQL 直读 | 删除页面 read-model gate/detail/polling/202 合同；rows/summary/facets 同 snapshot，active relation component 直接读取，写后正常 GET | `tests/test_invoice_usage_collection_canonical_query.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` |
| 2026-06-23 | 补 read model manifest 合同守卫 | 不改变进项发票使用情况业务/UI/read model/worker 状态；锁定 `input_invoice_usage` 为 scoped incremental、fan-out `all`、自管 freshness，并保持 query owner、permission owner 和 repository ports 不与 `invoice_lifecycle` / `output_invoice_collection` 混用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts` |
| - | 初始骨架 | 待补充 | - |
| 2026-06-10 | 明确 all scope source_versions 聚合规则 | 修复默认 all 查询因月份间 workbench 关系嵌套版本不同而被 API 误判 `refreshing` 的风险 | `tests.test_invoice_usage_collection_sql_runtime`、`tests.test_input_invoice_usage_api`、`tests.test_read_model_freshness`、`web/src/test/InputInvoiceUsagePage.test.tsx` |
| 2026-06-10 | 新增以发票反提 OA 本地状态机设计 | 明确 `创建 OA 草稿`、手动 OA 提交、`已提交 OA` 确认和 `未提交 OA` 本地回滚的状态边界 | 文档设计阶段，实施时按 `tests.md` 新增/更新测试 |
| 2026-06-10 | 新增目标 OA 申请人凭据状态 | 后端支持 admin-only 保存/删除凭据，API 只暴露 `configured/unconfigured` 状态 | `tests.test_oa_applicant_credentials_service`、`tests.test_oa_applicant_credentials_api`、`tests.test_postgres_oa_applicant_credentials_repository`、`tests.test_postgres_migrations` |
| 2026-06-10 | 落地目标 OA 申请人 token provider 和一步创建草稿后端状态 | `创建 OA 草稿` 后端使用目标申请人凭据登录 OA；`未提交 OA` 清理本地草稿字段后可重新创建；`已提交 OA` 进入已提交历史 | `tests.test_target_oa_applicant_token_provider`、`tests.test_input_invoice_usage_oa_reverse_service`、`tests.test_input_invoice_usage_api`、`tests.test_postgres_input_invoice_usage_oa_reverse_repository` |
| 2026-06-10 | 落地反提 OA 前端 `待处理 | 已提交` 状态 | 前端只暴露 `创建 OA 草稿`，草稿创建后弹窗确认 `已提交 OA` 或 `未提交 OA`；已提交 tab 只展示业务历史字段 | `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`cd web && npm run build` |
| 2026-06-11 | 补齐测试闭环状态机引用 | 将 all scope、OA 反提、目标申请人凭据、submitted history、UI/read model 状态纳入本轮闭环验证 | `tests.test_invoice_usage_collection_sql_runtime`、`tests.test_input_invoice_usage_api`、`tests.test_input_invoice_usage_oa_reverse_service`、`web/src/test/InputInvoiceUsagePage.test.tsx` 等本轮最小闭环 |
| 2026-06-12 | 收口 OA reverse relation 写入口 | OA reverse batch 不作为 relation 事实源；evidence detected 后通过 `WorkbenchRelationCommandService` 写 `input_invoice_oa_reverse`，non-fresh 时 fail fast 且不保存 detected batch | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-12 | 接入 unified relation candidate 和单行详情 | 关联台未配对 candidate 通过 `WorkbenchRelationReadFacade` 进入页面展示；candidate 不参与支付状态；`+N` 详情优先读取 SQL read model 单行 payload，避免全量 live rebuild 卡在加载态 | `tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_input_invoice_usage_service.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/InputInvoiceUsagePage.test.tsx` |
| 2026-06-17 | 补真实 Chromium OA reverse 子集草稿 smoke | Browser e2e 覆盖 rows 首屏、`以发票反提 OA` drawer、取消候选子集、子集 preview hash、创建 OA 草稿、`已提交 OA` 和 submitted history，防止页面维护破坏完整浏览器流 | `web/e2e/input-invoice-usage-flow.spec.ts`、`cd web && npm run e2e:smoke` |
| 2026-06-30 | 简化 OA reverse OA 关联状态 UI | 草稿创建后的确认弹窗必须等待用户二选一；已有 active OA 关系的发票展示 `已关联oa`，无 active relation 或历史 candidate 兼容值展示 `未关联oa`；筛选只保留 `全部/已经关联oa/未关联oa`，候选发票清单支持搜索，提示放在抽屉标题右侧 | `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`web/e2e/input-invoice-relation-fanout.spec.ts` |
| 2026-06-17 | 主列表通过 OA 附件 row id 查询 relation distribution | 正式发票由 OA 附件提升/合并后，列表 rows 使用正式发票 id 与 `source_workbench_row_id` 共同查询统一 relation facade，显示已有 OA/candidate 证据但不改变支付状态 | `tests/test_input_invoice_usage_service.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` |
| 2026-06-18 | 补 Spec-first Browser relation fan-out smoke | 不改变状态机；新增真实 Chromium 覆盖 candidate OA/流水证据只展示不驱动支付状态、Workbench confirm 后 linked 证据驱动 `已支付`，并在 OA reverse drawer 中证明 candidate/linked 均不可勾选 | `web/e2e/input-invoice-relation-fanout.spec.ts` |
| 2026-06-18 | 新增 OA reverse `暂存` bucket | `oa_draft_created` 作为用户可见暂存状态，关闭确认弹窗不清理 batch；暂存列表只展示两项处理动作，不展示 OA 草稿链接 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` |
| 2026-06-23 | all-scope refresh 清理 orphan month shards | 修复旧月份 read model scope/rows 不再属于当前发票事实集但继续参与 all-scope source version 聚合，导致 `oa_projection_sync_version_missing` 并长期显示“正在刷新”的问题 | `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_input_api_all_scope_recovers_after_orphan_scope_prune`、`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_input_repository_prunes_orphan_scope_shards`、`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_refresh_handler_expands_all_scopes_and_completes_with_source_version` |
| 2026-06-23 | 修正 `+N` 关系明细 source version scope | 关系明细按 `row_id` 命中 SQL read model 单行后，使用该行 `read_model_scope_key` 校验 expected source versions，避免列表 fresh 但明细被 all/no-scope relation 版本误判 refreshing | `tests/test_input_invoice_usage_api.py::InputInvoiceUsageApiTests::test_relation_details_compare_source_versions_with_row_scope` |
| 2026-06-23 | 补跨月配对 relation fallback | 进项发票月份 scope 返回 unlinked/empty relation row 时，仍按发票 row id 定向补查其他 scope 中的 linked group，并保持当前 shard source versions | `tests/test_input_invoice_usage_service.py::InputInvoiceUsageQueryServiceTests::test_month_scope_unlinked_row_does_not_hide_cross_month_linked_relation`、`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_input_projection_keeps_current_scope_relation_versions_after_cross_month_fallback` |
| 2026-06-24 | T8 module IO contract reconciliation | 不改变业务状态；明确 rows 与 filter-options 合并 fresh 后才允许普通空态和导出 | `web/src/test/InputInvoiceUsagePage.test.tsx`、`bash scripts/verify.sh docs` |
