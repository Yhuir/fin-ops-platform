---
phase: 36-right-drawer-motion-production-closure
verified: 2026-07-31T18:13:36Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
gaps: []
release:
  name: main-d6266b05-20260801015117
  git_commit: d6266b053c9669aec35af841f26e6f77405c23dc
  gate_status: PASS
---

# Phase 36：全站右侧抽屉滑入动效与详情链路生产闭环验证

**Phase Goal：** 所有 modal 右侧抽屉通过唯一的 HeroUI/CSS motion contract 从右侧完整滑入并原路退出，删除绕过共享边界的旧壳，同时发布关联台同 generation 详情修复并取得生产正确性、隔离性和性能证据。

**验证结论：PASSED。** 本地实现、深度代码审查、目标测试、`origin/main`、生产 release、自动发布门禁、认证只读详情探针和真实 Chromium 动画采样已经形成完整闭环。

## Goal Achievement

| # | Observable truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Modal 右抽屉统一经 HeroUI right placement 完成 100% → 0 → 100% 位移，进入 240ms、退出 180ms，空间动画只使用 `translate`，并支持 reduced motion。 | ✓ VERIFIED | `AppDrawer.tsx` 唯一组装 `Drawer.Backdrop -> Drawer.Content placement="right" -> Drawer.Dialog`；`styles.css` 把 motion 绑定到真实移动的 dialog。6/6 本地 Chromium 测试和生产几何采样均通过。 |
| 2 | OA 关联支出流水和流水规则标签管理迁移到 `AppDrawer`，业务 I/O、权限、表单、loading/error、写时序和 busy/race 合同不变。 | ✓ VERIFIED | 目标 Vitest、Chromium 以及生产真实 OA candidate GET/关闭路径通过；生产验证未执行保存/关联写操作，全部 mutation 计数为 0。 |
| 3 | 税金已认证结果保持 mounted non-modal complementary rail，只动画 transform/opacity，收起时 inert/aria-hidden，焦点保留在 toggle。 | ✓ VERIFIED | 生产 10 段收起/展开采样全部完整位移、CLS=0、总体帧 p95 18.5ms；3 轮业务 endpoint 隔离断言为 0，`transition-property` 为 `opacity, transform`。 |
| 4 | 关联台详情从同一 active generation 读取完整 row，只对 version conflict 最多恢复一次，不盲重试 missing/invariant/unavailable。 | ✓ VERIFIED | 生产真实详情返回 200/fresh 且响应 version 与请求 expected version 相同；20 次热读全部 200，p95 67.707ms；只读 stale version 返回 409，缺失 row 返回 404。前端 bounded retry 和后端 invariant/unavailable 分支由本地目标测试保护。 |
| 5 | 冲突旧动画、旧自定义 shell、重复 Escape owner 和过期 fallback 已删除；没有新增动画依赖或第二套抽屉抽象。 | ✓ VERIFIED | 深度代码审查最终 clean；whole-source scan 与依赖清单未发现旧 28px/22px keyframe、永久 `will-change`、OA/bank-flow 并行 shell 或新 animation package。 |
| 6 | 目标门禁、推送后的 `main`、精确生产 release、认证详情探针和浏览器测量共同证明正确性、页面隔离、健康度与性能。 | ✓ VERIFIED | `origin/main` 和部署候选均为 `d6266b053c9669aec35af841f26e6f77405c23dc`；release `main-d6266b05-20260801015117` 的 pre/T+0/T+60/T+300 全部 PASS，生产 `/health` 为 ready 且 runtime identity consistent。 |

**Score：6/6 truths verified。**

## Release Evidence

- Remote main：`d6266b053c9669aec35af841f26e6f77405c23dc`。
- Active release：`main-d6266b05-20260801015117`。
- `/health`：`status=ready`，`runtime_release.consistent=true`，工作目录、package path、`PYTHONPATH` 和 `RELEASE.json` 全部指向该 release，`problems=[]`。
- 自动门禁：pre、T+0、T+60、T+300 的 domain contract audit、page canonical/System Audit、RabbitMQ metrics/topology、runtime sync closure 和 worker inventory 全部 PASS。
- 最终强约束：dirty scope、pending/publishing/failed outbox、durable/RabbitMQ dead letter、required worker not ready、unknown worker 全部为 0；`queue_stable_after_300_seconds=true`，`terminal_publish_reconciliation_stable=true`。

第一次 candidate `main-d6266b05-20260801014252` 在 T+0 因部署窗口内 Workbench `refreshing`、1 个 processing/publishing 瞬态以及既有 pending-invoices p95 1010.999ms 自动 fail closed，并成功回滚到 `main-825d3401-20260731225415`。等待生产基线恢复 fresh、空队列和 sub-second 后，第二次用同一 Git SHA 发布并通过全部稳定性窗口；没有降低 SLO、跳过检查或留下半发布状态。

## Production Browser Evidence

认证 Chromium 在 1366×900 viewport 下只读打开和关闭以下生产表面：

