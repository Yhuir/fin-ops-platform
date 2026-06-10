# 进项发票使用情况 状态机


> 修改 `进项发票使用情况` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：页面本身是只读查询页，业务状态主要来自行 payload 中的 `paymentStatus`、OA 关联、银行流水关联和发票生命周期判断。
- 状态事实源：`read_model.input_invoice_usage_rows.payload` 是页面读取事实；发票、OA、银行流水和 workbench 关系由 read model worker 构建时投影进入 payload。
- 允许流转：支付状态规则、OA 反提、workbench 关系确认或撤销会通过 read model refresh 影响页面展示。
- 禁止流转：页面列表查询不直接修改发票、OA 或银行流水事实；缺失或过期 read model 不能回退为 live scan 伪装 fresh。

## 以发票反提 OA 本地状态机

`以发票反提 OA` 使用后端内部 batch 记录本地状态。batch 是内部状态对象，不作为前端用户概念暴露；前端只展示 `创建 OA 草稿`、确认弹窗和 `已提交` 历史。

### 目标申请人凭据状态

- `unconfigured`：目标 OA 申请人尚未配置可用于后端登录 OA 的账号密码，不能创建 OA 草稿。
- `configured`：管理员已保存目标 OA 申请人的 OA 登录账号和密码；后端只向前端返回 `已配置`，不返回密码、密文或 token。
- 状态事实源：PostgreSQL 为 `app.oa_applicant_credentials.credential_status` 与 `encrypted_password`；本地/测试模式为 `InMemoryOaApplicantCredentialRepository`。生产解密密钥来自 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。
- 允许流转：管理员保存/更新密码后 `unconfigured -> configured`；管理员删除/清空凭据后 `configured -> unconfigured`。
- 禁止流转：非 admin 用户不能维护凭据；普通 `/api/workbench/settings` 不能携带凭据；列表查询不能解密或返回密码材料。

### 状态

- `ready_to_create`：当前选择可创建 OA 草稿；前端显示 `创建 OA 草稿`。
- `creating_draft`：后端正在使用目标 OA 申请人凭据/token 创建 OA 暂存草稿；前端显示提交中状态。目标申请人登录使用 `FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_PATH` 和 RSA 加密后的密码，不能复用当前操作人的请求 token。
- `oa_draft_created`：OA 暂存草稿已创建，FinOps 已保存 `oaDraftId`/`oaDraftUrl`，等待用户确认是否已在 OA 手动提交。
- `submitted_confirmed`：用户在 FinOps 选择 `已提交 OA`，本次进入已提交历史。

`未提交 OA` 不作为长期历史状态展示。用户选择 `未提交 OA` 后，FinOps 清理当前本地草稿字段并回到 `ready_to_create`。

### 流转

| From | Trigger | To | 规则 |
| --- | --- | --- | --- |
| `ready_to_create` | 点击 `创建 OA 草稿` | `creating_draft` | 必须有写权限、目标申请人凭据已配置、候选发票仍有效。 |
| `creating_draft` | OA 暂存草稿创建成功 | `oa_draft_created` | 保存草稿 id/url 和内部 batch 状态；batch 不作为前端按钮或用户概念暴露。 |
| `creating_draft` | OA 登录、创建草稿、候选校验或权限失败 | `ready_to_create` | preview hash 校验失败、候选失效或凭据缺失时不创建内部 batch；已创建 batch 但 OA 失败时保留失败状态供诊断，前端仍返回明确错误。 |
| `oa_draft_created` | 用户选择 `已提交 OA` | `submitted_confirmed` | 进入 `已提交` 历史。 |
| `oa_draft_created` | 用户选择 `未提交 OA` | `ready_to_create` | 只回滚 FinOps 本地状态，不删除 OA 暂存草稿。 |

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

