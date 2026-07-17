---
phase: 05-cost-statistics-improvements
plan: 07
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-07 Summary：成本页轻量 freshness 交互锁

## 结果

`PASS`。`/cost-statistics` 已使用 cost-local、非 dialog 的轻量交互锁闭环 loading、refreshing、stale、unavailable、request error 与 tag-rules barrier。只有当前 request payload 明确 fresh，且 App Status 当前精确成本 scope 没有 non-fresh 反证时才开放业务操作。

本轮没有修改后端 API、read model、worker、Audit、共享 App Status/StatePanel/AppDrawer 语义或其他页面；没有部署、访问生产、stage、commit、branch、push、PR、stash、reset 或 clean。

## 实施边界

- `CostStatisticsPage` 派生唯一 `effectiveCostPageState`，精确匹配 `readModelKey=cost_statistics` 与当前 `active:month|all` scope；其他月份/其他 read model 不会误锁。
- 视图/范围、header actions 和内容使用原生 `inert` + `aria-busy`；标题、Audit、App Shell 和导航在锁定边界外。
- 状态轨是页面内 `role=status`，失败/不可用时仅开放 `重新检查`；遮罩使用 20% page 色，即约 80% 透明，`pointer-events:auto`、无 card/blur/shadow/动画。
- 进入锁定关闭 detail/export portal 与范围 popover，清除 preview/detail，并 abort 可取消的 detail/export-reference 请求；晚到详情响应不能重开旧 portal。
- tag-rules drawer 保留壳与草稿，body/footer 在 non-fresh 时 inert；保存中继续沿用既有 operation barrier。
- blur→focus、hidden→visible 与 BFCache `pageshow.persisted=true` 先清除可操作 payload，再重走后端 gate；焦点只在原本位于成本业务区域时迁移到状态轨，fresh 后安全恢复。

## 旧链路删除证据

current runtime/test scan 结果：

- 旧 loading/non-fresh 文案 `正在加载成本统计数据...`、`成本统计读模型正在刷新...`、`成本统计读模型不是最新...`、`成本统计数据暂不可用，请等待...`：零命中。
- 旧前端 cache/client 符号 `getCachedCostStatisticsExplorer`、`clearCostStatisticsExplorerCache`、`costExplorerCache`、`fetchCostStatisticsMonth`、`fetchProjectCostStatistics`：零命中。
- runtime 中 `cost-lock-breathe` / `cost-lock-fade-in`：零命中；测试只保留一个负向 guard，防止动画回归。
- 页面仍有的三个 `.state-panel` 只服务 fresh payload 下的 load-more error、detail loading 和真实 fresh empty；不存在首屏/non-fresh 双状态 UI。
- overlay 唯一生产挂载点在 `CostStatisticsPage`，唯一生产 selector 是 cost-local `.cost-lock-overlay`；没有全局 overlay 或 `backdrop-filter`。

## 测试与七类责任

1. Business core unit：不适用；金额、归因、分类、权限决策和业务状态转换未改。
2. Service-layer：不适用；service、repository、queue、cache、worker 和 Audit 未改。
3. API contract：本轮 shape/status 不变；复跑 `CostStatisticsApi.test.ts` 的现有 explorer/freshness/cursor contract。
4. Read model/cache/background job：间接适用；新增前端对 API/App Status non-fresh 的 fail-closed 与 exact-scope 隔离测试，后端 gate/CAS 未改。
5. Frontend component/interaction：适用；覆盖 initial/error/refreshing/stale/unavailable/fresh、inert、retry、焦点、drawer、portal、BFCache 和静态视觉合同。
6. End-to-end：适用；Chromium 覆盖真实 computed overlay、native inert、三种 non-fresh、retry、精确/旁支 App Status scope、五视图、详情、导出、大表和窄屏。
7. Existing regression：适用；现有成本页全部 Chromium flow 通过；默认 mock 不向其他页面注入 cost App Status domain。

## 验证证据

- `cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx src/test/CostStatisticsApi.test.ts --reporter=verbose`：`37 passed`。
- `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium --reporter=line`：`12 passed`。
- `cd web && npm run build`：通过；仅有既有第三方 generated CSS selector warning 与主 chunk size warning。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- old text/symbol/motion scan：生产旧文案、旧 cache/client 与遮罩动画 runtime 零命中。

## 文档影响

已更新成本统计 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md`、`implementation-notes.md` 与唯一主设计 `performance-freshness-lock-overlay-design.md`，明确 05-07 已完成和剩余门禁。

## 剩余风险与下一状态

本轮只关闭 UI freshness lock，不冒充整体任务闭环。仍需后续单一 prompts 分别处理：成本 Audit 正确性/性能、请求期 expected-source provider、导出长尾和全部剩余后端 legacy owner；统一部署后还需真实 migration/rebuild、App Health SSE/fallback、跨设备收敛、`EXPLAIN (ANALYZE, BUFFERS)`、浏览器/API SLO、worker/queue/Audit 证据。

因此 next state 为 `IMPLEMENTING`，整体 `/goal` 保持 active，部署保持 `DEPLOYMENT_HOLD`。本轮不生成 `05-08`。
