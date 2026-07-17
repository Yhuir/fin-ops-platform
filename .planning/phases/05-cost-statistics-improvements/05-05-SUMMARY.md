---
phase: 05-cost-statistics-improvements
plan: 05
status: complete
completed_at: 2026-07-16
next_state: IMPLEMENTING
requirements:
  - COST-PERF-01
  - COST-FRESH-01
  - COST-LEGACY-01
---

# 05-05 执行摘要：首屏 I/O 隔离与前端旧缓存删除

## 结果

本切片已关闭 05-04 后最直接、且无需扩展后端合同的首屏 I/O 放大器。成本统计默认 time/month 首屏现在只请求当前 `active:YYYY-MM` explorer，不再为尚未打开的导出中心无条件请求约 `765KB decoded / 1.769s` 的 `active:all`。前端 5 分钟 module-level explorer Map、get/clear API 和缓存初始化已全部删除；页面首次进入、重新挂载、手工刷新或 domain event 触发刷新都必须重新经过后端 freshness boundary。

当前 explorer state 绑定 canonical `project_scope:month`。scope/view 切换开始后，上一 scope payload 立即退出可操作内容；旧 effect generation 由既有 AbortController cleanup 阻止写回。domain/manual/tag-rule refresh 同时失效本次 mount 内的导出参考数据，避免事实变化后继续复用旧导出选项。

导出参考数据改为用户动作后的窄生命周期读取：time/bank-tag 导出不请求 `active:all`；project view 复用其已加载的 fresh all payload；expense-type 或导出中心内部切换到 project/expense-type 时，只有缺少本次 mount 内 fresh reference 才请求一次 all。请求 non-fresh 或失败时导出中心保持关闭并显示明确错误；并发模式切换会取消失去所有权的请求，不回退旧缓存。

whole-repo current-code scan 证明两个零调用旧 client `fetchCostStatisticsMonth`、`fetchProjectCostStatistics` 已无调用方，现连同只为它们存在的 API DTO 和前端 types 一并删除。没有新增 endpoint、cache manager、global store、singleflight、SSE、cursor、fallback 或依赖。

本轮未修改后端、HTTP DTO、read model、worker、共享 query/cache/UI、其他页面或其他页面 read model。没有部署、生产访问/写入、branch、stage、commit、push 或 PR，也没有生成 05-06 prompt。唯一下一状态是 `IMPLEMENTING`。

## Grill-me / 反过度设计复核

| 问题 | 结论 |
| --- | --- |
| 是否需要新后端 export-options endpoint | 本切片不需要；复用现有 fresh explorer 即可确定性移除首屏 all I/O。专用有界 endpoint 必须由后续 cursor/payload 设计统一决定，避免现在形成第二套临时合同。 |
| 是否以新前端 cache 换取返回页速度 | 不使用；没有 durable freshness 证明的 TTL payload 会重现“事实已变、页面仍旧”的问题。 |
| 是否增加通用请求状态框架 | 不增加；复用组件 state、AbortController 和现有 export feedback，仅增加 cost-local request ownership。 |
| 是否保留旧 client 作为兼容 | 不保留；全仓扫描已证明生产零调用，删除比隐藏 fallback 更安全。 |
| 是否已经达到最终 SLO | 尚未；本轮只消除首屏第二个大请求。当前 explorer 仍返回完整 scope DTO 并在浏览器聚合，project/all 与按需导出仍可能读取大 payload。 |
| 是否影响其他页面 | 不影响；没有修改共享 cache、App Shell、`DEFAULT_MONTH`、后端 gateway 或任何其他页面 read model。 |

## 实现边界

- `web/src/features/cost-statistics/api.ts`
  - `fetchCostStatisticsExplorer()` 恢复为纯 request/map 边界，每次调用真实 fetch。
  - 删除 5 分钟 Map、cache key、get/clear exports、两个零调用 client 和孤立 API DTO。
- `web/src/features/cost-statistics/types.ts`
  - 删除仅由两个旧 client 使用的 month/project statistics types。
- `web/src/pages/CostStatisticsPage.tsx`
  - explorer state 与 canonical scope key 绑定；scope generation 变更时不展示上一 scope。
  - 删除 mount-time all-prefetch effect 和所有 cache clear/read。
  - domain/manual/tag-rule refresh 失效 component-local export reference。
  - project/expense-type 导出按需请求 fresh all reference；time/bank-tag 保持零额外 all I/O。
- tests/mock
  - 增加可控 explorer delay，只用于证明 scope 切换期间旧表格已撤下；不改变生产代码。

## 旧代码删除

已删除：

- `costExplorerCache`、`COST_EXPLORER_CACHE_TTL_MS`、cache entry/key builder；
- `getCachedCostStatisticsExplorer`、`clearCostStatisticsExplorerCache`；
- 页面 mount-time `active:all` export reference effect；
- 页面 cache 初始化、cached-visible-data 分支和 domain/tag-rule cache clear；
- `fetchCostStatisticsMonth`、`fetchProjectCostStatistics`；
- `ApiCostMonthSummaryRow`、`ApiCostMonthStatistics`、`ApiCostProjectRow`、`ApiCostProjectStatistics`；
- `CostMonthSummaryRow`、`CostMonthStatistics`、`CostProjectRow`、`CostProjectStatistics`；
- 只验证旧 module cache 的测试断言。

