# ETC 业务批次统一与 OA 自动提交检测设计

日期：2026-05-19

## 背景

当前 ETC 对账任务完成 ZIP 导入后，用户会看到类似两个批次的入口。根因不是 ZIP 被重复导入，而是现有模型把一个业务流程拆成两个用户可见技术批次：

- `EtcImportBatch`：记录 ZIP 发票导入来源、导入会话和发票集合。
- `EtcBatch`：记录 OA 草稿和 OA 提交批次，内部 ID 类似 `etc_batch_0001`，外部号类似 `etc_20260519_001`。

前端 `EtcTicketManagementPage` 同时展示对账任务的 `importBatchId` 详情和普通 `/api/etc/batches` 批次列表，导致一个业务动作在 UI 上像两个批次。创建 OA 草稿后，当前还要求用户手动选择“我已提交 OA”或“未提交 OA”。这个选择只更新 app 内部状态，没有从 OA 系统校验流程是否已经进入 `进行中`。

本设计目标是把 ETC 对账任务、ETC 发票导入、OA 草稿/提交统一为一个用户可见的业务批次，并由 app 后台自动检测 OA 流程状态。人工确认仍保留，但作为异常兜底，不作为正常路径。

## 目标

- 用户视角只看到一个 ETC 业务批次，不再看到两个并列批次。
- 同一个对账任务只能有一个 active ETC 业务批次。
- 同一个业务批次允许多次补充 ZIP 导入，补充导入合并到同一业务批次。
- 创建 OA 草稿后，页面不再要求用户立即选择“已提交/未提交”。
- app 后台持续检测 OA 是否从草稿进入 `流程状态：进行中`，用户可关闭页面或继续其他操作。
- OA 检测成功后，系统自动把 ETC 批次推进为已提交。
- 普通用户仍可在异常状态下人工标记“已提交 OA”或“未提交 OA”，但必须写审计。
- 删除、撤销、迁移和错误处理以业务批次为边界，同时保留技术子资源审计。

## 非目标

- 不删除 OA 源系统数据。
- 不保存用户 `Admin-Token` 做长期后台轮询。
- 不直接废弃 `EtcImportBatch` 或 `EtcBatch` 的技术职责。
- 不把 ETC 对账重做成通用异常处理入口。
- 不在第一阶段强制迁移到新数据库表结构；当前可先在现有 state 结构上新增聚合与迁移逻辑。

## 推荐方案

采用“统一业务批次 + 技术子资源 + OA Mongo 自动检测 + 人工兜底”的方案。

新增用户可见聚合：`EtcBusinessBatch`。它是 ETC 页面、权限、状态、删除、审计和自动检测的主对象。`EtcImportBatch` 和 `EtcBatch` 仍作为技术子资源存在，分别负责导入来源和 OA 提交容器。

备选方案比较：

- 只做前端隐藏重复批次：实现快，但根因仍在，删除、审计、迁移和状态一致性继续复杂。
- 直接废掉 `EtcImportBatch`：看起来简单，但会破坏导入来源追溯、补充导入、附件清理、canonical invoice 同步和防误删保护。
- 推荐方案：改造范围较大，但边界清楚，能支撑生产级状态机、后台恢复和历史迁移。

## 业务批次模型

`EtcBusinessBatch` 建议字段：

```text
business_batch_id
task_id
status
version
owner_user_id
owner_org_id
import_batch_ids
submission_batch_id
external_etc_batch_id
oa_draft_id
oa_draft_url
oa_row_id
oa_process_status
oa_detection_status
oa_detection_started_at
oa_detection_next_run_at
oa_detection_deadline_at
oa_detection_final_retry_until
oa_detection_attempts
oa_detection_error
oa_detection_reason
invoice_ids
import_attempts
audit_events
created_at
updated_at
```

字段语义：

- `business_batch_id`：用户可见主 ID，例如 `etc_business_batch_0001`。
- `task_id`：关联 ETC 对账任务。
- `version`：乐观锁版本，所有高风险写接口必须带 `expectedVersion`。
- `owner_user_id` / `owner_org_id`：权限边界，普通用户只能操作自己或所属组织可访问批次。
- `import_batch_ids`：一个业务批次可包含多个 ZIP 导入技术批次。
- `submission_batch_id`：现有 `EtcBatch.id`，用于 OA 草稿/提交技术子批次。
- `external_etc_batch_id`：写入 OA 的业务号，例如 `etc_20260519_001`。
- `oa_row_id`：检测到 OA 进入流程后回写的 app 侧 OA row id。
- `invoice_ids`：业务批次当前有效 ETC 发票集合。
- `import_attempts`：每次 ZIP 预览/确认/补充导入记录。
- `audit_events`：统一审计，必须包含业务批次 ID 和技术子批次 ID。

事实源规则：

