# 关联台状态机

日期：2026-07-21

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
  -> paired after fresh generation publish
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
unpaired singleton selection
  -> preview locks canonical row set + expected versions
  -> command/UoW creates active relation only
  -> current page normal GET compares relation/rule versions and scoped OA/bank/invoice/pending-claim canonical versions
  -> exact Workbench scope converges on access
  -> paired group

paired group
  -> withdraw preview locks active case + expected versions
  -> command/UoW withdraws/cancels relation only
  -> current page normal GET compares the same canonical vector and converges on access
  -> each no-longer-owned fact becomes an unpaired singleton
```

preview 请求本身只有一个页面级临时状态：`idle -> pending(confirm|withdraw) -> idle`。进入 pending 必须在发出请求前同步完成，并在下一次 render 输出 spinner、busy label、disabled、`aria-disabled` 和 `aria-busy`；confirm 与 withdraw 不允许并行或重复请求。成功响应仅在发起时的 selection、scope 和 active read-model version 仍一致时打开正式 preview drawer，否则直接丢弃。请求失败恢复入口并展示安全中文错误；该临时状态不改变 preview drawer 已有 submit/sync/load 状态机，也不会新增第三种正式页面关系状态。

旧 row `case_id` 不能让撤回后的 facts 继续同组。没有 active relation 的行不能执行撤回。

## Read model 状态

| 状态 | 页面行为 |
| --- | --- |
| `fresh` | 可展示，满足权限和 write-safety 时可写 |
| `refreshing` | 已有 active generation 时继续显示上一版稳定 rows，并展示刷新诊断；不得把它当新事实、覆盖操作投影或提交写入 |
| `stale` | 已有 active generation 时可稳定展示，但明确陈旧并禁止依赖该版本提交关系写入 |
| `failed` | 保留上一版稳定 generation、展示真实错误和重试入口，不显示 false-empty |
| `missing` | 触发受控 enqueue；不得回退旧 candidate/snapshot 链路 |

只有完成、校验通过并原子激活的 generation 可成为页面事实。

## Row detail 读取状态

```text
列表 exact generation + 同 generation detail row -> 200，打开抽屉
expected generation 已切换                    -> 409，只重载列表并重试一次
active group 中无该 row                        -> 404，直接显示记录不可用
可见非 summary row 缺 detail row               -> 503，报告投影不变量破坏
repository / migration / timeout 不可用         -> 503，显示详情暂不可用
关闭抽屉或打开另一行                           -> abort 旧请求
```

row detail GET 是纯读操作：稳定 generation 即使处于 `refreshing/stale` 也可读取，不执行第二次 canonical freshness proof，不触发 dirty scope、outbox、refresh 或 generation 切换。ETC 与流水规则 summary 只负责展开完整成员，不进入 row detail 状态机。

## OA/发票异常状态

```text
日常报销 item 金额 = 显式绑定发票合计          -> absent
日常报销 item 金额完整且与绑定发票合计不等      -> active（金额不一致）
日常报销 item 有附件且零已解析绑定发票           -> active（OA发票附件缺失）
支付申请 OA/发票总额完整且不等                  -> active（金额不一致）
active --ignore--> ignored（已忽略：对应异常）
ignored --restore--> active
比较单元/成员/金额/附件状态变化 -> fingerprint 变化 -> 旧 ignored 决定失效
```

该状态机只描述异常处置，不是第三种关系状态；它与 `paired|unpaired` 正交。ignore/restore 不修改 relation、canonical facts 或金额，只持久化 fingerprint-bound 决定和 audit。“进行中的异常”与“已忽略的异常”由同一个右侧抽屉读取；后者可按关系组执行“撤回忽略”。
