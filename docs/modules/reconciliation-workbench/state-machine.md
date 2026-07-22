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
  -> current page normal GET compares canonical source version
  -> exact Workbench scope converges on access
  -> paired group

paired group
  -> withdraw preview locks active case + expected versions
  -> command/UoW withdraws/cancels relation only
  -> current page normal GET converges on access
  -> each no-longer-owned fact becomes an unpaired singleton
```

旧 row `case_id` 不能让撤回后的 facts 继续同组。没有 active relation 的行不能执行撤回。

## Read model 状态

| 状态 | 页面行为 |
| --- | --- |
| `fresh` | 可展示，满足权限和 write-safety 时可写 |
| `refreshing` | 展示刷新诊断，不把旧结果当新事实 |
| `stale` | 明确陈旧；禁止依赖该版本提交关系写入 |
| `failed` | 展示错误和重试入口，不显示 false-empty |
| `missing` | 触发受控 enqueue；不得回退旧 candidate/snapshot 链路 |

只有完成、校验通过并原子激活的 generation 可成为页面事实。