- `EtcBusinessBatch` 是用户可见状态和操作边界的事实源。
- `EtcInvoice.current_batch_id` 仍是发票占用事实源，用于防止同一张发票被两个 active 业务批次占用。
- `EtcBusinessBatch.invoice_ids` 是可重建 read model。写操作必须同步更新它，但发现不一致时以 `EtcInvoice.current_batch_id + import_batch_ids + submission_batch_id` 重建，并写 `business_batch_invariant_repaired` 审计。
- `EtcImportBatch` 是来源事实源，保留每次 ZIP 文件、解析结果和附件补齐记录。
- `EtcBatch` 是 OA 草稿/提交技术容器事实源，保留 OA draft id、OA URL 和历史提交字段。

## 状态机

主流程：

```text
draft
  -> reviewing
  -> ready_for_import
  -> importing
  -> imported
  -> oa_draft_creating
  -> oa_submission_detecting
  -> oa_submitted
  -> closed
```

异常状态：

```text
import_failed
import_partial_failed
oa_draft_failed
not_submitted
oa_detection_timeout
oa_detection_conflict
oa_detection_unavailable
manually_marked_submitted
manually_marked_not_submitted
migration_conflict
business_batch_invariant_broken
deleted
superseded
```

关键规则：

- 一个对账任务只能有一个 active 业务批次。
- 一个业务批次可以包含多次补充导入，不创建第二个用户可见批次。
- `oa_draft_created` 不是稳定状态，只作为审计事件和短暂内部事件；创建成功后立即进入 `oa_submission_detecting`。
- 创建 OA 草稿必须幂等：已有 active 草稿时返回已有草稿，不新建第二个 `submission_batch_id`。
- 已自动或人工确认提交后，不允许物理删除，只允许按受控流程撤回或更正。
- 技术子资源允许保留多个历史版本，但 UI 默认只展示当前 active 业务批次和导入记录。

active 状态：

```text
draft
reviewing
ready_for_import
importing
imported
import_failed
import_partial_failed
oa_draft_creating
oa_draft_failed
oa_submission_detecting
oa_detection_timeout
oa_detection_conflict
oa_detection_unavailable
not_submitted
manually_marked_not_submitted
migration_conflict
business_batch_invariant_broken
```

非 active 状态：

```text
oa_submitted
manually_marked_submitted
closed
deleted
superseded
```

唯一性约束：

- 创建或绑定业务批次时，必须使用存储层原子约束保证同一 `task_id` 只有一个 active 批次，不能只依赖前端或进程内检查。
- 生产环境使用 app MongoDB detailed collections 时，新增 `etc_business_batches` 集合，并建立唯一约束：`unique(task_id, active=true)`。如果 Mongo 版本不支持 partial unique index，则使用 `task_active_key = "{task_id}:active"` 字段建立唯一索引，非 active 批次清空该字段。
- 写入 active 批次必须用 Mongo session transaction 或条件更新：同一事务内检查 task active key、创建/更新业务批次、更新发票占用和审计。未启用事务的部署必须通过部署检查阻断该功能上线。
- 本地开发的 state 文件模式只允许单进程使用，启动时必须声明 `FINOPS_STORAGE_MODE=local_state`，且不能作为生产部署方案。
- 发现多个 active 批次时，全部置为 `migration_conflict`，禁止继续导入、创建 OA 草稿或提交，直到人工合并或关闭冲突。
- 所有写接口以 `version` 做乐观锁，后台检测与人工兜底并发时，先提交成功的一方推进状态，另一方收到 `409 version_conflict` 后重新读取。

允许操作矩阵：

| 状态 | 补充导入 | 创建/打开 OA 草稿 | 刷新检测 | 撤销草稿/释放发票 | 物理删除 | 人工兜底 |
| --- | --- | --- | --- | --- | --- | --- |
| `draft` / `reviewing` / `ready_for_import` / `imported` | 允许 | `imported` 后允许 | 禁止 | 禁止 | 允许 | 禁止 |
| `importing` | 禁止并发导入 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |
| `import_failed` / `import_partial_failed` | 允许重试或补充 | 禁止，直到导入状态恢复 | 禁止 | 禁止 | 允许 | 禁止 |
| `oa_draft_creating` | 禁止 | 幂等返回进行中 | 禁止 | 禁止 | 禁止 | 禁止 |
| `oa_draft_failed` | 允许，因未生成有效草稿 | 允许重试 | 禁止 | 禁止 | 允许 | 禁止 |
| `oa_submission_detecting` / `oa_detection_unavailable` / `oa_detection_timeout` / `oa_detection_conflict` | 禁止，必须先撤销草稿/释放发票 | 返回已有草稿 | 允许 | 允许 | 禁止 | 异常状态允许 |
| `not_submitted` / `manually_marked_not_submitted` | 允许 | 允许重建新草稿 | 禁止 | 已释放则禁止重复释放 | 允许 | 禁止 |
| `oa_submitted` / `manually_marked_submitted` / `closed` | 禁止 | 禁止新建 | 只读刷新 | 禁止 | 禁止 | 禁止或管理员更正 |
| `migration_conflict` / `business_batch_invariant_broken` | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 管理员修复 |