whole-repo current-code scan：

```text
rg -n "costExplorerCache|getCachedCostStatisticsExplorer|clearCostStatisticsExplorerCache|fetchCostStatisticsMonth|fetchProjectCostStatistics" web/src web/e2e
=> 0 matches
```

仍保留且属于后续状态驱动切片：完整 explorer DTO/客户端聚合、view-specific cursor、请求期 expected-source providers、导出完整 explorer/workbook、cost-local lock overlay、Audit、warmup/runtime/旧后端 class/route 和 cost-tax 混合所有权。禁止把这些未完成项解释为 05-05 回归。

## 测试变化与七类覆盖

更新 `web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` 和 `web/src/test/apiMock.ts`：

- 默认月份首屏只请求 `month=2026-03`，不请求 `month=all`；
- API client 连续两次 explorer 调用执行两次真实 fetch，不保留 module payload；
- scope 延迟请求期间上一 scope 表格退出交互并显示真实 loading；
- time 导出打开不请求 all；
- expense-type 直接打开导出中心时才请求 all；
- 已打开导出中心从 time 切到 project 时才请求 all 并得到完整选项；
- all payload 为 refreshing 时导出中心保持关闭并显示明确反馈；
- 既有 project/expense filters、preview/download、详情、标签规则、五视图、empty/error/non-fresh 行为继续通过。

| 类别 | 结论 |
| --- | --- |
| 1. Business core unit | 不适用；金额、归因、方向、标签选择和状态转换规则未改变。 |
| 2. Service-layer | 不适用；无后端 service、repository、persistence 或 worker 变更。 |
| 3. API contract | 适用；锁定 explorer DTO mapping、project scope 透传和每次调用真实 fetch。 |
| 4. Read model/cache/background job | cache 边界适用；证明前端 module cache 删除、non-fresh fail-closed 且后端 gate 保持唯一 freshness 证明。read model/worker 本轮未改。 |
| 5. Frontend interaction | 适用；覆盖 initial loading、scope loading、lazy reference、non-fresh failure、导出模式切换和既有页面行为。 |
| 6. End-to-end business flow | 既有 explorer→五视图→详情/导出 Chromium 主流程适用并全量通过；本轮不新增跨模块写流。 |
| 7. Existing regression | 适用；成本 API/page 全量 Vitest、10 个成本 Browser 流和生产 build 均通过。 |

## 验证

- `cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx --reporter=verbose`：35 passed。
- `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`：10 passed。
- `cd web && npm run build`：通过；仅保留既有第三方 HeroUI/Tailwind 生成 CSS minify syntax warnings 和主 bundle size warning，不是本轮新增失败。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- whole-repo current-code scan：5 个旧 cache/client 符号均为 0 matches。

## 文档影响

已同步成本模块 boundary I/O、UI state machine、测试矩阵、implementation notes 和唯一主设计文档。文档明确区分：05-05 已关闭前端 TTL cache 与首屏 all-prefetch；完整 explorer/cursor、遮罩、Audit、剩余旧模块和生产 SLO 仍未完成。

## 未完成风险

- explorer/month 仍映射并返回完整 scope DTO；当前月虽不再并行加载 all，但主请求长尾和浏览器聚合仍未由 view-specific cursor 消除。
- project/all 视图与项目/费用类型导出仍可能读取约 765KB 的 `active:all`；本轮只是从首屏移到真实需要时，不是最终 payload 优化。
- 页面尚无 Impeccable 轻量 inert lock overlay、跨用户/focus/BFCache revalidation 闭环。
- cost-owned Audit、当前 source-version mismatch、`<=5s` 门槛、流式导出和剩余后端旧模块删除尚未实施。
- 未运行真实 PostgreSQL EXPLAIN、生产 migration/rebuild、worker drain、Audit 或生产性能门槛；按用户要求只能在所有 thread 合并并明确授权统一部署后验证。

## 共享工作树保护与部署门禁

共享工作树仍有其他 thread 的 Workbench、OA pending、server、worker、repository、文档和前端修改；`web/src/test/apiMock.ts` 也包含其他 thread 的既有 workbench hunks。本轮只追加 cost explorer delay test option，未覆盖、回退或格式化并行修改。

当前状态：`READY_FOR_NEXT_LOCAL_SLICE / DEPLOYMENT_HOLD`。用户提出“所有 thread 完成后统一部署，再做生产性能验证”是合理且必要的：现在部署会把共享工作树中的未完成修复一起带入，无法建立 exact artifact、归因、回滚和性能基线。统一部署前仍须先合并各 thread、全量验证并冻结唯一 release artifact。

## 唯一下一状态

`IMPLEMENTING`

理由：05-05 已关闭首屏 all-prefetch、前端 TTL stale cache、旧 scope 可见和两个零调用 client，但总目标仍有 view-specific cursor/完整 payload、请求期 source I/O、轻量锁定遮罩、Audit、导出、剩余旧模块删除和最终生产性能证据。按主控规则，本摘要不生成下一 prompt；下一 prompt 必须根据本次完成状态和届时共享工作树事实重新决定。
