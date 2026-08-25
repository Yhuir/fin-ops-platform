# OA 集成状态机

> 修改 `oa-integration` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。

## 外部 OA / Mongo 状态

| 状态 | 含义 | 允许行为 | 禁止行为 |
| --- | --- | --- | --- |
| `available` | OA 用户信息、OA 登录、OA Mongo 或投影源可用 | session 校验、sync、查询、草稿创建 | 无 |
| `degraded` | 部分字段、附件或下游投影不可用 | 返回可解释 warning/status；允许只读旧投影但必须标明 stale/degraded | 把 degraded 数据标成 fresh |
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
| `allowed_read_export_only` | canonical Settings ACL tier 为 `read_export_only` | 查询、导出 | 写入按钮隐藏/禁用；API mutation `403 permission_denied` |
| `allowed_full_access` | canonical Settings ACL tier 为 `full_access` | 普通业务写入 | admin-only 设置仍禁用 |
| `allowed_admin` | canonical username 精确为固定 `YNSYLP005` | 账户、凭据、数据重置、App Health 高风险入口 | 仍需二次确认和密码复核 |
| `forbidden` | 非管理员缺席 canonical ACL，或 ACL provider fail closed | 无业务访问 | OA role/permission/menu 即使存在也不改变 denied；`/api/session/me` allowed false，业务 API 403 |
| `expired_or_unavailable` | token 过期、OA userInfo 超时/失败 | retry / 重新登录 OA | 前端 error/expired，不渲染业务页面 |

## OA Sync / Projection Worker 状态

| 状态 | 触发 | 允许流转 |
| --- | --- | --- |
| `queued` | 受控运维 CLI/timer 写 durable runtime event | `queued -> running` |
| `running` | worker 消费 `oa.sync` | `running -> succeeded`、`running -> failed` |
| `succeeded` | canonical OA 投影原子 upsert 完成并写 sync run | 页面下次 normal GET 读取新事实；不 fan-out 已退役页面 refresh |
| `failed` | 源 adapter、repository 或 queue 失败 | 记录失败 run，保留旧投影，等待 retry/backoff |
| `retention_pruned` | all scope sync 根据 cutoff 清理旧投影 | 旧月份下游 scope dirty，不能删除 manual import marker |

禁止：

- HTTP API 直接 inline 跑全量 sync。
- projection 半写入后标记 succeeded。
- worker 依赖 Flask/Application/session/header。
- RabbitMQ transport 被当作 read model 事实源。

### 精确附件刷新

| 状态 | 触发/合同 | 下一状态 |
| --- | --- | --- |
| `queued` | Settings mutation gate 校验 row IDs 为存在且 completed 的 canonical OA 后，登记 `oa.sync(operation=refresh_attachments)`；POST 返回 202/event id | `processing` |
| `processing` | OA worker 只对 event 中 row IDs 强制下载/解析附件，定向 upsert projection，复用统一 promotion 且 `ensure_matching=true` | `done`、`failed`、`dead_lettered` |
| `done` | durable `runtime_result` 含逐 row 附件/发票计数、promotion summary 与 affected scopes；前端此时才更新行 | 终态 |
| `failed` | 来源记录缺失、非完成态、附件/OCR/promotion 或持久化失败 | durable retry 或 `dead_lettered`；返回真实错误，不读取旧投影冒充成功 |
| `dead_lettered` | bounded retry 已用尽 | 终态，需人工处理 |

精确刷新不新增 worker/event type，不执行普通 all/month sync 的 stale deletion，也不允许 HTTP 进程持有 Mongo adapter、OCR 或 promoter。重复刷新必须保持 canonical 发票和来源边幂等，同时允许再次补发 matching reconciliation。

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

- preview hash stale 后继续创建 batch。
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
- error：OA session/OA login/Mongo/API structured error 必须可见，不吞掉。
- syncing：显式 OA sync job 运行时展示任务进度；精确附件刷新展示 queued/processing/done/failed，并在组件卸载或新刷新开始时取消旧轮询；业务页面不伪造 read-model refreshing。
- permission disabled/hidden：只读用户隐藏写入，full access 隐藏 admin-only，admin 才能维护 OA applicant credentials。