## 补充导入规则

同一个 ETC 业务批次允许多次补充导入 ZIP。

每次补充导入记录为一次 `importAttempt`：

```text
businessBatchId = etc_business_batch_0001
  importAttempts:
    - attempt 1: 首次导入，35 张
    - attempt 2: 补充导入，2 张
    - attempt 3: 补齐附件，0 张新增，2 张附件补齐
```

合并规则：

- 新发票进入同一 `businessBatch.invoice_ids`。
- 重复发票不重复创建。
- 缺 PDF/XML 的重复发票可补齐附件，并记录 `attachment_completed`。
- 不属于该对账任务 allowlist 的发票不得进入业务批次，预览中显示过滤原因。
- 导入部分失败时，业务批次进入 `import_partial_failed` 或保持可重试状态，不能静默成功。

真正禁止的是同一对账任务并存多个 active 业务批次，不是禁止多次导入 ZIP。

补充导入边界：

- 允许补充导入的前提是尚未创建有效 OA 草稿，状态必须在 `draft`、`reviewing`、`ready_for_import`、`imported`、`import_failed`、`import_partial_failed`、`oa_draft_failed`、`not_submitted` 或 `manually_marked_not_submitted`。
- 进入 `oa_submission_detecting` 后，OA 草稿金额、附件和明细已经固化，本地不得再直接补充导入。
- 如果创建草稿后发现 ETC 导入不足，用户必须先执行“撤销草稿/释放发票”。app 不删除 OA 源系统草稿，只把本地业务批次从该草稿解绑、释放发票占用、记录旧 `submission_batch_id` 为历史，再回到 `not_submitted`。之后可以补充导入并重新创建新的 OA 草稿。
- 进入 `oa_submitted`、`manually_marked_submitted` 或 `closed` 后，不允许向同一业务批次补充导入。漏导发票只能创建更正/追加业务批次，或按财务已有规则生成补充凭证。
- 任何导致金额、发票数、附件集合变化的导入都必须在创建 OA 草稿前完成，否则拒绝并返回 `422 oa_draft_already_exists`。

## OA 自动检测

创建 OA 草稿成功后，正常流程不再弹出“我已提交 OA / 未提交 OA”选择。后端立即持久化业务批次状态：

```text
status = oa_submission_detecting
oa_draft_id = ...
oa_draft_url = ...
oa_detection_started_at = now
oa_detection_next_run_at = now + interval
oa_detection_deadline_at = now + 30 minutes
oa_detection_final_retry_until = now + 24 hours
oa_detection_attempts = 0
```

检测依据：

- 不保存用户 `Admin-Token` 做长期轮询。
- 使用 OA Mongo 只读适配器查询，优先复用现有 `MongoOAAdapter` 的支付申请读取能力。
- 查询限定 OA 支付申请表单，当前 form id 为 `2`。
- 查询条件以 `business_batch_id` 和 `external_etc_batch_id` 为稳定幂等标记。
- OA 源系统流程状态必须在适配器层归一化。canonical `in_progress` 的输入兼容值包括数字 `1`、字符串 `"1"` 和展示值 `进行中`；业务服务只判断 canonical status，不直接散写字面值比较。

创建 OA 草稿时，继续在 OA 表单内容中写入稳定标记：

```text
ETC批量提交
etc_batch_id=etc_20260519_001
business_batch_id=etc_business_batch_0001
```

检测合同：

- 候选来源：OA Mongo 表单数据集合，路径以现有 OA 只读适配器实际配置为准；实现前必须在适配器层集中定义 collection、form id、字段路径和 projection，不允许页面或业务服务散写 Mongo 查询。
- 必须限定：form id、业务标记、创建时间窗口、申请人或组织边界、金额、发票数量。
- 时间窗口：`oa_draft_created_at - 1 day` 到 `oa_detection_deadline_at + 1 day`，人工刷新也不能无界扫描历史数据。
- 金额校验：OA 申请金额必须等于业务批次 `invoiceSummary.amount`，金额按分或 Decimal 精确比较，不使用浮点。
- 数量校验：OA 备注或明细中的 ETC 发票数量必须等于业务批次发票数量；如果 OA 源字段缺失，进入 `oa_detection_conflict`，不得自动提交。
- 组织边界：候选 OA 的申请人、创建人或所属组织必须与业务批次 `owner_user_id` / `owner_org_id` 匹配；无法确认时进入 `oa_detection_conflict`。
- 附件校验：能读取附件列表时，至少校验草稿附件包含本批次生成的 ETC 附件包或稳定文件名；不能读取附件时写 `attachment_check_skipped` 审计，不作为自动失败条件。
- 索引要求：OA Mongo 侧应具备 form id、processStatus、createdAt 的索引；业务标记如只能存在备注文本内，先通过 form id + createdAt + processStatus 缩小范围后做文本匹配，不能全表扫描。
- `oa_marker_missing` 是 `oa_detection_reason`，不是业务批次 `status`。它表示 OA Mongo 可用但在窗口内找不到业务标记，业务批次继续保持 `oa_submission_detecting`，直到成功、conflict、unavailable 或 deadline 后进入 `oa_detection_timeout`。
- `oa_detection_unavailable` 表示 Mongo 不可用、权限失败或查询超时；`oa_detection_timeout` 表示持续检测超过截止时间仍无可接受候选。

