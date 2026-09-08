# 银行明细状态机

日期：2026-09-08（同时间顺序修复本地实施中，未发布）

银行明细页面直接读取 PostgreSQL canonical facts，不再拥有 read model / worker 状态机。本文件只维护业务写状态和用户可观察的页面请求状态。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 银行流水 | active / excluded | `app.bank_transactions.status` | 导入模块创建或更新；页面只读。 |
| 自动标签解析 | `internal_transfer` | canonical 流水 + 系统规则 | SQL 在 `±2 days` context 中匹配内部转账；命中后停止普通规则。 |
| 自动标签解析 | `auto_matched` | 当前 active 自动标签规则 | 当前最高优先级仅命中一个规则；用户可从“撤销”入口重新选择标签，保存为人工覆盖。 |
| 自动标签解析 | `needs_confirmation` | 当前 active 自动标签规则 | 当前最高优先级命中多个规则；可确认当前候选，也可人工改为系统“内部往来款”。 |
| 自动标签解析 | `unmatched` | 当前 active 自动标签规则 | 可从 active 标签和系统“内部往来款”中人工分类。 |
| 自动标签解析 | `manual_confirmed` | active confirmation/category fact | 候选确认可撤销；人工分类可清除；effective 标签实际变化时，分类事实与受影响 active 普通关系 requirement/history 原子提交，随后 normal GET 重算当前状态。 |
| 自动标签规则 | active / archived | canonical app settings | PUT/file replacement 通过版本 CAS 变更；reapply 不改版本，只写审计并重新 GET。 |
| 正式关系 | unlinked / linked | `app.workbench_pair_relations status=active` | relation owner 写入或撤回；银行页面下次 GET 直接看到已提交状态。 |
| 同时间顺序 | `time` / `balance_chain` / `unresolved` | 完整同账户、同币种、同时间组的 canonical 时间/金额/账后余额 | 每次 GET 派生；补导、撤回或纠错后重新判断，不持久化状态。 |
| 账户余额 | `confirmed` / `last_known` / `unresolved` / `missing` | 共享同时间组末余额判定 | 导入、删除、重导或原始余额变化后，下次 accounts GET 直接聚合；详见账户余额状态机。 |

关键约束：

- `needs_confirmation` 只能提交当前 `auto_candidate_categories` 中的候选；外部往来同 code 多第三层候选时必须同时校验第三层标签。
- `category-assignment` 是唯一人工覆盖入口，可覆盖 `unmatched`、`auto_matched`、`needs_confirmation` 和系统 `internal_transfer`；可选 code 限定为当前 active 自动标签与系统 `internal_transfer`。
- 人工覆盖在同一事务中 supersede 旧 active category、revoke 旧 active confirmation 并写入新的 `source=manual, manual_assignment=true` fact；有效分类统一以该人工 fact 优先于当前自动规则，直到用户清除或再次覆盖。
- 自动标签旁的“撤销”只打开重新分类菜单，不写空事实；保存新标签后才原子覆盖，避免自动规则在空窗期重新生效。
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

同时间顺序是行级证据状态，不是请求 freshness：`time` 不需要组内推导；`balance_chain` 表示完整无分支组已确认；`unresolved` 在时间旁提示“同时间顺序待核实”，保持原行金额和余额。`unresolved` 只说明当前保守方法无法证明完整顺序，不声称一定存在多种真实顺序。分支组可能仍有可靠末余额，不能由行状态直接推断账户余额状态。

账户、流水、标签统计与规则分别保存失败状态，一侧成功不得清除另一侧的“账户未更新”“流水未更新”“标签统计未更新”或“规则未更新”。保留旧可用内容时同时显示未更新提示；AbortController 取消后和提交结果前都阻止过期请求覆盖当前筛选结果。切换账户的旧流水响应、旧 header 刷新的规则响应都不能覆盖更新的读取；账户失败不得被流水成功清除。页面重新激活和刷新继续复用现有请求入口。API 缺少或返回未知顺序/余额状态时应提示刷新页面，不将缺字段默认为已确认。

## 写后重新读取

1. route/service 完成权限、业务校验、canonical write、audit/CAS。
2. 成功响应不返回 202、read-model status、refresh scope/job 或 operation barrier。
3. 当前页面保留成功反馈，并发起一次当前 transactions GET。
4. 新 GET 成功后替换当前 rows；空结果进入真实 empty。
5. GET 失败进入 error，用户可通过筛选变化或明确重试恢复。

## 禁止状态与恢复

- 禁止 `refreshing`、`stale`、`schema_mismatch`、`missing` 等页面 read-model UI 状态；`balance_status=missing` 仅表示账户没有可用原始余额，与已退役 freshness 状态无关。
- 禁止定时轮询 accounts/transactions、隐藏页后台 I/O、route unmount 后残留 timer。
- 禁止 stale fallback、旧 rows 冒充新请求结果或 202 自动重试。
- 请求错误时不切换到空态；保留可用 rows 并显示错误，下一次用户请求重新读取 canonical facts。

## 变更记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
| 2026-09-08 | 增加行级顺序/账户余额证据状态及局部请求失败、过期响应保护；未发布 | 本地测试和验收进度见同时间修复计划；不以本行代替执行结果 |
| 2026-07-27 | 页面迁移为 direct canonical PostgreSQL query，删除 read-model freshness/polling 状态，写后只做一次 GET | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsPage.test.tsx`、`web/e2e/bank-details-stale-refreshing.spec.ts` |
| 2026-08-08 | 人工分类可原子覆盖自动/候选分类；待分类、待确认和自动标签重新分类菜单加入“内部往来款”，人工事实成为统一 effective 优先级 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_postgres_mutation.py`、`tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetailsPage.test.tsx` |
