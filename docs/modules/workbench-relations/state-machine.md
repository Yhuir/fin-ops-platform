# Workbench 正式关系状态机

日期：2026-08-12

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
 -> require at least 2 distinct members for manual confirm
 -> check active overlap/case reuse/expected versions/idempotency
 -> create active relation + history
 -> enqueue durable refresh in same UoW
```

人工确认不要求成员跨 pane，也不以金额相等、方向已知或材料完整作为创建门槛；只有既有 `amount_check.requires_note=true` 时才强制填写 `note`，创建后的 relation 可继续显示在 `unpaired`。确定性引擎只有在唯一安全计划成立时进入此状态机；它的精确金额、证据、唯一性和资源门禁保持不变，没有中间候选或 decision 状态。

## 扩展/替换

```text
active case + unique safe new members
 -> explicit reference, or exact composite closure that fills a missing pane
 -> lock current version
 -> supersede/replace snapshot atomically under same case identity
 -> history records exact before/after
```

不能把一个 active member 同时分配到两个 case。组合证据扩展要求新增缺失栏与已有至少一栏金额完全一致；已有其他栏的金额差异继续作为异常展示，不阻断精确配对。候选集合、跨 case 重叠、撤回 fingerprint 或资源预算任一项无法唯一证明时均零写；完整三栏 case 保持不变。

## 撤回

```text
preview(paired or unpaired active case, exact full active member set, expected versions)
 -> fingerprint current/after topology + confirm history identity
 -> submit same exact member set and preview identity
 -> lock current/restored cases + restored canonical typed members
 -> reload and revalidate target topology/canonical members/unique owners
 -> withdrawn/cancelled + history + withdrawal fingerprint
 -> restore previous canonical stable topology when provable
 -> refresh
```

没有 active case 时 fail fast；未配对 singleton 不能撤回。撤回以整条 active case 为边界；preview 和 submit 的 canonical member set 都必须与当前完整 active member set 精确相等，子集、超集或混入其它 case 成员都不得由后端自动扩张。submit 的 typed member 校验、完整 canonical 行水合和 OA source alias 解析必须发生在同一个 relation UoW 事务中；preview DTO 与事务外 live-row 扫描都不能成为提交 alias 事实源。alias 多义时返回 `canonical_selection_ambiguous` 并零写。系统读取最近一次 confirm history 的 `before_relations`，并在同一事务的 current/restored case 与 canonical member locks 内重载和重验：目标 topology 未漂移、restored case 未被复用、canonical typed member 仍存在、每个成员只有唯一 active owner。没有可证明 predecessor 时成员才成为 unlinked singleton；任一恢复冲突整笔 fail closed。不得根据 row `case_id`、display metadata、非稳定 display ownership 或隐藏 fallback 猜测恢复；同一 member set 不得伪装为恢复。OA 附件 source binding 的不可拆规则继续由 pair service/command service 显式处理。

关系 version 是 topology 并发令牌：新关系为 1，status 或 typed member set 变化才在当前值上单调 +1；取消必然 +1；恢复 predecessor 时使用数据库当前 predecessor version 与历史快照 version 的较大值再 +1，不能回退到历史旧版本。withdraw preview identity 对 current/after relations 均包含 case id、version、status、按类型和 ID 排序的完整成员，并包含所选 confirm history 的 operation id/type/created at，因此关系拓扑或恢复历史任一变化都会使旧 preview 失效。

## 并发与幂等

- expected version 冲突返回 conflict，不覆盖新状态。
- exact full active member set 不一致返回 `workbench_relation_exact_selection_required`；恢复 canonical member 缺失或 case/owner 冲突均零写。
- 相同 idempotency key + fingerprint 返回原结果。
- 相同 key 不同 fingerprint fail fast。
- UoW 任一步失败全部回滚。
- worker replay 不创建重复 active relation/history/outbox。
