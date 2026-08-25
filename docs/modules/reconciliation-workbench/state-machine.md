# 关联台状态机

日期：2026-08-22

## 页面关系状态

```text
canonical fact + complete active formal relation    -> paired relation group
canonical fact + incomplete active formal relation  -> unpaired relation group（待补 OA/发票）
canonical fact - active formal relation              -> unpaired singleton
```

页面关系状态只有 `paired` 和 `unpaired`。`open`、`proposed`、candidate、decision 不是页面关系状态，也不是隐藏状态。

## 自动正式化

```text
durable dirty scope
  -> load canonical facts + active relations + withdrawal fingerprints
  -> pure deterministic plan
  -> ambiguous / unsafe / resource limited: no write, facts remain unpaired
  -> safe unique plan: one relation UoW
  -> active formal relation + history + outbox
  -> paired/unpaired result visible on the next direct canonical GET
```

匹配过程中没有持久候选状态。安全计划在事务提交前也不能成为页面事实。

## 正式关系生命周期

| 状态 | 含义 | 页面效果 |
| --- | --- | --- |
| `active` | 当前唯一有效正式关系，成员被该 case 独占 | 冻结要求满足时进入 paired；未满足时同 case 进入 unpaired，并保留下游 linked ownership |
| `cancelled` | 被上层业务取消或替换 | 不再拥有成员，成员按当前事实重新分区 |
| `withdrawn` | 用户/业务 owner 撤回 | 不再拥有成员；精确 typed member fingerprint 阻止自动重建 |
| `superseded` | 被新正式关系显式替代 | 旧关系仅保留审计，新 active relation 决定分组 |

人工、历史、系统自动创建不是状态。它们只记录在 actor、rule/evidence、source metadata 和 history 中。

## 人工确认与撤回

```text
unpaired selection with >=2 distinct canonical members
  -> preview resolves the current canonical row set and amount evidence
  -> amount/direction mismatch requires existing note; completeness does not block create
  -> submit/UoW re-resolves and locks the exact typed rows and active owners
  -> command/UoW creates active relation only
  -> current page performs exactly one normal direct canonical GET
  -> paired group when completion contract passes; otherwise same-case unpaired relation group

paired or unpaired active relation group
  -> withdraw preview requires the exact full active typed member set
  -> fingerprint binds current/after case + version + status + sorted members and confirm-history identity
  -> command/UoW locks current case/members, then predecessor case/members
  -> reloads and revalidates target topology, canonical members, predecessor case and unique owners
  -> withdraws/cancels current relation and restores previous provable stable topology
  -> current page performs exactly one normal direct canonical GET
  -> previous groups are restored; members without a predecessor become unpaired singletons
```

preview 请求本身只有一个页面级临时状态：`idle -> pending(confirm|withdraw) -> idle`。进入 pending 必须在发出请求前同步完成，并在下一次 render 输出 spinner、busy label、disabled、`aria-disabled` 和 `aria-busy`；confirm 与 withdraw 不允许并行或重复请求。成功响应仅在发起时的 selection 和 scope 仍一致时打开正式 preview drawer，否则直接丢弃。confirm 提交由同一 UoW 再次解析并锁定 exact typed selection；withdraw 的 `preview_id`、relation versions 和 fingerprint 是提交前置条件，并在该 UoW 同一事务内从已校验完整 canonical 行严格生成 OA alias。事务外 alias 扫描、异常后 ID 自映射和 alias first-wins 均不存在。页面 cursor 不是写 CAS。请求失败恢复入口并展示与结构化 conflict reason 对应的安全中文错误和 request id，不泄漏内部异常。该临时状态不改变 preview drawer 已有 submit/sync/load 状态机，也不会新增第三种正式页面关系状态。

人工确认允许同栏或跨栏成员，不再要求“银行 + OA/发票”；只有少于 2 个不同 canonical identity、成员不可用、active owner/version 冲突或非法 summary 才阻止进入预览/提交。Workbench 撤回若显式携带 row ids，preview 与 submit 都必须精确等于当前 active relation 的完整 typed member set；子集、超集、跨 case 混选或 case/rows 不一致返回 `workbench_relation_exact_selection_required`，不能自动补齐。case-only 撤回只保留给已证明 owner 的内部调用。旧 row `case_id` 不能让撤回后的 facts 继续同组；上一稳定拓扑只能由 canonical relation history 证明。恢复必须在同一事务锁内重新证明 canonical member 存在、restored case 没有被复用、每个成员只有唯一 active owner；缺 canonical 返回 `workbench_relation_canonical_member_missing`，case/owner 冲突返回 `workbench_relation_restore_conflict`，不允许部分恢复。没有 active relation 的行不能执行撤回。

relation version 是拓扑并发令牌：新关系从 `1` 开始，active relation 的 status 或 typed member set 改变时单调 `+1`，取消同样 `+1`；恢复 predecessor 时使用 `max(数据库当前 predecessor version, history snapshot version)+1`，不得回退到历史旧版本。withdraw preview fingerprint 包含 current/after relation 的 `case_id`、`version`、`status`、排序后的完整 typed members，以及所选 confirm history 的 `operation_id`、`operation_type`、`created_at`；拓扑或恢复历史任一漂移都拒绝旧 preview。

## Direct query 状态

