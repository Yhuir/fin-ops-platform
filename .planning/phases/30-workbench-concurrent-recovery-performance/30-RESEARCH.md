# Phase 30 Research: 关联台并发恢复性能

日期：2026-07-25

## 目标

解释并优化 Phase 29 可逆关系生产验证中的关联台 `3.106–4.616s` 并发恢复样本，同时保持：

- active-generation 原子发布；
- 访问时 exact-scope freshness 与零写后 fan-out；
- stale/refreshing fail closed；
- 无新缓存、表、索引、worker、queue 或第二协调链路。

## 已验证事实

1. Phase 29 生产 worker 最近窗口 p95 约 `1.8–1.9s`。
2. 浏览器等价 gzip、六并发的 fresh 读取：
   - combined initial exact/all：约 `0.72–1.15s`；
   - `/groups` exact/all：约 `0.66–1.53s`。
3. 因此 `3.106–4.616s` 是 worker 恢复、轮询间隔和首次并发读的合计尾部，不是单个页面 SQL 持续卡死。
4. 正式关联台页面首屏和写后恢复调用 `GET /api/workbench?month=all`；可逆 relation runner 当前却把
   `GET /api/workbench/groups` 注册为 `reconciliation-workbench` 页面 consumer，测量边界不等于真实页面首屏。
5. `WorkbenchSqlProjectionBuilder._oa_projection_rows(...)` 为读取 OA rows 先调用
   `WorkbenchQueryService.get_workbench(...)`，该调用构建 summary、paired/unpaired grouping 和完整序列化结果后被丢弃，
   随后 builder 再扫描并序列化同一批 OA rows。10,000 行本地 characterization 证明当前路径执行 20,000 次
   serialization。
6. `WorkbenchSqlProjectionBuilder._legacy_oa_rows(...)` whole-repo 无调用者。

## 允许执行的共享修复

1. 在现有 `WorkbenchQueryService` 增加一个窄的 exact/all OA-row 读取方法；projection builder 直接消费该 I/O，
   不再构建并丢弃 legacy grouped payload。
2. 删除零调用 `_legacy_oa_rows(...)`。
3. 把可逆 relation runner 的关联台 consumer 合同切到真实 combined initial endpoint，并把业务断言根绑定到
   `paired` / `unpaired`；不降低 freshness、完整性或 relation membership 断言。

## 否决方案

- cache warmer：已删除旧链路，会恢复隐藏 I/O。
- relation delta / exact-candidate 增量 projection：Phase 27 已因复杂度和非正确性必要项删除。
- 第二份 all-scope stats/read model：跨月 canonical owner 去重不能安全求和，会增加 owner 与发布事务。
- 把 `/groups` 结果标为页面首屏性能：测量对象错误；`/groups` 继续作为滚动分页 API 独立保留。
- 放宽断言、接受 stale payload 或提高 timeout 来获得通过：不属于性能优化。

## 风险与验证

- OA row shape、附件父 OA、relation grouping 不得变化。
- combined initial 必须仍执行真实 freshness gate、exact-scope enqueue、最终 fresh membership 断言。
- 只运行定向 backend/service/read-model/API/frontend 与可逆生产 fixture；不运行无关 183-browser suite 或全量 CI。
