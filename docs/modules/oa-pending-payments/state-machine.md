# OA 待付款核对状态机

日期：2026-07-17

> 修改业务状态、UI 状态、read model、worker、Audit 或写回流程前必须读取本文件。页面不得自行推断付款状态或 freshness。

## 业务状态

| 状态域 | 状态 | PostgreSQL 页面事实源 | 允许流转 |
| --- | --- | --- | --- |
| OA 主行 | `completed` | `app.oa_applications` completed/legacy projection | OA sync 权威更新；不受 in-progress admission 限制 |
| OA 主行 | `in_progress` | `app.oa_pending_payment_admissions` | 仅由 OA sync 根据有效 `t_payment_simple.flow_id` + OA 当前 workflow replace/delete；完成后离开本状态 |
| 付款状态 | `unpaid` | fresh OA read model | 无 active linked 付款关系；候选、历史 candidate、金额字段本身不能驱动 paid |
| 付款状态 | `paid` | fresh OA read model | 存在 active linked relation；金额差异或非支出边仍阻断写回，但不制造第三种付款状态 |
| OA 外部写回 | `not_written` | payment-status snapshot `pay_status != 1` | 合法 `writeback-paid` 或金额匹配的 bank link 可进入 `written` |
| OA 外部写回 | `written` | payment-status snapshot `pay_status = 1` | 幂等终态；重复命令不重复写 MySQL，但仍可修复遗漏的 PG snapshot |
| in-progress relation | `active` | OA pending relation + bank claim | 创建后占用银行流水；OA 完成后 promotion |
| in-progress relation | `cancelled` | pending relation owner | admission 权威消失或显式撤销后释放 claim |
| in-progress relation | `promoted` | pending relation history + Workbench active relation | promotion 原子切换 owner；不能同时保留两个 active owner |

只有 `paid` / `unpaid` 两种 `paymentStatus`。金额、outflow、flow id 和 relation 完整性是写回前置条件，不是第三种 payment status。

## OA integration 状态

| 状态 | 行为 |
| --- | --- |
| 外部读取中 | 每个启用 form/scope 只读一次并构造双视图；不改变 PostgreSQL canonical snapshot，不删除旧记录 |
| 外部读取失败/部分 form 成功/schema 非法 | 整轮失败并记录 failed sync run；不得提交部分集合或把未知集合解释为删除 |
| 外部读取成功 | `projection_records` 遵守通用导入配置，`admission_records` 固定包含 completed + in-progress；合法 in-progress 草稿未填业务字段仍以稳定 identity 准入，空金额为 `NULL`；同一 PostgreSQL 事务提交 completed projection、admission、payment-status snapshot、source watermark 和 OA 精确月份 dirty/outbox |
| PostgreSQL commit 失败 | 全部回滚；上一次 snapshot 继续是页面可证明事实 |
| commit 成功且仅 admission/payment-status 变化 | `T0`；只刷新 OA 待付款精确月份，不触发 Workbench、成本统计或其它 shared consumers |
| commit 成功且 completed canonical 变化 | `T0`；刷新 OA 待付款，并由 sync service 通过既有 shared owner fan-out 合法 consumers |

Mongo/MySQL 变化尚未同步进 PostgreSQL 时属于 integration sync lag。页面和 read model worker 不允许直连外部系统掩盖该延迟。

in-progress 同步当前只保留原始/上下文化附件文件元数据，不解析附件证据、发票或 OCR。completed 保持现有附件处理。未来启用 OCR 必须新增独立版本、队列、回填、失败和 Audit 合同，不能静默改变本状态机。

## 写回状态机

### `writeback-paid`

1. 从 PostgreSQL projection 解析 OA 行并读取 active Workbench/pending relation。
2. 复核 outflow、支出合计等于 OA 金额、可解析 `flow_id`。
3. 幂等读取/写入 MySQL `t_payment_simple.pay_status=1`。
4. 无论 MySQL 本次新写还是此前已为 paid，都调用 PostgreSQL `record_paid_statuses(records=...)`。
5. PG writer 同事务更新 payment-status snapshot、月份 source watermark 和精确月份 dirty/outbox。
6. 若步骤 5 失败，返回 `oa_payment_status_snapshot_write_failed`；不声称页面已完成同步。命令可安全重试，下一次 OA sync 也会修复。
7. 前端收到成功后立即隐藏旧 rows，等待 operation barrier fresh，再读取新版本。

### `link-bank-transactions`

1. 只允许 in-progress OA 和 outflow bank transaction。
2. 创建 OA pending relation 与 bank claim，不写 Workbench active relation。
3. 金额相等且 flow id 合法时执行同一 MySQL + PG paid reconcile。
4. 关系 owner 和 payment snapshot writer分别对同一月份提交版本/outbox；queue dedupe 合并重复 wakeup。
5. 返回受影响 scope/barrier；前端等待 fresh 后重读。

不做跨 MySQL/PostgreSQL 的分布式事务。外部成功、PG 失败的唯一恢复合同是幂等重试或下一次 OA sync；禁止用 live read/fallback 猜测完成状态。

## UI 状态

| UI 状态 | 触发 | 页面行为 |
| --- | --- | --- |
| `loading` | 首次完整 rows 请求 | 显示骨架，不显示历史 snapshot |
| `ready` | `200` 且 fresh | 展示 rows、summary、filters，并保存当前 query 的 ETag |
| `checking` | 可见 tab 的 500ms 条件 GET | 保留当前 fresh rows；同一时刻最多一个请求 |
| `unchanged` | `304` | 不更新 rows，不执行完整聚合/渲染 |
| `refreshing` | `202` / dirty / source mismatch | 立即隐藏旧 rows，停止条件轮询，展示“新数据正在生成”，等待精确 barrier targets |
| `empty` | fresh `200` 且 total=0 | 真实空态；不得由 `202` 或错误推断 |
| `error` | 请求、barrier 或合同失败 | 不显示旧 rows；提供明确错误与重试 |
| `hidden` | document/tab 不可见 | 取消条件检查；恢复可见时立即检查一次 |
| `mutation_waiting` | 写命令成功 | 隐藏旧 rows，等待返回的 OA scope fresh 后完整重读 |

