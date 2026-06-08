# ETC票据管理 状态机


> 修改 `ETC票据管理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - `draft/imported`：ETC 发票已导入，业务批次仍在未提交链路。
  - `oa_draft_created`：OA 草稿已创建，等待用户人工确认。
  - `submitted_confirmed`：用户确认 OA 已提交，业务批次进入已提交口径，绑定的 ETC 对账任务同步闭环。
  - `not_submitted`：用户确认 OA 未提交，释放本地 ETC 发票占用并回到未提交链路。
- 状态事实源：`etc_business_batches` 业务批次、绑定的 ETC 对账任务状态、ETC 提交批次及审计事件。
- 允许流转：
  - 导入确认后创建或更新同一个业务批次，不在前端拆成“导入任务”和“对账任务”两个用户可见任务。
  - 创建 OA 草稿后只能由 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`。
  - `submitted` 成功后，关联台 open 区生成一条 `source_kind=etc_invoice_summary` 折叠汇总发票行，金额取业务批次上报金额，等待未来 OA 和银行流水进入后普通配对。
- 禁止流转：
  - ETC 页面不得提供自动 OA 检测、刷新检测或异常检测入口。
  - 批次已人工确认后，不得由 legacy OA 检测覆盖用户确认结果。
  - 关联台未找到 OA 和银行流水三项匹配前，`etc_invoice_summary` 不得直接进入已配对区。

## UI 状态

- loading：页面加载业务批次、导入/草稿/人工确认动作执行中时显示按钮级 loading，不展示后台英文状态码作为主文案。
- empty：未提交或已提交 tab 下无批次时只显示该 bucket 的空态；一个业务批次在前端只出现一次。
- error：导入、创建草稿、人工确认、删除失败时显示本地化业务错误；内部对象 id、文件 id、legacy 检测码不作为主要用户文案。
- stale/refreshing：ETC 页面本身不触发 OA 自动检测；关联台 read model 刷新状态由关联台页面展示。
- permission disabled/hidden：权限不足时隐藏或禁用创建、导入、草稿、人工确认、删除入口，不能让前端绕过后端状态校验。

## Read Model / Worker 状态

- ETC 业务批次列表直接读取业务批次事实源；关联台是否出现 `etc_invoice_summary` 由 Workbench SQL projection/read model 决定。
- `submitted` 人工确认会隐藏散落 ETC 发票，并让 Workbench open 区投影一条合并行；投影失败时不应把批次回滚成未提交。
- refresh 触发来源：ETC 导入确认、OA 草稿创建、人工提交确认、人工未提交确认、关联台普通配对关系确认或撤回。
- 失败恢复：优先重跑相关 read model refresh；业务批次、ETC 发票占用和审计事实不得从前端临时修补。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-08 | ETC 页面统一为单个业务批次链路；人工确认已提交后闭环对账任务并投影 `etc_invoice_summary` | ETC 批次、关联台 open 区、人工确认 API | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