- 流水规则标签管理
- 成本统计标签规则
- 银行明细自动标签规则
- 发票与支付状态规则
- OA 关联支出流水
- 关联台真实详情
- 税金已认证结果 complementary rail

结果：

- 五类 modal 规则/OA 抽屉均完成 1.000 panel-width 右侧进出，最终右边缘与 viewport 一致。
- 单段 modal 帧间隔 p95 为 16.8–18.6ms；所有抽屉诱发 CLS 均为 0。
- 关联台连续 5 次真实开关共 10 段：每次进入/退出均为 1.000 panel-width，最终右边缘 1366/1366；退出 `translate` transition event 为 0.18s；合并帧 p95 18.6ms。
- 税金右栏 10 段合并 313 个 frame interval：p50 16.7ms、p95 18.5ms，10/10 完整位移，CLS 全 0。
- 所有 modal 关闭业务 API 增量为 0；税金 toggle 对 `/api/tax-offset` 的业务请求增量为 0。观察到的 `/api/app-health` 和 `/api/background-jobs/active` 是全局周期性只读健康请求，不由抽屉状态触发。
- 全部生产浏览器验证 mutation 请求为 0。
- Headless Chromium 在部分重内容 drawer mount/unmount 窗口记录到 52–120ms long task，税金首次采样最大 194ms；它们没有改变完整位移、终点、CLS 或 p95。该尾部抖动保留为非阻塞监控事实，没有隐去或用 retry 覆盖。

## Production Workbench Detail Evidence

- 真实可见 row 的 UI 详情请求：200，`read_model_status=fresh`，`expected_read_model_version` 存在且与响应 `read_model_version` 完全一致。
- 同一真实详情 URL 连续 20 次热读：20/20 为 200；p50 58.809ms，p95 67.707ms，max 159.872ms，显著低于 1s 目标。
- 关闭详情抽屉后的业务 API 增量：0。
- 只读 stale-version 探针：409 `workbench_read_model_version_conflict`。
- 只读 missing-row 探针：404 `workbench_row_not_found`。
- 未通过破坏生产 read model、制造数据库故障或暂停 worker 来强制触发生产 503；`workbench_row_detail_invariant_broken` 和 `workbench_detail_unavailable` 的 no-retry 合同由 5 个目标后端测试和 2 个目标前端测试验证。

## Verification Commands

| Gate | Result |
| --- | --- |
| 5 个目标 Vitest 文件 | 118/118 passed |
| `web/e2e/drawer-motion.spec.ts --project=chromium` | 6/6 passed |
| Workbench backend generation/invariant/API/SQL target suite | 240 passed |
| `npm --prefix web run build` | passed；仅有既有 HeroUI 生成 CSS 空 `:is()` minifier warning |
| `bash scripts/verify.sh lint` | passed |
| `bash scripts/verify.sh docs` | passed |
| `git diff --check` | passed |
| `e2e:production-shell` | 16 个核心 route 全部通过，0 mutation |
| `e2e:production-admin` | AppHealth 页面通过，0 mutation |
| `scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh` | second candidate PASS through T+300 |

## Seven-Category Test Assessment

1. **Business core：适用。** 关联台 generation conflict/missing/invariant/unavailable 决策由目标后端和前端测试覆盖；抽屉本身不新增业务规则。
2. **Service layer：适用。** `WorkbenchQueryFacade` 的 exact-generation、纯读和不 enqueue 合同由目标 service/repository 测试覆盖；drawer shell 不触碰 service。
3. **API contract：适用。** 生产 200/409/404 与本地 503 映射均有证据，且校验具体 error/read-model 字段。
4. **Read model/cache/background job：适用。** 同 generation SQL、freshness/invariant 测试与生产 release gate 的 queue/worker/read-model 稳定性共同覆盖。
5. **Frontend component/interaction：适用。** 118 个目标 Vitest 与 6 个 Chromium motion/lifecycle 测试覆盖 loading/error/busy/open/close/reduced-motion/inert/focus。
6. **E2E business flow：适用。** 本地确定性 OA/bank-flow/Workbench/tax 链路加生产只读真实 OA candidate、Workbench detail 和 16-route smoke 覆盖关键跨模块读路径；没有对生产业务关系执行写操作。
7. **Existing regression：适用。** 共享 drawer、OA、bank-flow、cost、bank auto-tag、invoice rules、tax、Workbench、build/lint/docs 以及 16 个生产 route 均受保护。

## Remaining Untested Risk

唯一未在生产主动制造的分支是 invariant/unavailable 503，因为安全触发需要破坏 read model、停止依赖或制造数据库异常，不属于只读生产验证授权；本地自动化已经覆盖其显式 no-retry 合同。生产 headless Chromium 的少量 long-task 尾部建议继续观察，但当前所有既定验收阈值均通过。

---

_Re-verified: 2026-07-31T18:13:36Z_
_Verifier: main orchestrator after exact production deployment_
