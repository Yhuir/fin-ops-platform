# 银行明细状态机

日期：2026-07-27

银行明细页面直接读取 PostgreSQL canonical facts，不再拥有 read model / worker 状态机。本文件只维护业务写状态和用户可观察的页面请求状态。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 银行流水 | active / excluded | `app.bank_transactions.status` | 导入模块创建或更新；页面只读。 |
| 自动标签解析 | `internal_transfer` | canonical 流水 + 系统规则 | SQL 在 `±2 days` context 中匹配内部转账；命中后停止普通规则。 |
| 自动标签解析 | `auto_matched` | 当前 active 自动标签规则 | 当前最高优先级仅命中一个规则。 |
| 自动标签解析 | `needs_confirmation` | 当前 active 自动标签规则 | 当前最高优先级命中多个规则；只能从当前候选确认。 |
| 自动标签解析 | `unmatched` | 当前 active 自动标签规则 | 可人工补分类。 |
| 自动标签解析 | `manual_confirmed` | active confirmation/category fact | 候选确认可撤销；人工补分类可清除；effective 标签实际变化时，分类事实与受影响 active 普通关系 requirement/history 原子提交，随后 normal GET 重算当前状态。 |
| 自动标签规则 | active / archived | canonical app settings | PUT/file replacement 通过版本 CAS 变更；reapply 不改版本，只写审计并重新 GET。 |
| 正式关系 | unlinked / linked | `app.workbench_pair_relations status=active` | relation owner 写入或撤回；银行页面下次 GET 直接看到已提交状态。 |
| 账户余额 | has_balance / missing_balance | canonical 银行流水最新非空 balance | 导入、删除、重导或原始余额变化后，下次 accounts GET 直接聚合。 |

关键约束：

- `needs_confirmation` 只能提交当前 `auto_candidate_categories` 中的候选；外部往来同 code 多第三层候选时必须同时校验第三层标签。
- `category-assignment` 只允许 `unmatched`，不得覆盖 `auto_matched`、`needs_confirmation` 或 `internal_transfer`。
- 人工补分类清除把 active fact 标记为 `cleared`，不得写 active `unknown`。
- 分类与规则写保留 canonical fact/version/audit/CAS；不创建页面 read-model dirty/outbox 或 freshness target。
- 正式关系只认 active canonical relation；candidate/withdrawn/turnover manual closure 不生成页面 linked 标签。
- 分类写闭环不得更新 ETC/批量账务关系，不得发送关联台页面通知；关联台按自己的 freshness/generation 读取已提交 canonical relation。

## 页面请求状态

| UI 状态 | 来源 | 用户语义 |
| --- | --- | --- |
| loading | 首次 accounts / transactions / rules 请求未完成 | 展示加载态，不渲染假空。 |
| ready | direct canonical GET 成功且有 rows | 展示 rows、统计、facets、关系标签和分页。 |
| empty | direct canonical GET 成功且 `rows=[]` | 当前筛选真实无流水；不需要 freshness 二次判定。 |
| error | API、导出或写请求失败 | 展示结构化错误；abort-like 请求不显示业务错误。 |
| retrying | 用户改变筛选、搜索、分页或显式重试 | 发起新的 direct GET；不使用 timer 或 worker polling。 |
| permission disabled/hidden | session permissions | 规则保存、reapply、确认、人工补分类和导出入口按权限禁用或拒绝。 |

## 写后重新读取

1. route/service 完成权限、业务校验、canonical write、audit/CAS。
2. 成功响应不返回 202、read-model status、refresh scope/job 或 operation barrier。
3. 当前页面保留成功反馈，并发起一次当前 transactions GET。
4. 新 GET 成功后替换当前 rows；空结果进入真实 empty。
5. GET 失败进入 error，用户可通过筛选变化或明确重试恢复。

## 禁止状态与恢复

- 禁止 `refreshing`、`stale`、`schema_mismatch`、`missing` 等页面 read-model UI 状态。
- 禁止定时轮询 accounts/transactions、隐藏页后台 I/O、route unmount 后残留 timer。
- 禁止 stale fallback、旧 rows 冒充新请求结果或 202 自动重试。
- 请求错误时不切换到空态；保留可用 rows 并显示错误，下一次用户请求重新读取 canonical facts。

## 变更记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
| 2026-07-27 | 页面迁移为 direct canonical PostgreSQL query，删除 read-model freshness/polling 状态，写后只做一次 GET | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-stale-refreshing.spec.ts` |
