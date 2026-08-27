# 销项发票收款情况状态机

日期：2026-08-27

本页是 canonical 只读状态投影，不拥有状态写入口。状态由销项发票、精确冲红备注和 active relation 中唯一归属的收入流水即时计算。

## 状态

| code | 展示 | 颜色语义 | 条件 |
| --- | --- | --- | --- |
| `pending_collection` | 待收款 | 琥珀 | 正票，已收为 0 |
| `partial_collected` | 部分收款 | 紫 | 正票，`0 < 已收 < 价税合计` |
| `collected` | 已收款 | 绿 | 正票，已收大于或等于价税合计 |
| `reversed_by_red` | 已被红冲 | 灰蓝 | 正票号码被唯一红票的精确备注指向 |
| `reverses_blue` | 已冲销蓝票 | 靛蓝 | 负票备注唯一指向一张 canonical 正票 |
| `unmatched_red` | 红票待核对 | 红 | 负票缺少唯一、可解析且可命中的目标号码 |

## 判定顺序

1. 负票优先判断是否存在有效红蓝票关系：有则 `reverses_blue`，否则 `unmatched_red`。
2. 正票存在有效红蓝票关系时为 `reversed_by_red`，不再按收入流水显示收款进度。
3. 其余正票按 active relation 中的收入流水合计判断 `pending_collection`、`partial_collected` 或 `collected`。
4. 支出流水不得计入已收金额。

## 红蓝票精确关系

- 红票必须为负数，且备注精确包含一个 `被红冲蓝字数电发票号码：<20 位数字>`。
- 该号码必须恰好命中一张正数 canonical 销项发票。
- 缺备注、多个号码、目标不存在或目标重复均保持未匹配；不比较金额、税额、购销方或日期作兜底。
- 页面逐张输出 canonical 发票，并按精确号码派生关系；普通 active relation 仅用于收款流水归属。

## UI 状态

- `loading`：只加载当前 canonical rows。
- `empty`：API `200` 且 `pagination.total=0`。
- `error`：保留结构化错误和用户刷新入口，不伪装为空。
- `stale/refreshing/polling`：不适用。
- `permission`：read/export 权限控制页面和导出；没有 mutation/admin-only UI。

## 禁止状态

以下旧状态和流程不得恢复到本页：

- 手工收款状态、预计收款日期、提醒和备注。
- 收据 preview/issued/voided/reissued/history/settings。
- 手工红蓝票确认/撤销。
- OA 或收据关系详情。
- 页面 read model freshness、worker、operation barrier 或 fallback。
