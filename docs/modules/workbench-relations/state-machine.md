# Workbench 正式关系状态机

日期：2026-07-21

## 当前状态

| 状态 | 成员占用 | 下游 | 关联台 |
| --- | --- | --- | --- |
| `active` | 是，case 独占 | `linked` | 冻结要求满足时为 `paired`；未满足时同 case 为 `unpaired` |
| `cancelled` | 否 | `unlinked` | 无其他 active owner 时 singleton `unpaired` |
| `withdrawn` | 否 | `unlinked` | 无其他 active owner 时 singleton `unpaired` |
| `superseded` | 否，由新 active relation 接管 | 由新关系决定 | 由新关系决定 |

来源不是状态。人工、历史和系统自动创建都走相同 active lifecycle。

## 创建

```text
validate canonical typed members
 -> check active overlap/case reuse/expected versions/idempotency
 -> create active relation + history
 -> enqueue durable refresh in same UoW
```

确定性引擎只有在唯一安全计划成立时进入此状态机；没有中间候选或 decision 状态。

## 扩展/替换

```text
active case + unique safe new members
 -> lock current version
 -> supersede/replace snapshot atomically under same case identity
 -> history records exact before/after
```

不能把一个 active member 同时分配到两个 case。

## 撤回

```text
preview(active case, expected versions)
 -> submit same preview identity
 -> withdrawn/cancelled + history + withdrawal fingerprint
 -> refresh
```

没有 active case 时 fail fast。普通撤回后不根据 row `case_id`、display metadata 或旧 history 猜测恢复关系。只有领域规则明确标记、且与当前 member set 不同的可恢复 snapshot 才可恢复；同一 member set 不得恢复。OA 附件 source binding 的不可拆规则继续由 pair service/command service显式处理。

## 并发与幂等

- expected version 冲突返回 conflict，不覆盖新状态。
- 相同 idempotency key + fingerprint 返回原结果。
- 相同 key 不同 fingerprint fail fast。
- UoW 任一步失败全部回滚。
- worker replay 不创建重复 active relation/history/outbox。
