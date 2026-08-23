# OA 待付款核对状态机

日期：2026-08-06

## 业务状态

### OA workflow

| 状态 | Canonical 来源 | 页面视图 |
| --- | --- | --- |
| `completed` | `app.oa_applications` | 已完成 OA |
| `in_progress` | `app.oa_pending_payment_admissions` | 进行中 OA |

页面不读取 Mongo workflow 或 MySQL payment table；外部状态必须先由 OA integration 收敛到 PostgreSQL。

### Relation

| 状态 | 页面语义 |
| --- | --- |
| completed/in-progress + `app.workbench_pair_relations.status='active'` | 统一正式 relation evidence |
| completed/in-progress + withdrawn/inactive | 未关联；不得由 raw payload 的旧 active 值复活 |
| candidate/历史 claim only | 不等于正式支付，不直接驱动 paid 或 writeback |

所有 active 正式关系都进入本页关系消费。`turnover_manual_closure` 等混合收支关系中，只有可解析的 outflow bank member 是支付证据；inflow 不进入流水展示、已付金额或写回金额。只有 inflow、没有 outflow 时仍为未支付。

### Payment

| 状态 | 业务含义 |
| --- | --- |
| `unpaid` | 没有可解析的 active outflow relation |
| `paid` | 至少存在一条可解析的 active outflow relation；金额差额不改变关系事实，但会阻断自动写回 |
| `oaPaymentWriteback.code=written` | PostgreSQL payment-status snapshot 已记录 OA 外部写回结果 |

页面只展示后端给出的结果，不在浏览器重算金额、方向或写回资格。

## 页面读取状态

```text
idle
  -> loading
  -> ready(rows)
  -> empty
  -> error
```

- route mount、query 变化、手工刷新和本页写成功后各发起一次正常 rows GET。
- `loading`：首屏 skeleton。
- `ready`：显示 rows、summary、statistics、facets 和分页。
- `empty`：成功 `200` 且 rows 为空，显示“当前条件下暂无记录”。
- `error`：网络、HTTP 或 canonical repository 失败，清除旧 rows 并展示可观察错误；用户可手工重试。
- `refreshing` 仅表示用户已点击手工刷新且该请求正在进行，不是 read-model 状态。
- 晚到响应不能覆盖更新的 query；unmount/query change 取消旧请求。

不存在页面 `stale/missing/refreshing/fresh` read-model 状态，不存在 `202/304/ETag` 分支，也不存在定时 polling 或 visibility/focus 恢复。

## Rows snapshot

```text
parse/validate query
  -> begin REPEATABLE READ READ ONLY
  -> SQL select descriptors + summary + statistics + facets + total
  -> batch load current-page canonical facts
  -> pure row composition
  -> commit read-only snapshot
  -> 200 response
```

任何一步失败都不能返回部分 rows/summary。空 descriptors 不执行 hydrate。

## Detail 状态

```text
drawer open
  -> loading
  -> canonical detail ready
  -> 404 not found
  -> error
```

详情不访问外部 OA，也不等待 read-model worker。relation kind 非法返回 `400`；identifier 不存在返回结构化 `404`。

## OA 导出抽屉状态

```text
closed
  -> ready(all selected)
  -> ready(partial selected) | empty-selection
  -> downloading
  -> downloaded | export-error
```

- 打开时默认选择已完成和进行中 OA；“全选”只是前端聚合选择，不是第三种后端来源。
- 至少选择一种来源后才允许下载；`downloading` 期间禁止重复提交和关闭。
- 下载不改变 rows query、不刷新页面，也不继承月份、搜索、筛选、排序或分页。
- 失败只在抽屉内显示并保留当前选择；关闭后恢复默认全选。
- 后端在单一只读 snapshot 中生成 OA-only XLSX，成功后记录不含业务内容的下载审计。

## 支出流水候选抽屉状态

```text
closed
  -> loading
  -> ready(rows) | empty | candidate-error
  -> loading(retry)
```

- 候选 GET 仍由单一 abortable effect 发起；每次明确查询或回车只产生一个请求，晚到、已取消或旧 generation 的结果不能覆盖当前状态。
- `candidate-error` 只属于 `OaBankLinkDrawer`，在当前请求开始和成功时清空，仅由当前未取消且未过期的失败设置，并在抽屉内以 accessible alert 展示。
- 候选查询错误不得写入或清除页面 `error` / `actionError`；关联提交和页面写回等 mutation 错误继续由页面级错误状态负责。
- 抽屉关闭后候选错误反馈不可残留在页面；重新打开时由新的当前请求开始清理。

## 写回状态机

### `writeback-paid`

```text
validate actor/tenant/payload
  -> load OA + active relation evidence
  -> validate workflow/outflow/amount/flow id（混合关系只合计 outflow）
  -> idempotent external MySQL paid write
  -> idempotent PostgreSQL payment-status snapshot reconcile
  -> audit/result
  -> frontend normal rows GET
```

- already-paid 仍必须确保 PostgreSQL snapshot 已收敛。
- 外部成功、PG 失败：返回可安全重试错误，不返回成功。
- 冲突/非法状态保持既有 `409/400` 合同。
- 成功响应不含 read-model refresh/barrier metadata。

### `link-bank-transactions`

```text
validate actor/tenant/payload/idempotency
  -> validate outflow bank rows and active owner overlap
  -> create formal relation or extend the unique active case + audit
  -> amount matched ? run paid writeback : keep formal relation
  -> result
  -> frontend normal rows GET
```

重复提交必须幂等；多个 active owner、版本冲突或正式关系冲突不得半写。历史 pending relation/claim 不参与运行时。

## System Audit 子页 proof

OA 待付款页面不展示 Audit 控件。管理员在 App Health 运行 System Audit 时，后端在同一只读 snapshot 中执行本模块 proof：

- 校验 canonical relation member 存在性和 active identity 唯一性。
- 独立计算 active OA+outflow 期望关系集，并与页面 canonical consumer 对照。
- 关系存在但页面遗漏、没有 outflow、支付状态错误或 relation member 缺失时，Audit 必须返回 blocking integrity issue。

该 proof 不调用 operation barrier、不轮询，也不作为 rows 正确性的 gate；它只向 System Audit 返回结构化 integrity/queue 结果和有界问题样本。

## 禁止状态与回流

- 禁止 stale rows + “后台刷新中”。
- 禁止页面请求访问 Mongo/MySQL/对象存储。
- 禁止 read model、Redis、queue、worker 或 Workbench projection 成为页面事实源。
- 禁止候选、inflow、inactive relation 直接驱动 paid/写回。
- 禁止外部写成功、PG reconcile 失败时返回成功。

## 变更记录

| 日期 | 决策 | 验证责任 |
| --- | --- | --- |
| 2026-07-27 | rows/details 迁移为 PostgreSQL canonical direct read；删除页面 freshness/version/cache/polling 合同 | repository/service/API/frontend/integration |
| 2026-08-06 | completed/in-progress 统一读写 active `app.workbench_pair_relations`；旧 pending relation/claim/promotion 退役 | canonical relation consistency / migration / Workbench workflow gate |
| 2026-07-27 | 写命令不再返回 `readModelRefresh`，成功后 normal GET | command/API/frontend |
| 2026-07-28 | 所有 active relation mode 均进入页面；混合收支关系只把 outflow 作为展示、已付金额和写回证据；Audit 对照期望关系集与 consumer | query/canonical rows/command/Audit/integration |
| 2026-08-19 | 增加已完成/进行中 OA 事实源 XLSX 导出；单快照、OA-only、无页面刷新 | export service/repository/API/frontend/E2E |