query、分页、排序、筛选、view mode、认证或 contract revision 变化时，取消旧请求并清除不匹配 ETag；晚到响应不得覆盖新 query。

## Read model / worker 状态

| 状态 | 判定 | API/worker 行为 |
| --- | --- | --- |
| `missing` | 月份 scope/source snapshot 不存在 | API `202` + enqueue；不返回 rows |
| `refreshing` | dirty/outbox pending/processing 或 source mismatch | API `202` + 精确 barrier targets；worker继续处理 |
| `fresh` | scope 存在、无 blocking dirty/outbox、expected=actual | API `200` 或条件 `304` |
| `superseded` | event source version 旧于 dirty scope | worker skip；不得读源、发布或清 dirty |
| `publish_lost_cas` | 构建期间出现更新版本 | 旧发布不清新 dirty；新 event继续处理 |
| `failed` | projector/publish/outbox处理失败 | retry/failed 可观测；API不得返回旧 rows |
| `unavailable` | repository/queue/worker依赖缺失 | fail closed，不启用 live fallback |

专属 `oa-pending-payment` worker 只 claim `oa_pending_payment.read_model.refresh`。`all` 是低优先级 fan-out control scope，只用于初始化和显式修复；普通业务 writer 只 enqueue 精确月份。

月份构建顺序：

1. CAS 检查 event source version 仍为当前版本。
2. 在 PostgreSQL 一致性事务中读取 completed OA、admission、payment status、canonical Workbench relation、pending relation，以及关系成员对应的 bank/invoice canonical facts；不等待其它页面 read model。
3. 批量构建 rows 与动态 source vector；不得 per-row I/O 或访问 Mongo/MySQL。
4. 原子发布月份 rows/scope/source vector。
5. 仅在 dirty 版本未前进时完成 event并清 dirty。

## HTTP 条件读取

- `200`：`ETag` 由 tenant、normalized query fingerprint、contract revision 和 read-model version token组成；响应使用 `Cache-Control: private, no-cache` 与 `Vary: Authorization, Cookie`。
- `304`：认证、query parsing 和小型 freshness/version gate 已通过，body 为空；禁止 rows count、sort、facet aggregation。
- `202`：不含旧 rows，返回 `read_model_status=refreshing` 和当前 tenant 的精确月份 `operationBarrierTargets`。
- 旧 `/api/oa-pending-payments/filter-options` 不存在；`filterConfig` / `filterOptions` 只随 `200 rows` 返回。

## Audit 状态

| 证据状态 | 文案 | 行为 |
| --- | --- | --- |
| fresh + queue drained + integrity pass | `Audit 通过 · App 内部数据一致` | 可展开证据摘要 |
| dirty/outbox 活跃 | `Audit 校验中 · 新数据正在生成` | 不判 integrity fail；barrier fresh 后重跑一次 |
| fresh 后有 issues | `Audit 未通过 · 发现 N 个一致性问题` | 展示前三个去重中文样本；内部 code仅作诊断 |
| 超时或 refresh failed | `Audit 未通过 · Read model 未在时限内更新` | 展示 scope、queue age/错误摘要 |
| 请求失败/证据不足 | `Audit 无法完成 · 请查看诊断` | 不显示通过 |

OA wrapper 只覆盖本页面文案和重跑行为；共享 `PageAuditIcon` 与其它页面输出保持不变。Audit 只证明 App 内 PostgreSQL snapshot 一致性，不宣称与此刻外部 Mongo/MySQL 完全相等。

## 禁止状态与回流

- 禁止 stale rows + “后台刷新中”同时展示。
- 禁止页面/read model worker读取 Mongo/MySQL。
- 禁止恢复 filter endpoint、`all_rows()`、Python 全量分页 facet、snapshot/pickle fallback或共享 invoice worker OA branch。
- 禁止普通月份 enqueue `oa_pending_payment:all`。
- 禁止候选 relation、历史 candidate 或非 outflow edge直接驱动 paid/写回。
- 禁止把 Flowable instance/request id 或 `t_payment_simple.id` 当 flow id。

## 变更记录

| 日期 | 决策 | 验证责任 |
| --- | --- | --- |
| 2026-07-16 | 单一 rows + ETag/304，500ms可见页检查，202立即隐藏旧 rows | API contract、frontend interaction、E2E |
| 2026-07-16 | OA sync 原子提交 completed/admission/payment snapshot/watermark/outbox | service-layer rollback、migration、integration |
| 2026-07-16 | OA PG-only projector和专属 worker；shared invoice worker删除 OA branch | worker isolation、dependency guard、regression |
| 2026-07-16 | 页面写回后幂等 reconcile PG snapshot；解决 MySQL 已变但页面仍旧 | command/service、rollback、retry regression |
| 2026-07-16 | OA 专属 Audit 中文文案，隔离共享组件 | component、API/Audit、其它页面 regression |
| 2026-07-17 | 双视图 source batch 隔离通用 status filter；admission-only 只刷新 OA，completed change 才共享 fan-out；in-progress 不解析附件/OCR | adapter/service/repository、fail-closed、真实 PG、架构 guard、三页面生产隔离 |
