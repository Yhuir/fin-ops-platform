# 税金抵扣状态机

## 页面读取状态

| 状态 | 触发 | 用户可观察行为 |
| --- | --- | --- |
| loading | 首次或月份切换 GET 未完成 | 展示 loading，不显示假空态 |
| ready | canonical GET 200 且有 rows/summary | 展示表格、统计、认证 drawer 与计划操作 |
| empty | canonical GET 200 且四组 rows 均为空 | 展示真实空态；不轮询 |
| error | 网络、权限、参数或 repository 失败 | 展示错误；保留明确重试/重新进入能力 |
| refreshing | 不适用 | 页面直读没有 read-model refreshing/stale/missing/202 状态 |

页面 focus/visibility 不触发额外请求；重新进入、月份变化、计划保存成功和认证导入完成会执行一次 normal GET。

## 抵扣计划状态

1. GET 返回 `canonical_snapshot_version` 和当前默认/最新保存选择。
2. 用户修改未锁定进项选择，页面调用 calculate。
3. 保存请求携带选择、token 与 idempotency key。
4. service 重新读取一次 canonical snapshot：
   - token 相同：使用该 payload 计算 summary 并保存；
   - token 不同或缺失：返回 409 `tax_offset_canonical_version_conflict`；
   - 重复 idempotency key：repository 返回原计划。
5. 成功后页面直接重新 GET；不等待 operation barrier。

## 认证导入状态

`previewed -> queued/running -> confirmed` 保持既有后台 job 合同。解析/OCR 只发生在导入工作流；confirmed 后 canonical records 已提交，页面直接 GET。重复 session confirm 幂等，失败不写半成品且错误可见。

## 认证与计划规则

- 已认证记录匹配当前进项时锁定对应行，不允许再次作为未认证计划选择。
- 范围外认证记录单独展示，但仍计入认证税额。
- 最新保存计划仅保留当前 canonical rows 中仍存在且可选择的 ID。
- Workbench relation 状态不参与任何流转。
