---
phase: 37-app-shell-sidebar-identity
verified: 2026-08-01T03:16:06+08:00
status: passed
score: 5/5 must-haves verified
gaps: []
release:
  name: main-99a7b536-20260801030234
  git_commit: 99a7b536a914f2b854b5004d1fdc4921872bd4a2
  gate_status: PASS
---

# Phase 37：App Shell 侧栏生产验证

**结论：PASSED。** 本地实现、自动测试、`origin/main`、精确生产 release、16-route smoke、AppHealth 和真实 Chromium 性能/隔离性验证形成闭环。

## Goal Achievement

| # | Observable truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | 桌面、折叠和移动侧栏使用固定品牌区、独立滚动导航和固定 OA 账号区，保持 232/72px 合同。 | ✓ VERIFIED | 组件/CSS 负向测试、responsive Chromium、生产桌面与 390×844 移动开关通过。 |
| 2 | 账号只来自 SessionContext，显示真实 OA 用户，打开详情不新增请求或图片 I/O。 | ✓ VERIFIED | 生产真实身份渲染；`/api/session/me` 总计 1 次，打开账号弹层增量 0；无远程头像。 |
| 3 | 静态本地图标保留 App Status 入口，旧旋转实现完全不可达。 | ✓ VERIFIED | 生产 computed `animation-name=none` 且状态弹层可打开；源码 negative scan 和测试阻止旧 class/keyframes 回归。 |
| 4 | 页面名称、路由、权限和业务 I/O 不变，无新增依赖或并行路径。 | ✓ VERIFIED | package/lock 无差异；全量 894 tests、16-route production smoke 与 mutation=0 通过。 |
| 5 | 性能、健康、remote main 与生产 release 达标。 | ✓ VERIFIED | 生产 6 段合并 frame p95 19.56ms、CLS 0；账号 47.4/199.5ms；release 四轮门禁 PASS。 |

## Production Evidence

- Remote candidate / active Git SHA：`99a7b536a914f2b854b5004d1fdc4921872bd4a2`。
- Active release：`main-99a7b536-20260801030234`。
- pre、T+0、T+60、T+300：domain contract、page canonical/System Audit、RabbitMQ、runtime sync、worker inventory 全部 PASS。
- Queue/runtime：dirty、pending、publishing、failed、dead letter、unknown/not-ready worker 全部为 0，`queue_stable_after_300_seconds=true`，无回滚。
- Route shell：16 个核心页面均未卡 session gate 或 loading，mutation 0。
- AppHealth：admin-only 页面成功加载真实 dashboard，mutation 0。
- 浏览器：真实 OA 身份、账号 popover、静态状态入口、桌面 6 段开关、移动 drawer 全部通过；账号新增 session I/O=0，总 mutation=0。
- 性能：账号 first-visible 47.4ms、settled 199.5ms；侧栏 149 intervals，p50 16.7ms、p95 19.56ms、max 28.2ms、CLS 0。

## Remaining Untested Risk

Figma Make 正式导出资产仍不可读，因此没有生产像素 diff；行为、布局合同、响应式、无障碍与性能均已自动化/生产验证，正式图标可在不改变 I/O 的前提下原位替换。

