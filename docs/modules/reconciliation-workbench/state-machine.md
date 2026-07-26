# 关联台状态机

日期：2026-07-27

## 页面关系状态

```text
canonical fact + complete active formal relation    -> paired relation group
canonical fact + incomplete active formal relation  -> unpaired relation group（待补 OA/发票）
canonical fact - active formal relation              -> unpaired singleton
```

页面关系状态只有 `paired` 和 `unpaired`。`open`、`proposed`、candidate、decision、refreshing 或 generation 状态都不是页面关系状态。

## 页面请求状态

```text
idle -> loading -> data
                -> empty
                -> error -> retry -> loading
```

页面只用普通 HTTP 请求状态表达 loading/empty/error。它不读取 `read_model_status`，不轮询 refresh status，不订阅 Workbench SSE，也不展示旧 generation 后等待刷新。

## 自动正式化

```text
durable matching scope
  -> load canonical facts + active relations + withdrawal fingerprints
  -> pure deterministic plan
  -> ambiguous / unsafe / resource limited: no write, facts remain unpaired
  -> safe unique plan: relation command/UoW
  -> active formal relation + history
  -> next Workbench GET directly reads the committed facts
```

匹配过程中没有持久候选状态。安全计划在事务提交前也不能成为页面事实。

## 正式关系生命周期

| 状态 | 含义 | 页面效果 |
| --- | --- | --- |
| `active` | 当前唯一有效正式关系，成员被该 case 独占 | 冻结要求满足时 paired；否则同 case unpaired |
| `cancelled` | 被上层业务取消或替换 | 不再拥有成员，成员按当前 canonical facts 重新分区 |
| `withdrawn` | 用户/业务 owner 撤回 | 不再拥有成员；精确 typed member fingerprint 阻止自动重建 |
| `superseded` | 被新正式关系显式替代 | 旧关系只保留审计，新 active relation 决定分组 |

人工、历史或系统创建只记录 provenance，不形成页面状态。

## Preview 与提交

```text
selection
  -> preview pending
  -> canonical preview loaded
  -> drawer submit
  -> command transaction revalidates identities/types/ownership/versions
  -> committed -> page GET
  -> conflict 409 -> refresh selection
```

- preview 最多选择 20 行，只产生展示数据和 `preview_id`。
- confirm 与 withdraw preview 不并行、不重复请求。
- submit 不携带 `expected_read_model_version`。
- canonical row 消失/类型变化、active owner 变化、业务版本冲突或幂等 fingerprint 冲突均 fail closed。
- 成功响应后重新 GET；GET 失败显示读取错误，但不得把已经提交的 command 改写为失败。