检测逻辑：

1. 查询支付申请表单。
2. 按 `business_batch_id` 精确匹配候选；如果旧草稿没有该字段，再按 `external_etc_batch_id` 匹配。
3. 过滤 form id、时间窗口、金额、数量、组织边界和附件标记。
4. 只接受唯一候选。
5. 候选必须由 OA 适配器归一化为 canonical `in_progress`。
6. 检测成功后写回 `oa_row_id`、`oa_process_status` 和检测时间。
7. 推进业务批次到 `oa_submitted`。
8. ETC 发票置为 `submitted`。
9. 对账任务置为 closed。
10. 同步该 OA row 到 app 工作台/read model。
11. 写审计事件 `oa_submission_detected`。

多候选处理：

- 多条候选全部进入 `oa_detection_conflict`，后端保存最多 10 条候选摘要：`oaRowId`、申请人、组织、金额、发票数量、创建时间、processStatus、匹配命中的 marker。
- 前端只展示摘要供用户选择，选择后后端仍必须重新校验 form id、金额、数量、组织边界和状态。
- 任何候选校验失败都不能直接被普通用户强制通过；普通用户可选择 `manual_without_oa_row`，但必须填写原因并进入高风险审计。

检测策略建议配置化：

```text
前 5 分钟：每 15 秒检测一次
5-30 分钟：每 60 秒检测一次
30 分钟后：进入 oa_detection_timeout
timeout 后 24 小时内：只响应用户手动刷新，不再自动高频扫描
```

后端重启后必须扫描仍处于以下状态的业务批次并恢复检测：

```text
oa_submission_detecting
oa_detection_unavailable
```

`刷新检测` 只是触发一次即时检测，不能重复创建多个检测任务。

后台任务要求：

- 检测任务必须以 `businessBatchId` 作为幂等键，同一批次任意时刻只能有一个运行中检测。
- 服务重启后只自动扫描 `oa_submission_detecting` 和 `oa_detection_unavailable`，按 `oa_detection_next_run_at` 恢复。
- `oa_detection_timeout` 不再自动轮询；用户点击 `刷新检测` 时，如果未超过 `oa_detection_final_retry_until`，可触发一次即时检测。超过该时间后只允许人工兜底或撤销草稿/释放发票。
- 每次检测要设置 Mongo 查询超时，超时进入 `oa_detection_unavailable` 并写 `oa_detection_error`。
- 后台检测推进状态时同样校验 `version`，避免覆盖用户刚刚执行的人工兜底。

## 人工兜底

用户确认采用 B 口径：

- 普通用户有权限点击“已提交 OA / 未提交 OA”。
- 正常流程不展示这个选择，由 app 自动判断。
- 只有异常状态下才显示人工兜底入口。

显示人工入口的状态：

```text
oa_detection_timeout
oa_detection_conflict
oa_detection_unavailable
```

人工“我已提交 OA”规则：

- 必须填写原因。
- 如果能找到候选 OA，用户应选择候选 OA。
- 后端校验批次仍未提交。
- 如提供 OA row id，后端检查 row 存在、表单类型、金额、ETC 标记和流程状态。
- 如果没有 OA row id，也允许，但来源标记为 `manual_without_oa_row`。
- 普通用户只能处理自己或所属组织可访问批次；跨组织批次、`migration_conflict` 和 `business_batch_invariant_broken` 只能由管理员处理。
- 写审计：actor、reason、before_status、after_status、candidate_oa_row_id、technical child ids。

人工“未提交 OA”规则：

- 必须写审计。
- 释放 ETC 发票 `current_batch_id`。
- 发票状态回到 `unsubmitted`。
- 业务批次进入 `not_submitted` 或 `manually_marked_not_submitted`。
- 旧 `submission_batch_id` 标记为 inactive 历史草稿，并从当前业务批次 active 草稿字段解绑。
- 保留草稿创建历史，不删除审计。

主动“撤销草稿/释放发票”规则：

