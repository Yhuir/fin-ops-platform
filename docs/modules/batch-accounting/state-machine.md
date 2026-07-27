# 批量账务状态机

日期：2026-07-27

## 业务关系状态

| 当前状态 | 事件 | 校验 | 下一状态 |
| --- | --- | --- | --- |
| `unsubmitted` | submit | 银行/OA 资格、权限、金额说明、active relation 冲突、expected version | `active batch_accounting` |
| `active batch_accounting` | withdraw | 权限、active mode、撤回原因、expected version | `cancelled` |
| `cancelled` | 页面重新 GET | canonical 银行/OA 重新满足候选资格 | `unsubmitted` |

正式关系状态只来自 `app.workbench_pair_relations`；页面不从 projection 推断状态。

## 页面可观察状态

| 状态 | UI 行为 |
| --- | --- |
| `loading` | 展示银行/OA 加载状态，不展示假空集 |
| `ready` | 展示 canonical rows、summary 和双分页 |
| `empty` | 成功响应且当前页 total/rows 为空时展示真实空态 |
| `error` | 请求失败时展示后端 message 和刷新入口 |
| `submitting` / `withdrawing` | 全局操作层阻止重复写；等待 command HTTP 完成 |
| `reloading_after_write` | command 成功后执行一次普通 GET |
| `write_succeeded_reload_failed` | 保留成功 message，并提示最新列表加载失败、需手动刷新 |

不存在 `refreshing/stale/missing read model`、refresh enqueue、202 polling 或 operation barrier 状态。

## 页面状态重置

- 切换 bucket、银行年份或服务端分页时重置不再可见的选择。
- 切换银行、OA 选择或 bucket 时清理差额说明，避免将旧说明用于新关系。
- OA search 变化时 OA 页码重置为 1，并发中的旧 GET 由 AbortController 取消。
- submit/withdraw 成功后的唯一自动收敛动作是当前页一次 GET。

## 冲突与错误

- 非法参数、候选资格和必填说明返回 400。
- canonical active relation/version 冲突返回 409。
- query repository 或 command service 不可用返回 503。
- command 已成功但后置 GET 失败不回滚、不改写为 command 失败。