## Canonical Projection / Worker 状态

## ACL role sync 状态

| 状态 | 触发/行为 | 下一状态或结果 |
| --- | --- | --- |
| `not_called` | generic settings、ACL no-op、权限/DTO 失败 | 零 OA I/O |
| `target_validating` | 锁定唯一 `finops:app:view` menu、三个唯一专用 role 和 exact 三 binding | exact → `target_applied`；disabled/missing/drift/timeout → rollback + 502 |
| `target_applied` | 只替换三个专用 role members；业务 role/member、menu/binding 零写 | PostgreSQL ACL/audit commit |
| `committed` | Settings ACL 与 durable audit 原子提交 | success |
| `compensating` | target applied 后 PostgreSQL/audit 失败 | previous snapshot 最多恢复一次 |
| `compensated` | previous assignments read-back 成功 | persistence failure，未提交新 ACL |
| `inconsistent` | compensation、read-back 或 commit outcome 无法确认 | 503；停止自动继续并人工核对 DB/OA/session |

该同步是低频同步 I/O，不新增 outbox、worker、read model 或缓存。

## Deployment ACL 专项验收状态

| 状态 | 合同 |
| --- | --- |
| `not_requested` | 标准发布路径；任何 profile 都只读取 005，不读取 006 或 ACL artifact |
| `preflight_blocked` | 显式专项验收遇到 disabled/missing、wrong selector、menu/role/member/env/identity/fingerprint drift，或 artifact 不是 `eligible=true`；零写并终止专项验收，不改变标准激活状态 |
| `preflight_exact` | 显式专项验收证明 selector/menu/三 role/三 binding/members、strict env、0133/CHECK 与 005/006 identity 全部 steady-state exact |
| `maintenance` | 真正 ACL profile 激活后标准 runtime gate 失败；禁止启动旧 vulnerable binary，只能 forward repair |

fresh OA menu 验收只接受角色投影后的新 `/system/menu/getRouters` 或新 shell session；旧 DOM 不构成状态事实。

| 状态 | 含义 | 页面/API 要求 |
| --- | --- | --- |
| `queued` | 显式 `oa.sync` job 已入 durable queue | 返回 job 状态，不返回页面 read-model target |
| `running` | OA worker 正在读取外部源并构造 canonical batch | App Status 显示任务运行；业务页面继续读取上次已提交事实 |
| `succeeded` | completed/admission/payment-status/watermark 同批原子提交 | 页面下次 normal GET 直接读取 canonical PostgreSQL |
| `failed` | 任一启用 form、repository 或 queue 失败 | 整轮不提交部分 snapshot；记录 error/run，允许明确 retry |
| `unavailable` | OA/Mongo/PostgreSQL 依赖不可用 | structured error；不得伪造成功或回退历史页面 projection |

OA 手工导入/删除、进项 OA reverse、ETC OA 草稿和 settings 变更只提交各自 canonical
facts、audit 和必要领域任务。它们不触发已退役页面 read-model fan-out。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 首轮测试闭环补齐 OA 集成状态机 | session、OA sync、凭据、进项 OA 反提、ETC OA 草稿、read model 状态 | `PYTHONPATH=backend/src python3 -m unittest ... -v`、`cd web && npm test -- --run ...`、`bash scripts/verify.sh docs` |
| 2026-08-02 | 收敛 canonical ACL、fixed-menu 三角色 runtime projection 与 deployment exact cleanup/rollback | OA identity、APP authorization、菜单可见性和发布证据责任分离 | `tests.test_oa_role_sync_service`、`tests.test_settings_access_control_preflight`、`tests.test_deploy_oa_script`、`tests.test_permissions_write_entry_inventory` |
| 2026-08-03 | 一次性 cleanup/rollback 退出稳态发布，ACL gate 只接受 `eligible=true` | 普通发布不读取 006；OA topology drift 阻断且零写 | `tests.test_deploy_oa_script` |
| 2026-08-05 | 双身份验证退出标准激活前置条件 | 所有 profile 只读取 005；005/006 artifact 仅用于显式权限专项验收 | `tests.test_deploy_oa_script` |
