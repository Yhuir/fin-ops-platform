---
phase: 37-app-shell-sidebar-identity
plan: "01"
subsystem: ui
tags: [react, heroui, sidebar, session, playwright, performance]
provides:
  - Clear 64/36/44/72px sidebar hierarchy with fixed brand and OA account zones
  - Current OA identity presentation through the existing SessionContext
  - Static local brand status mark with the existing App Status popover
  - Removal of rotating status and inherited sidebar-width state paths
affects: [app-shell-navigation, reconciliation-workbench]
tech-stack:
  added: []
  patterns: [local shell state boundary, session-owned identity, on-demand DOM geometry]
key-decisions:
  - "Reuse HeroUI Popover and SessionContext; add no API, avatar request, dependency, or account action."
  - "Keep 232px/72px external widths but do not animate width/flex layout properties."
  - "Read the actual sidebar geometry only when the Workbench filter opens; delete the inherited CSS width state."
requirements-completed: []
completed: 2026-08-01
---

# Phase 37 Plan 01：App Shell 侧栏身份与层级收口

侧栏现已使用固定品牌区、独立滚动导航和固定 OA 账号区；账号来自现有会话，静态品牌图标继续打开全局状态弹层，旧旋转动画和旧宽度状态链已删除。

## 完成内容

- 保留全部页面名称、路由、顺序、权限和 `232px / 72px` 外部宽度合同，桌面行高调整为 36px、移动抽屉为 44px，导航间距与字体层级统一。
- 新增轻量 `AppSidebarAccount`，直接消费 `SessionContext`；展示当前 OA displayName/username/department，弹层不重新请求 session，也不加载远程头像。
- 用隔离的本地 SVG 和静态状态点替换旋转圆环；原 App Status popover、键盘和权限行为不变。
- 将展开状态限制在 `StatefulAppSidebar`，避免开关侧栏重新渲染整棵业务页面；删除 width/flex/max-width/max-height 动画。
- 删除 `--sidebar-width`、导出的宽度常量和 Workbench 对继承状态的读取；筛选弹层只在定位时读取真实侧栏几何。
- 未新增 npm 包、API、后端逻辑、read model、worker、缓存、迁移或兼容 fallback。

## 验证

- 全量前端 Vitest：73 files，894/894 passed。
- 最终受影响目标测试：5 files，46/46 passed。
- App Shell Chromium：6/6 passed；最终 responsive：2/2 passed。
- `npm --prefix web run build`、`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 全部通过。
- 本地 Chromium：账号首次可见 27.1ms、稳定 163.6ms；侧栏 frame p95 22.04ms、CLS 0。
- Whole-source negative scan：生产源码中的旧旋转 track/sweep/keyframes、`--sidebar-width` 和宽度常量均为 0；依赖清单无变化。

## 生产闭环

- 候选提交：`99a7b536a914f2b854b5004d1fdc4921872bd4a2`，已推送 `origin/main`。
- Active release：`main-99a7b536-20260801030234`；pre、T+0、T+60、T+300 全部 PASS，未回滚。
- dirty scope、pending/publishing/failed outbox、dead letter、unknown/not-ready worker 均为 0；System Audit、domain contract、runtime sync 和 worker inventory 全部通过。
- 生产 16-route shell 与 admin AppHealth smoke 均通过，全程 mutation 0。
- 生产 OA 身份真实渲染；账号弹层首次可见 47.4ms、稳定 199.5ms，新增 session 请求 0。
- 生产侧栏 6 段、149 个 frame interval 合并 p50 16.7ms、p95 19.56ms、max 28.2ms、CLS 0；移动菜单与状态弹层均可正常打开关闭。

## 七类测试评估

1. **Business core：不适用。** 未改变金额、状态、匹配、权限决策或业务规则。
2. **Service layer：不适用。** 未改变后端 service/repository/persistence/audit/job。
3. **API contract：不适用。** 没有新增或修改请求、响应 shape；只复用既有 session DTO。
4. **Read model/cache/background job：不适用。** 未改变 freshness、queue、worker 或缓存。
5. **Frontend component/interaction：适用且已覆盖。** Vitest 与 Chromium 覆盖 loading/unavailable/forbidden identity、开关、弹层、移动抽屉、reduced motion 与性能。
6. **E2E flow：适用于 App Shell 读链路且已覆盖。** 生产 16-route、OA session、App Status 与移动抽屉均以只读方式验证。
7. **Existing regression：适用且已覆盖。** 全量 894 tests、构建、lint/docs、WorkBench 定位测试与生产 route shell 共同保护现有页面。

## 剩余风险

- 用户提供的 Figma Make 原图文件缺失，因此本地 SVG 按已批准视觉方向实现，不能宣称像素级复刻；资产已隔离，取得正式导出图后可原位替换而不改变组件或 I/O。
- 生产页面初始业务数据并发加载期间的一次诊断采样为 p95 28.38ms；页面稳定后的静止基线 p95 19.92ms，最终 6 段交互合并 p95 19.56ms。该启动期尾部抖动保留为监控事实，没有通过重试隐藏。