```text
route entry                      -> 一次 combined canonical GET
query/filter/sort change         -> abort 旧请求，只重取受影响 zone 首页
page cursor                      -> 绑定 query hash 的 keyset GET；不做 OFFSET fallback
write committed                  -> 清空 selection/cursor，恰好一次 normal canonical GET
OA sync changed + active selection/preview/editor
                                -> 保留交互状态，只合并一个 pending canonical refresh
active interaction closed       -> 消费 pending，恰好一次 normal canonical GET
direct query unavailable/timeout -> 显示可重试读错误，不回退 projection/cache
hidden/focus/visible             -> 不触发 Workbench business status I/O
```

普通 writer 只提交 canonical facts/relation/version/audit/idempotency 与必要的独立领域任务。Workbench page 不拥有 queue、worker、generation、freshness polling 或 Redis payload cache；3 秒 OA status safety poll 只用于写门禁和触发 direct canonical reread。它不得在用户已选择记录、打开关系预览或正在录入发票时替换页面并清空交互；这些变化只折叠为一个 pending refresh，交互结束后执行一次。写成功后的 post-commit reread 仍优先执行并清空旧选择。OA sync、App Health、background jobs、`workbench_relation` 与 `workbench-matching` 保持各自 owner 合同。

### 发票费用明细归属

```text
active relation 含 OA expense items + relation invoice 无有效 item edge
  -> 发票行 `oa_invoice_attachment_unassigned`，完整关系留在 unpaired
  -> 用户从感叹号显式选择同关系内 1～100 个 OA 明细（默认零选择）
  -> 一个 POST：锁关系成员与 invoice source links，重验 item fingerprint / CAS / 幂等
  -> 冲突或证据漂移：零写，保留当前页面事实并提示刷新
  -> 成功：保留历史来源并追加精确 `oa_expense_item_invoice` 边
  -> 恰好一次 canonical GET；前端不本地挪行
  -> 待归属 item 消失，发票按显式 ownership 与所选 OA 明细同行；其它异常照常保留
```

该 action 不创建、拆分或修改正式关系成员，也不修改 OA、流水或发票金额。金额、项目名称和顺序不参与候选推荐或自动选择；已有不同或不完整显式归属必须 fail closed，精确相同 targets 重放为幂等成功。归属完成后关系是否进入 `paired` 只由下一次 canonical GET 的完整性与剩余异常决定。

## Row detail 读取状态

```text
typed row/detail key 在 latest committed 事实中可见 -> 200，打开抽屉
row/group 已不可见或身份不存在               -> 404，直接显示记录不可用
cursor/query 绑定错误                             -> 400，清页后由用户重试
repository / migration / timeout 不可用              -> 503，显示详情暂不可用
关闭抽屉或打开另一行                                -> abort 旧请求
```

row detail GET 是纯读操作：按 typed identity 窄查 latest committed canonical row，不构建全 scope group spine，不触发 dirty scope、outbox、refresh 或 cache。ETC 与流水规则 summary 只负责展开完整成员，不进入 row detail 状态机。

## 统一异常审阅状态

```text
无异常且 relation 完整                           -> paired
三栏可比较且命中七分类，或存在明细/附件异常       -> unpaired / 未配对异常
服务端重算当前 bundle --keep_unpaired-->          -> unpaired / 未配对异常
服务端重算当前 bundle
  --accept_paired 且无其他 blocker-->             -> paired / 已配对异常
已配对异常 --撤回到未配对--> keep_unpaired        -> unpaired / 未配对异常
成员/金额/附件状态变化 -> fingerprint 变化       -> 旧决定失效，重新回到未配对异常
```

该状态机改变关联台的有效展示分区，但不修改 `app.workbench_pair_relations.status=active`、成员或 canonical 金额。下游页面仍消费同一正式关系，避免异常审阅污染已支付、成本和发票归属。服务端在写入时重取 canonical detail，以当前 bundle 推导 evidence fingerprints 和 detected codes；客户端不得提交人工分类、逐项审阅结果或 actor。审阅只持久化 fingerprint-bound 决定、服务端证据摘要与 audit。

异常抽屉的筛选状态不创造新的业务状态：`bucket(unpaired|paired) -> view(amount|document_only) -> amount code`。金额分类由服务端保证每个关系最多一个；金额与资料并存时只进入该金额分类，资料只作为附属 evidence。没有金额分类且存在至少一个附件异常时才进入 `document_only`。一个关系无论含多少异常 item，在当前 bucket 内都只属于一个视图/分类并只计数一次；切换 bucket/view/code 必须取消旧请求并从新查询首页开始。

异常决定的作用域取当前 canonical 组的成员月份：成员都在同一月时写入单月决定；同一关系跨多个自然月时写入全局决定并在各月视图复用。不得因为页面使用 `month=all` 或成员跨月而拒绝审阅，也不得拆成多个相互冲突的月度决定。

只有当前 direct canonical descriptor 计算出的 `workbench_anomaly` 进入状态机；用户可见金额 item 严格是七种互斥三栏分类，子付款项局部差异只辅助定位已成立分类，不创建第八类。三栏不完整、金额无效、方向未知/冲突或总额完全一致时不得生成金额分类。历史人工分类字段、ignore/restore、WEX/row-ignore 不得改变分区、成员、抽屉或计数。

未配对工具栏不提供第二套人工异常入口；右上统一入口显示 `未配对异常 n | 已配对异常 m`。
