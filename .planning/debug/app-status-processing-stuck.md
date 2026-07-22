---
status: resolved
trigger: "运行状态持续显示关联台正在同步约十分钟；截图显示 Read model 3 刷新中、Worker 全部 active 28/22、Queue 0 pending / 25 processing；要求使用 grill-me 全量分析真实原因。"
created: 2026-07-22
updated: 2026-07-22
---

# Debug Session: app-status-processing-stuck

## Symptoms

- Expected behavior: 关联台和相关 read model 刷新应在正常 SLO 内收敛，运行状态回到已同步，durable queue 不长期保留 processing。
- Actual behavior: 运行状态持续约十分钟显示“关联台正在同步”；3 个 read model 刷新中，25 个 queue event 处于 processing，pending 为 0；worker 摘要显示全部 active。
- Error messages: 截图没有失败或缺失提示，只有持续 processing。
- Timeline: 2026-07-22 09:59:40 截图时已持续约十分钟。
- Reproduction: 打开生产 app 并查看全局运行状态抽屉，可持续观察到上述 runtime snapshot。

## Current Focus

- hypothesis: 已证实是全量 scope fan-out 与持续业务写入共同造成的队列放大/移动收敛目标，不是单个 worker 或 SQL 锁卡死。
- test: 已对照 App Status 聚合合同、durable queue/dirty scope 事件、worker heartbeat、PostgreSQL activity/locks、发布后 service 运行状态和代码 fan-out 图完成交叉验证。
- expecting: 不适用；根因已收敛。
- next_action: 若授权修复，先对 all-scope 影响月份做精确化，再对 parent/shard 收敛事件和批量分类确认做合并去重。
- reasoning_checkpoint: 两次真实规则保存创建全历史月份收敛；运行中的分类确认又持续改写精确月份和 all 父 scope，导致后台一直“有事做”。
- tdd_checkpoint: diagnose-only; no fix authorized.

## Evidence

- 2026-07-22: 截图显示 `0 pending / 25 processing` 且 worker `active 28/22`，排除“任务尚未被 worker 领取”和“所有 worker 缺失”两种解释。
- 2026-07-22: 前端 `AppStatusIndicator` 直接展示 `AppStatusOverviewService` 汇总的 read model、worker、outbox 状态，页面转圈不是浏览器本地定时器自行制造。
- 生产 `app.app_settings` 最终记录为 version 127，`updated_at=2026-07-22 09:51:03.980652+08`；规则版本为 91，证明 09:51 是真实配置写入，不是空保存。
- durable queue 证明存在两波独立 `bank_auto_tag_rules_changed` 根事件：第一波从 09:41:48.801 开始，第二波从 09:51:04.057 开始；每波都以 `scope=all` 分发至 bank detail/no-OA/bank flow/workbench/workbench relation/matching/invoice lifecycle/pending invoice/cost/search。
- 09:40–10:10 的生产事件窗口共计 6,015 个 read-model refresh 事件：`pending_invoice=1,835`、`cost_statistics=2,119`、`workbench=603`、`workbench_relation=534`、`search=494`、`invoice_lifecycle=182`、`bank_detail=154`，其余 94。
- 最大的 fan-out reason 是 `pending_invoice_month_shard=1,600`、`workbench_shard_published=1,082`、`cost_statistics_shard_converged=942`、`workbench_all_shard=563`、`bank_transaction_category_changed=559`、`workbench_relation_month_shard=443`、`search_all_shard=403`。
- 队列不是停滞：分钟级新建量在 09:43 为 437、09:44 为 421、09:45 为 499、09:54 为 459、09:56 为 585、09:57 为 450，说明 worker 一边消费，上游一边继续扩散。
- 截图中的 2024-05/2024-04/2023-12 是尾部 scope：首波 bank-detail 事件约 58–60 秒完成，首波 workbench 月分 shard 从入队到完成约 122–129 秒；后续又被新写入重复失效。
- 最慢收敛链路是 workbench 和 invoice lifecycle：workbench 603 事件入队到完成 p95 94.282s/max 136.855s；invoice lifecycle 182 事件中 101 个发生重试，max 543.635s。10:05 时只剩 5 个 invoice-lifecycle 月份 scope。
- 持续业务写入是第二个放大器：09:42:58–10:17 一直有 `bank_detail_category_confirmation_changed` / `bank_transaction_category_changed`；10:16–10:17 的最后采样仍新增 2026-06、2026-02 的分类确认 fan-out，并再次创建 workbench all/month shard。
- 无故障证据：28/22 required worker 都有心跳，两个 invoice-lifecycle worker 在尾部采样中仍活跃处理；无 failed/dead-letter、无 worker missing/stale/mismatch、无数据库不可用。
- PostgreSQL 实时锁采样为 `blocked_sessions=0`、`lock_waiters=0`；workbench systemd 单元自 09:21:45 运行且 `NRestarts=0`，排除发布重启造成的孤儿 lease。
- 单个 handler 普遍仍是秒级：最近 15 分钟 workbench handler p95 约 4.7s、bank detail p95 约 2.94s、pending invoice p95 约 1.11s；十分钟墙钟时间来自排队、fan-out、重试和收敛目标持续改变，不是一条超慢 SQL。

## Eliminated

- 纯前端动画卡住：已排除；状态来自后端 App Health/App Status runtime snapshot。
- 完全没有 worker：已排除；required worker 均被判 active，尾部 processing owner 的 heartbeat 仍新鲜且正在执行。
- worker 孤儿/stale lease：已排除；owner heartbeat 新鲜，服务无重启。
- PostgreSQL 锁等待/单条长 SQL：已排除为主因；实时无 blocker，handler 延迟大部分为秒级。
- RabbitMQ/transport 卡住：已排除为主因；durable PostgreSQL queue 持续发生 claim/complete/fan-out。
- 单个坏月份或脏数据：已排除；截图中的历史月份是 all-scope 展开后的尾部，同一 scope 后续能够完成又被新写入重新失效。

## Resolution

- root_cause: 09:41 和 09:51 的两次自动标签规则真实保存都用 `scope=all` 对全历史月份发起多 read-model 收敛；各 read model 又继续拆 month/filter shard 并生成父 scope 收敛事件。同时从 09:42:58 开始持续发生分类确认写入，不断重新失效 workbench/invoice lifecycle/pending invoice/cost/search，使收敛目标持续移动。直接延迟尾部为 workbench fan-out 和 invoice-lifecycle 依赖/重试链。
- fix: diagnose-only; not authorized.
- verification: 已读取代码/边界文档；已通过生产 admin health 入口、PostgreSQL read-only 事务、worker heartbeat、service start/restart 状态和 DB lock 采样交叉验证；所有生产操作均为只读。
- files_changed: `.planning/debug/app-status-processing-stuck.md` only (debug artifact).
