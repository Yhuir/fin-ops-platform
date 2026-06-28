# OA 集成状态机

> 修改 `oa-integration` 相关业务状态、UI 状态、projection 状态或 worker 状态前必须读取本文件。

## 外部 OA / Mongo 状态

| 状态 | 含义 | 允许行为 | 禁止行为 |
| --- | --- | --- | --- |
| `available` | OA 用户信息、OA 登录、OA Mongo 或投影源可用 | session 校验、sync、查询、草稿创建 | 无 |
| `degraded` | 部分字段、附件或下游投影不可用 | 返回可解释 warning/status；允许只读旧投影但必须标明 degraded/outdated | 把 degraded 数据标成可用新数据 |
| `unavailable` | OA userInfo、OA login 或 Mongo 连接失败 | 返回 401/403/502/structured error；App Status blocked/degraded | 伪造用户、创建草稿、刷新投影成功 |
| `backoff` | Mongo 短时间连续失败 | 跳过重复外部查询，保留 error read status | 高频重试压垮外部 OA/Mongo |

状态事实源：

- `OAIdentityService.resolve_identity(...)`
- `MongoOAAdapter.get_read_status()`
- `OAProjectionSyncService` sync run payload
- App Status / runtime monitoring registry

## Session / 权限状态

| 状态 | 触发 | 允许行为 | UI/API contract |
| --- | --- | --- | --- |
| `loading` | 前端启动请求 `/api/session/me` | 不渲染业务页面 | `SessionGate` loading |
| `allowed_read_export_only` | OA 有 `finops:app:view`，app tier 只读导出 | 查询、导出 | 写入按钮隐藏/禁用；API mutation `403 permission_denied` |
| `allowed_full_access` | app 全操作用户 | 普通业务写入 | admin-only 设置仍禁用 |
| `allowed_admin` | 管理员 | 账户、凭据、数据重置、App Health 高风险入口 | 仍需二次确认和密码复核 |
| `forbidden` | 无 OA 权限或不在 app allowed list | 无业务访问 | `/api/session/me` allowed false；业务 API 403 |
| `expired_or_unavailable` | token 过期、OA userInfo 超时/失败 | retry / 重新登录 OA | 前端 error/expired，不渲染业务页面 |

## OA Sync / Projection Worker 状态

| 状态 | 触发 | 允许流转 |
| --- | --- | --- |
| `queued` | `/api/integrations/oa/sync` 或 runtime event 入队 | `queued -> running` |
| `running` | worker 消费 `oa.sync` | `running -> succeeded`、`running -> failed` |
| `succeeded` | 投影 upsert 完成并写 sync run | 下游页面通过 direct API、operation projection、真实 outbox 或 cache warmup 收敛；不得恢复页面刷新队列。 |
| `failed` | 源 adapter、repository 或 queue 失败 | 记录失败 run，保留旧投影，等待 retry/backoff |
| `retention_pruned` | all scope sync 根据 cutoff 清理旧投影 | 旧月份下游 scope dirty，不能删除 manual import marker |

禁止：

- HTTP API 直接 inline 跑全量 sync。
- projection 半写入后标记 succeeded。
- worker 依赖 Flask/Application/session/header。
- RabbitMQ transport 被当作页面事实源。

## OA Applicant Credential 状态

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `unconfigured` | 未保存目标申请人凭据 | admin save -> `configured` |
| `configured` | 已保存 username/password secret | delete -> `unconfigured`；login success -> 可创建草稿 |
| `invalid` | OA 登录返回业务失败或账号锁定 | 保持 `configured`，返回 `target_oa_login_failed` |
| `expired_or_unavailable` | 网络、OA login 服务、RSA/openssl 配置失败 | 保持 `configured`，返回 `target_oa_login_failed` 或 `target_oa_login_unavailable` |

禁止：

- 非 admin 保存/list/delete 凭据。
- API、settings、audit、日志回显 password。
- 缺凭据时仍创建本地 OA reverse batch 或伪造草稿成功。