- 适用于用户发现 OA 草稿创建后本地 ETC 发票导入不足、金额错误或不准备提交的正常路径。
- 前置状态：`oa_submission_detecting`、`oa_detection_timeout`、`oa_detection_conflict`、`oa_detection_unavailable`。
- 后端必须先执行一次即时 OA 检测；如果检测到 OA 已为 canonical `in_progress`，拒绝撤销并推进为 `oa_submitted`。
- 未检测到已提交时，释放 ETC 发票 `current_batch_id`，发票状态回到 `unsubmitted`，当前 `submission_batch_id` 标记为 inactive 历史草稿，清空 active `oa_draft_id` / `oa_draft_url` / `submission_batch_id`，业务批次进入 `not_submitted`。
- app 不删除 OA 源系统草稿，页面必须提示用户旧 OA 草稿已从本地释放，不能继续提交旧草稿；重建草稿会生成新的 `submission_batch_id` 和 OA 草稿。
- 操作必须幂等，重复调用返回当前 `not_submitted` 状态和第一次释放的审计事件。

审计字段：

```text
event_id
event_type
actor_user_id
actor_role
actor_org_id
source = api | background-detector | migration
request_id
ip
user_agent
business_batch_id
task_id
import_batch_ids
submission_batch_id
external_etc_batch_id
oa_row_id
before_status
after_status
expected_version
actual_version
reason
created_at
```

## 页面交互

页面用户视角只展示 `ETC业务批次`。

建议结构：

```text
左侧：ETC业务批次列表
右侧上方：业务批次状态与操作
右侧中部：对账任务文件、信用卡项、票根网项、匹配结果
右侧下方：已导入 ETC 发票、OA 草稿/流程状态、导入记录、审计记录
```

核心交互：

- 新建对账任务时创建或绑定一个业务批次。
- ZIP 导入结果合并到当前业务批次。
- 补充 ZIP 导入展示为导入记录，不创建新用户可见批次。
- 点击“创建并打开 OA 草稿”后打开 OA 页面，同时业务批次进入 `oa_submission_detecting`。
- 用户可以关闭页面、刷新浏览器或继续其他操作，后台检测继续运行。
- 页面重新打开时从后端读取业务批次状态。
- 检测成功后自动显示 `OA 已提交：进行中`，并进入已提交区。
- 检测异常后显示人工兜底按钮。

自动检测中显示：

```text
OA 草稿已创建，等待 OA 系统确认提交。
```

操作按钮：

- 打开 OA 草稿。
- 刷新检测。
- 撤销草稿/释放发票。
- 异常处理。

按钮状态：

- `打开 OA 草稿`：只在存在 `oaDraftUrl` 时显示。
- `刷新检测`：只在检测相关状态显示；点击后立即返回最新业务批次状态和一次检测结果。
- `撤销草稿/释放发票`：只在草稿已创建但尚未提交状态显示；用户确认后进入 `not_submitted`，允许继续补充导入和重建草稿。
- `异常处理`：只在 timeout/conflict/unavailable 显示，展开人工“已提交 OA / 未提交 OA”入口。

## API 合同

新增业务批次 API：

```text
GET    /api/etc/business-batches
GET    /api/etc/business-batches/{businessBatchId}
POST   /api/etc/business-batches
POST   /api/etc/business-batches/{businessBatchId}/source-files
POST   /api/etc/business-batches/{businessBatchId}/etc-import/preview
POST   /api/etc/business-batches/{businessBatchId}/etc-import/confirm
POST   /api/etc/business-batches/{businessBatchId}/oa-draft
POST   /api/etc/business-batches/{businessBatchId}/oa-draft/revoke
POST   /api/etc/business-batches/{businessBatchId}/oa-status/refresh
POST   /api/etc/business-batches/{businessBatchId}/manual-oa-status
DELETE /api/etc/business-batches/{businessBatchId}
```

旧 API 过渡期保留：

- `/api/etc/reconciliation-tasks`
- `/api/etc/import/preview`
- `/api/etc/import/confirm`
- `/api/etc/batches`
- `/api/etc/batches/{id}/draft`
- `/api/etc/batches/{id}/confirm-submitted`
- `/api/etc/batches/{id}/mark-not-submitted`

前端新页面应逐步切到 `business-batches`。旧 API 可以包装到新服务，避免一次性破坏历史流程和测试。

统一响应 envelope：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "requestId": "req_..."
}
```

错误响应：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "version_conflict",
    "message": "批次状态已变化，请刷新后重试。",
    "details": {
      "businessBatchId": "etc_business_batch_0001",
      "expectedVersion": 3,
      "actualVersion": 4
    }
  },
  "requestId": "req_..."
}
```

核心写接口合同：

