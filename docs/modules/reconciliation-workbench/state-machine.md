# 关联台状态机

日期：2026-08-13

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
  -> preview locks canonical row set + expected versions
  -> amount/direction mismatch requires existing note; completeness does not block create
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

preview 请求本身只有一个页面级临时状态：`idle -> pending(confirm|withdraw) -> idle`。进入 pending 必须在发出请求前同步完成，并在下一次 render 输出 spinner、busy label、disabled、`aria-disabled` 和 `aria-busy`；confirm 与 withdraw 不允许并行或重复请求。成功响应仅在发起时的 selection 和 scope 仍一致时打开正式 preview drawer，否则直接丢弃。preview 产生的 `preview_id`、canonical entity versions 和 fingerprint 是提交前置条件；页面 cursor 不是写 CAS。请求失败恢复入口并展示安全中文错误；该临时状态不改变 preview drawer 已有 submit/sync/load 状态机，也不会新增第三种正式页面关系状态。

人工确认允许同栏或跨栏成员，不再要求“银行 + OA/发票”；只有少于 2 个不同 canonical identity、成员不可用、active owner/version 冲突或非法 summary 才阻止进入预览/提交。Workbench 撤回若显式携带 row ids，preview 与 submit 都必须精确等于当前 active relation 的完整 typed member set；子集、超集、跨 case 混选或 case/rows 不一致返回 `workbench_relation_exact_selection_required`，不能自动补齐。case-only 撤回只保留给已证明 owner 的内部调用。旧 row `case_id` 不能让撤回后的 facts 继续同组；上一稳定拓扑只能由 canonical relation history 证明。恢复必须在同一事务锁内重新证明 canonical member 存在、restored case 没有被复用、每个成员只有唯一 active owner；缺 canonical 返回 `workbench_relation_canonical_member_missing`，case/owner 冲突返回 `workbench_relation_restore_conflict`，不允许部分恢复。没有 active relation 的行不能执行撤回。

relation version 是拓扑并发令牌：新关系从 `1` 开始，active relation 的 status 或 typed member set 改变时单调 `+1`，取消同样 `+1`；恢复 predecessor 时使用 `max(数据库当前 predecessor version, history snapshot version)+1`，不得回退到历史旧版本。withdraw preview fingerprint 包含 current/after relation 的 `case_id`、`version`、`status`、排序后的完整 typed members，以及所选 confirm history 的 `operation_id`、`operation_type`、`created_at`；拓扑或恢复历史任一漂移都拒绝旧 preview。

## Direct query 状态

```text
route entry                      -> 一次 combined canonical GET
query/filter/sort change         -> abort 旧请求，只重取受影响 zone 首页
page cursor                      -> 绑定 query hash 的 keyset GET；不做 OFFSET fallback
write committed                  -> 清空 selection/cursor，恰好一次 normal canonical GET
direct query unavailable/timeout -> 显示可重试读错误，不回退 projection/cache
hidden/focus/visible             -> 不触发 Workbench business status I/O
```

普通 writer 只提交 canonical facts/relation/version/audit/idempotency 与必要的独立领域任务。Workbench page 不拥有 queue、worker、generation、freshness polling 或 Redis payload cache；OA sync、App Health、background jobs、`workbench_relation` 与 `workbench-matching` 保持各自 owner 合同。

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
任一金额对不等或附件异常                         -> unpaired / 未配对异常
逐项已审阅 + 金额项已人工分类 --keep_unpaired-->  -> unpaired / 未配对异常
逐项已审阅 + 金额项已人工分类
  --accept_paired 且无其他 blocker-->             -> paired / 已配对异常
已配对异常 --撤回--> keep_unpaired               -> unpaired / 未配对异常
成员/金额/附件状态变化 -> fingerprint 变化       -> 旧决定失效，重新回到未配对异常
```

该状态机改变关联台的有效展示分区，但不修改 `app.workbench_pair_relations.status=active`、成员或 canonical 金额。下游页面仍消费同一正式关系，避免异常审阅污染已支付、成本和发票归属。金额异常提交前必须从 `OA流水金额不一致`、`OA发票金额不一致`、`流水发票金额不一致`、`无异常` 中选择一个或多个；`无异常` 与三种差异互斥。审阅只持久化 fingerprint-bound 决定、人工分类与 audit。

异常决定的作用域取当前 canonical 组的成员月份：成员都在同一月时写入单月决定；同一关系跨多个自然月时写入全局决定并在各月视图复用。不得因为页面使用 `month=all` 或成员跨月而拒绝审阅，也不得拆成多个相互冲突的月度决定。

只有当前 direct canonical descriptor 计算出的 `workbench_anomaly` 进入状态机；金额 item 必须是具体的三种 pair code，禁止恢复泛化“金额不一致”。系统检测 code 与人工 `review_classification_codes[]` 是不同事实：用户可以纠正分类，但不能覆盖或删除原始检测证据。历史 ignore/restore、WEX/row-ignore 不得改变分区、成员、抽屉或计数。

未配对工具栏不提供第二套人工异常入口；右上统一入口显示 `未配对异常 n | 已配对异常 m`。