- loading：前端请求 `/api/input-invoice-usage/rows` 与 filter options 时显示页面加载态。
- empty：API 返回 `read_model_status=fresh` 且 `pagination.total=0` 时展示标准空态。
- error：API 或解析失败时展示“进项发票使用情况加载失败，请稍后重试。”。
- stale/refreshing：API 返回 `read_model_status=refreshing` 时，页面不展示旧 rows，保持刷新提示/轮询语义；服务端应入队对应 scope 的 read model refresh。
- permission disabled/hidden：列表读取无独立权限状态；OA 反提、支付规则保存等 mutation 能力按对应接口权限和前端按钮状态控制。
- oa reverse pending tab：`待处理` 页签展示目标 OA 申请人、候选发票和 `创建 OA 草稿` 主动作；不展示 `创建本地批次`。
- oa reverse submitted tab：`已提交` 页签展示用户确认过的已提交历史，只显示申请人、时间、金额和发票摘要等业务字段。
- oa reverse confirmation：OA 草稿创建成功后显示确认弹窗，用户只能选择 `已提交 OA` 或 `未提交 OA`。

## Read Model / Worker 状态

- fresh：SQL read model payload 的 `refresh_status=fresh`，且 `source_versions` 覆盖服务端期望版本时，API 返回 rows 并设置 `read_model_status=fresh`。
- missing：repository 没有可用 payload 时，API 返回 `202` 和 `read_model_status=refreshing`，并以 `api_miss` 入队。
- refreshing：dirty scope 处于 `pending`/`processing`，或 API 判定 schema/source version stale 后，会返回空 rows 的 refreshing payload。
- stale/failed/unavailable：dirty scope 失败或依赖不可用时不得把旧 rows 伪装为 fresh；调用方应触发 refresh 或展示可恢复状态。
- all scope：默认不传 `month` 的页面查询使用 `scope_key=all`。当没有单独 `all` scope 行时，repository 会从各月份 scope 聚合共同一致的顶层 `source_versions`；月份间 `workbench_relation_source_versions` 等嵌套版本可不同，不应导致基础版本被清空。若任一月份 cache status 非 fresh，all scope 仍判定不可 fresh。
- refresh 触发来源：API miss、schema stale、source version stale、业务写入后的 read model invalidation、worker all scope 展开月 shard。
- 失败恢复：通过 durable queue 重新刷新对应 month 或 all scope；all scope refresh 会展开到月 shard 后完成 queue 状态。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| - | 初始骨架 | 待补充 | - |
| 2026-06-10 | 明确 all scope source_versions 聚合规则 | 修复默认 all 查询因月份间 workbench 关系嵌套版本不同而被 API 误判 `refreshing` 的风险 | `tests.test_invoice_usage_collection_sql_runtime`、`tests.test_input_invoice_usage_api`、`tests.test_read_model_freshness`、`web/src/test/InputInvoiceUsagePage.test.tsx` |
| 2026-06-10 | 新增以发票反提 OA 本地状态机设计 | 明确 `创建 OA 草稿`、手动 OA 提交、`已提交 OA` 确认和 `未提交 OA` 本地回滚的状态边界 | 文档设计阶段，实施时按 `tests.md` 新增/更新测试 |
| 2026-06-10 | 新增目标 OA 申请人凭据状态 | 后端支持 admin-only 保存/删除凭据，API 只暴露 `configured/unconfigured` 状态 | `tests.test_oa_applicant_credentials_service`、`tests.test_oa_applicant_credentials_api`、`tests.test_postgres_oa_applicant_credentials_repository`、`tests.test_postgres_migrations` |
| 2026-06-10 | 落地目标 OA 申请人 token provider 和一步创建草稿后端状态 | `创建 OA 草稿` 后端使用目标申请人凭据登录 OA；`未提交 OA` 清理本地草稿字段后可重新创建；`已提交 OA` 进入已提交历史 | `tests.test_target_oa_applicant_token_provider`、`tests.test_input_invoice_usage_oa_reverse_service`、`tests.test_input_invoice_usage_api`、`tests.test_postgres_input_invoice_usage_oa_reverse_repository` |
| 2026-06-10 | 落地反提 OA 前端 `待处理 | 已提交` 状态 | 前端只暴露 `创建 OA 草稿`，草稿创建后弹窗确认 `已提交 OA` 或 `未提交 OA`；已提交 tab 只展示业务历史字段 | `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`cd web && npm run build` |