| 接口 | 请求关键字段 | 前置状态 | 幂等条件 | 成功后置状态 |
| --- | --- | --- | --- | --- |
| `POST /business-batches` | `taskId`, `idempotencyKey` | 任务存在且无 active 批次 | `taskId + idempotencyKey` | `draft` |
| `POST /etc-import/preview` | `files`, `expectedVersion` | 允许补充导入状态 | 文件 hash 相同返回同一预览 | 状态不变 |
| `POST /etc-import/confirm` | `previewId`, `expectedVersion`, `idempotencyKey` | 允许补充导入状态 | `previewId + idempotencyKey` | `imported` / `import_partial_failed` |
| `POST /oa-draft` | `expectedVersion`, `idempotencyKey` | `imported` 且发票数大于 0 | 已有 active 草稿返回同一草稿 | `oa_submission_detecting` |
| `POST /oa-draft/revoke` | `expectedVersion`, `reason`, `idempotencyKey` | 草稿已创建但未提交 | `businessBatchId + idempotencyKey` | `not_submitted` |
| `POST /oa-status/refresh` | `expectedVersion` | 检测相关状态 | 同一时刻只运行一次检测 | 最新检测状态 |
| `POST /manual-oa-status` | `decision`, `reason`, `candidateOaRowId`, `expectedVersion` | timeout/conflict/unavailable | `businessBatchId + decision + expectedVersion` | `manually_marked_submitted` 或 `manually_marked_not_submitted` |
| `DELETE /business-batches/{id}` | `expectedVersion`, `reason` | 仅未生成有效 OA 草稿或 `not_submitted` | 重复删除返回 deleted | `deleted` |

`manual-oa-status` 请求示例：

```json
{
  "decision": "submitted",
  "candidateOaRowId": "oa-pay-682b...",
  "reason": "OA 已进入流程，自动检测超时后人工确认。",
  "expectedVersion": 7
}
```

`oa-draft/revoke` 请求示例：

```json
{
  "reason": "发现 ETC 导入缺少 516HJ 4 月发票，撤销本地草稿后补充导入。",
  "idempotencyKey": "revoke-etc-business-batch-0001-20260519",
  "expectedVersion": 8
}
```

错误码：

- `403 forbidden_scope`：用户无权访问该批次。
- `404 business_batch_not_found`：批次不存在。
- `409 version_conflict`：乐观锁冲突。
- `409 active_business_batch_exists`：同一任务已存在 active 批次。
- `409 operation_in_progress`：已有导入、建草稿或检测任务运行中。
- `422 invalid_status_transition`：当前状态不允许该操作。
- `422 oa_draft_already_exists`：已有草稿，不能补充导入。
- `422 oa_already_submitted`：撤销前即时检测发现 OA 已进入流程。
- `422 oa_candidate_invalid`：人工选择的 OA 候选未通过后端校验。
- `503 oa_detection_unavailable`：OA 只读查询不可用。

权限矩阵：

| 接口 | 最小权限 | 作用域 |
| --- | --- | --- |
| `GET /business-batches*` | `finops:app:view` | 只能读取自己或所属组织可见批次；`finops:app:admin` 可跨组织 |
| `POST /business-batches` | `finops:app:operate` | 只能为自己或所属组织任务创建 |
| `POST /etc-import/*` | `finops:app:operate` | 只能操作自己或所属组织 active 批次 |
| `POST /oa-draft` | `finops:app:operate` | 只能操作自己或所属组织 active 批次 |
| `POST /oa-draft/revoke` | `finops:app:operate` | 只能撤销自己或所属组织 active 批次；已提交后只能管理员走更正流程 |
| `POST /oa-status/refresh` | `finops:app:view` | 可触发一次只读检测，但状态推进由后台服务按批次权限和版本校验执行 |
| `POST /manual-oa-status` | `finops:app:operate` | 普通用户限自己或所属组织；无 OA row 的高风险提交需额外审计；跨组织只允许 `finops:app:admin` |
| `DELETE /business-batches/{id}` | `finops:app:operate` | 普通用户限未提交且自己或所属组织；冲突/不变量损坏只允许 `finops:app:admin` |

只拥有 `finops:app:view` 或导出权限的用户不得调用任何写接口。所有 403 都返回 JSON；高风险写接口的 403 也写安全审计，普通读取 403 只写访问日志。

业务批次详情返回示例：

```json
{
  "businessBatchId": "etc_business_batch_0001",
  "taskId": "ETC-RECON-000020",
  "status": "oa_submission_detecting",
  "version": 7,
  "importBatchIds": ["etc_import_batch_0004", "etc_import_batch_0005"],
  "submissionBatchId": "etc_batch_0027",
  "externalEtcBatchId": "etc_20260519_001",
  "oaDraftId": "682b...",
  "oaDraftUrl": "https://www.yn-sourcing.com/oa/#/normal/forms/form/2?formId=2&id=682b...",
  "oaRowId": null,
  "oaProcessStatus": "unknown",
  "invoiceSummary": {
    "count": 37,
    "amount": "1673.30"
  },
  "importAttempts": [],
  "auditEvents": []
}
```