## 进项发票 OA 反提状态

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `draft` | 本地 batch 已创建，未创建 OA 草稿 | `create_oa_draft -> oa_draft_created` 或 `oa_draft_failed` |
| `oa_draft_created` | 已创建真实 OA draft，本地持有 draft id/url | `manual submitted -> submitted_confirmed`；`manual not_submitted -> not_submitted`；`revoke -> not_submitted` |
| `oa_draft_failed` | 创建草稿失败，可恢复 | 重新创建草稿 |
| `submitted_confirmed` | 用户确认 OA 已提交 | 进入 submitted history，隐藏内部 batch id/invoice ids |
| `not_submitted` | 用户确认未提交或本地撤销绑定 | 可重新 create draft |
| `oa_submission_detecting` | 历史自动检测状态 | `oa_detected` / `oa_detection_missing` / `oa_detection_unavailable` |
| `oa_detected` | 找到 OA 投影 evidence | 写 relation，一次性闭环 |
| `oa_detection_missing` | 未找到 evidence | 不写 relation |
| `oa_detection_conflict` | evidence 冲突 | 人工处理 |
| `oa_detection_unavailable` | 外部或投影不可用 | retry/backoff |

禁止：

- preview hash 过期后继续创建 batch。
- expected version mismatch 后写状态。
- idempotency key 重复导致重复草稿。
- submitted history 暴露内部 batch id 或 invoice ids。

## ETC OA 草稿 / 人工状态

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `imported` | ETC 业务批次已导入，可创建 OA 草稿 | `create_oa_draft -> oa_confirmation_pending` |
| `oa_confirmation_pending` | OA 草稿已创建，等待用户人工确认 | `manual submitted -> manually_marked_submitted`；`revoke/not submitted -> not_submitted` |
| `manually_marked_submitted` | 用户确认真实 OA 已提交 | 创建/保留 ETC summary 待关联台未来闭环 |
| `not_submitted` | 用户确认未提交或撤销本地绑定 | 释放本地 ETC 发票占用，可重新处理 |
| `deleted` | 删除本地业务批次 | 清本地事实和占用，不删除真实 OA 草稿/流程 |

禁止：

- 自动检测或刷新真实 OA 提交状态。
- 删除本地批次时删除/撤销真实 OA 草稿或 OA 流程。
- OA review URL 携带 draft id、conditions 或 auto edit 参数。

## UI 状态

- loading：session bootstrap、OA 待付款 rows/filter/detail、进项 OA reverse preview/draft、ETC business batch detail/action、settings credentials/manual search 加载中。
- empty：无 OA rows、无凭据、无手动导入记录、无可导入 OA 搜索结果。
- error：OA session/OA login/Mongo/OA sync/API structured error 必须可见，不吞掉。
- direct unavailable：OA sync 或下游 direct payload 暂不可用时，页面必须禁用高风险写入或提示后台刷新。
- permission disabled/hidden：只读用户隐藏写入，full access 隐藏 admin-only，admin 才能维护 OA applicant credentials。

## OA Projection / Worker 状态

| 状态 | 含义 | 页面/API 要求 |
| --- | --- | --- |
| `current` | OA projection/OA sync 状态与 source version 对齐 | 正常展示与允许满足前置条件的写入 |
| `missing` | OA projection 或 sync watermark 缺失 | 只作为后端诊断；页面 API 不返回旧刷新状态合同 |
| `syncing` | OA sync 或真实后台任务正在处理 | 页面按模块 loading/disabled 语义展示，不透出页面级同步字段 |
| `outdated` | source version 变化或真实后台任务未完成 | 不得返回看似 current 的空数据 |
| `failed` | worker/sync 失败 | App Status blocked/degraded，页面显示结构化错误或 outdated 诊断 |
| `unavailable` | repository/queue/外部系统不可用 | structured error，不能同步扫描替代 production projection |

触发来源：

- `oa.sync` worker 成功后下游 direct API / operation projection / cache warmup。
- OA 手动导入/删除 marker。
- 进项 OA reverse draft/revoke/manual status。
- ETC OA draft/manual status/delete。
- settings OA retention / role / credentials 变更按具体模块影响刷新。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 首轮测试闭环补齐 OA 集成状态机 | session、OA sync、凭据、进项 OA 反提、ETC OA 草稿、projection/worker 状态 | `PYTHONPATH=backend/src python3 -m unittest ... -v`、`cd web && npm test -- --run ...`、`bash scripts/verify.sh docs` |