## 数据迁移

迁移或启动修复要从现有关系反推业务批次：

```text
EtcReconciliationTask.task_id
EtcReconciliationTask.import_batch_id
EtcReconciliationTask.oa_draft_batch_id
EtcReconciliationTask.etc_batch_id
EtcImportBatch.submission_batch_id
EtcInvoice.import_batch_id
EtcInvoice.current_batch_id
EtcBatch.id
EtcBatch.etc_batch_id
```

规则：

- 任务已有 `import_batch_id` 时，创建或绑定业务批次。
- import batch 已有 `submission_batch_id` 时，把对应 `EtcBatch` 绑定到同一业务批次。
- 任务已有 `oa_draft_batch_id` 时，以它绑定 `EtcBatch.id`。
- 任务只有 `etc_batch_id` 时，通过 `EtcBatch.etc_batch_id` 反查。
- 多个 active submission batch 关联同一任务时，标记 `migration_conflict`，不自动合并。
- 批次引用发票缺失时，保留业务批次并记录 `stale_reference_repaired`。
- 迁移第一阶段只新增业务聚合和兼容视图，不删除原技术子批次。

迁移执行要求：

- 必须先支持 `--dry-run`，输出将创建、绑定、冲突、修复、跳过的数量和明细文件。
- 正式迁移必须幂等。`business_batch_id` 使用确定性映射：优先 `task_id` 映射到固定业务批次；无任务的孤儿批次使用 `submission_batch_id` 映射。
- 重复运行不得创建第二个业务批次，不得重复追加同一 `import_batch_id`。
- 迁移前后校验数量：任务数、import batch 数、submission batch 数、invoice 数、`current_batch_id` 占用数、submitted 发票数。
- 迁移发现 active 冲突时只标记 `migration_conflict`，不自动选择 winner。
- 迁移前必须备份当前 state 文件或数据库快照。
- 回滚策略是关闭 `business-batches` 读写开关并恢复备份；第一阶段不删除技术子批次，因此旧 API 仍可读取原数据。
- 迁移报告进入 `docs/operations/` 或部署日志，不写入业务主文档。

删除和撤销策略：

- 未创建有效 OA 草稿前，允许物理删除业务批次，同时清理对应未提交 `EtcImportBatch`、未提交发票占用和可重建 canonical invoice。
- `not_submitted` / `manually_marked_not_submitted` 可物理删除本地业务批次，但必须保留旧草稿审计；不删除 OA 源系统草稿。
- `oa_submission_detecting` 及检测异常状态不允许物理删除，只允许“撤销草稿/释放发票”先进入 `not_submitted`。
- `oa_submitted`、`manually_marked_submitted`、`closed` 禁止物理删除；后续只能走撤回、更正或追加批次流程。
- canonical invoice 对已提交状态必须保留；对未提交删除只释放占用或删除本批次创建且无其他引用的本地记录。

## 错误处理

错误状态必须结构化：

```text
oa_detection_timeout
oa_detection_conflict
oa_detection_unavailable
oa_draft_failed
import_partial_failed
business_batch_invariant_broken
```

`oa_marker_missing`、`oa_amount_mismatch`、`oa_invoice_count_missing`、`oa_org_unverified` 是 `oa_detection_reason`，不作为业务批次 `status`。只有 timeout、conflict、unavailable 进入可见异常状态。

所有 API 必须返回 JSON，不允许把 HTML 502 暴露给业务页面。后端日志要带：

```text
requestId
businessBatchId
taskId
externalEtcBatchId
oaRowId
operation
```

`/api/` 入口要有统一异常边界：

- 已知业务异常返回 4xx/503 和结构化错误码。
- 未知异常返回 500 JSON，包含 `requestId`，不泄露堆栈给前端。
- 后端日志保留堆栈和结构化上下文。

## 验收标准

后端：

- 对账任务创建后只有一个 active business batch。
- 首次 ZIP 导入和补充 ZIP 导入都合并到同一 business batch。
- 重复发票不重复创建，只记录 duplicate/attachment_completed。
- 不属于对账任务 allowlist 的发票不能进入 business batch。
- 创建 OA 草稿幂等，重复调用不创建第二个 submission batch。
- OA Mongo 检测到唯一 canonical `in_progress` 后自动推进到 `oa_submitted`。
- 查不到时保持 detecting，超时后进入 timeout。
- 多条候选进入 conflict，不自动确认。
- OA Mongo 异常进入 unavailable，可重试。
- 人工确认已提交必须写原因和审计。
- 人工未提交释放发票占用。
- 撤销草稿/释放发票 API 幂等，撤销前必须即时检测并防止已提交批次被释放。
- 删除业务批次只允许在未提交/已释放状态清理技术子批次和未提交 canonical invoice。
- 已创建 OA 草稿后补充导入必须被拒绝，撤销草稿/释放发票后才能补充。
- 已提交或 closed 批次禁止物理删除和补充导入。
- 历史数据迁移能归并 import batch + submission batch。
- 脏引用不会导致 502。

前端：

- 页面只显示一个业务批次。
- 补充导入后仍在同一业务批次详情中展示导入记录。
- 创建 OA 草稿后不弹出二选一确认。
- 用户刷新、离开、回来后状态从后端恢复。
- 检测成功后自动进入已提交区。
- timeout/conflict/unavailable 时才显示人工兜底按钮。
- 人工兜底要求原因。
- 删除/撤销确认文案明确影响范围。

部署：

- 后端重启后 pending OA 检测能恢复。
- app MongoDB detailed collections 必须具备 active 业务批次唯一索引或等价条件写入；未满足时功能开关不得打开。
- `/api/etc/business-batches` 不返回 HTML 错误。
- Nginx `/api/` 与 `/fin-ops-api/` 的 GET/POST/DELETE 都可用。
- 生产日志能按 `businessBatchId`、`requestId`、`oaRowId` 排查。
- 旧 `/api/etc/batches` 在过渡期兼容。

文档同步交付：

- 更新 `docs/product-specs/tax-offset-and-etc.md`：把“用户确认已提交 OA”调整为“OA 自动检测或异常人工兜底后进入已提交链路”。
- 更新 ETC 开发 API 文档：补充 `business-batches` API、状态枚举、错误码、权限和幂等规则。
- 更新 `docs/operations/`：补充迁移 dry-run、回滚、active 唯一索引检查、OA 检测后台任务和 Nginx/API smoke。
- 文档同步必须和代码变更同一批完成，避免产品事实源和实现口径冲突。

测试矩阵：

| 层级 | 必测场景 |
| --- | --- |
| 单元测试 | 状态转移、active 判定、补充导入允许状态、删除策略、OA 候选过滤、`processStatus` 数字/字符串/展示值归一化、审计字段 |
| 后端集成 | active 批次并发创建存储层竞态、重复点击创建草稿、重复确认导入、后台检测成功/timeout/conflict/unavailable、人工兜底与检测并发、撤销草稿幂等、撤销草稿后补充导入、只读用户写接口拒绝 |
| 迁移测试 | dry-run、正式迁移、重复运行、active 冲突、脏发票引用、唯一索引缺失阻断、回滚备份验证 |
| 前端 E2E | 页面只显示一个业务批次、补充导入记录合并、创建草稿后自动检测、刷新/离开/回来恢复状态、异常时人工入口 |
| 部署 smoke | 后端重启恢复检测、Nginx 不返回 HTML 502、OA Mongo 慢查询超时、旧 API 兼容读取、长期产品/API/operations 文档同步检查 |

## 实施拆分建议

后续实现建议拆成四个子任务：

1. 后端业务批次聚合与迁移：
   - 在 `backend/src/fin_ops_platform/services/etc_service.py` 附近实现 `EtcBusinessBatch` 聚合、状态机、Mongo 存储层 active 唯一、乐观锁、迁移/修复逻辑和兼容 API 服务层。
   - 不删除 `EtcImportBatch` / `EtcBatch`，只把它们收敛为技术子资源。
   - 写单元/集成测试覆盖补充导入、撤销草稿、删除策略、active 并发冲突、脏引用修复和旧 API 兼容。

2. OA 自动检测服务：
   - 基于现有 OA Mongo 只读适配器实现业务批次检测器，严格按 form id、marker、金额、数量、组织、时间窗口过滤候选，并统一归一化 `processStatus`。
   - 实现后台恢复、检测幂等、timeout/conflict/unavailable 状态、人工兜底校验和审计。
   - 写测试覆盖唯一候选、多候选、marker 缺失、Mongo 超时、服务重启恢复和人工并发。

3. 前端 ETC 页面改造：
   - 将 `web/src/pages/EtcTicketManagementPage.tsx` 切到 `business-batches` 模型，只显示一个用户可见业务批次。
   - 创建草稿后展示“OA 草稿已创建，等待 OA 系统确认提交”，提供打开草稿、刷新检测、撤销草稿/释放发票、异常处理。
   - 仅在异常状态展示人工“已提交 OA / 未提交 OA”，并要求填写原因。
   - 写前端测试或最小 E2E 覆盖刷新恢复、补充导入和异常入口。

4. 验证与部署：
   - 汇总并运行后端 unittest、前端 build/test、迁移 dry-run、Nginx API smoke。
   - 验证已有 delete 502 修复不回退，旧 `/api/etc/batches` 兼容。
   - 同步更新产品规格、开发 API 文档和 operations 文档。
   - 输出部署顺序、回滚方式和生产检查清单。
