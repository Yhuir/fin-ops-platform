---
phase: 12
slug: etc-tickets-improvements
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-18
---

# Phase 12 — Validation Strategy

> ETC 票据高性能、暂存、OA 草稿可靠性、Audit 和隔离的执行期反馈合同。

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python unittest；Vitest；Playwright |
| **Config file** | `scripts/verify.sh`；`web/vitest.config.ts`；`web/playwright.config.ts` |
| **Quick run command** | `python3 -m unittest tests.test_etc_backend tests.test_platform_runtime_boundary_guards` 与 `cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx` |
| **Full phase command** | 上述 backend/frontend + `cd web && npx playwright test e2e/etc-tickets-flow.spec.ts` + `cd web && npm run build` + `bash scripts/verify.sh lint` |
| **Estimated runtime** | quick 约 1–4 分钟；full phase 约 5–15 分钟 |

## Sampling Rate

- **Tasks 01–06 每个完成后：**只运行该 task 列出的定向 verify。
- **Task 07 发布门：**运行一次 full phase commands 和定向跨页面 regression。
- **生产验证前：**本地 full phase、Audit fixture、request/I/O budgets 必须全绿。
- **最大反馈延迟：**迭代期 4 分钟；禁止每个小改动重复运行全量 CI。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | PAGE-14/PAGE-05 | T-EXT-01 | 无生产 mutation；外部能力不猜测 | source/contract scan | `rg -n "fetchEtcReconciliationTasks|oa_draft_creating|UploadedEtcZipFile" web/src backend/src tests scripts deploy docs` | ✅ | ⬜ pending |
| 12-01-02 | 01 | 1 | PAGE-14/PAR-03 | T-CONTRACT-01 | 权限、状态、I/O budget 先由测试锁定 | unit/API/UI | backend unittest + targeted Vitest | ✅ | ⬜ pending |
| 12-01-03 | 01 | 1 | PAGE-14/PAGE-04 | T-IO-01 | query 只读 canonical、零 object-store list/detail | repository/service | `python3 -m unittest tests.test_etc_backend` | ✅ | ⬜ pending |
| 12-01-04 | 01 | 1 | PAGE-14/PAGE-05 | T-UI-01 | 单选择、明确禁用原因、暂存不丢 | component/API | targeted Vitest + build | ✅ | ⬜ pending |
| 12-01-05 | 01 | 1 | PAGE-14/PAR-01 | T-REPLAY-01 | idempotency/CAS/ambiguous recovery；外部 I/O 锁外 | service/API | backend unittest + lint | ✅ | ⬜ pending |
| 12-01-06 | 01 | 1 | PAGE-14/PAR-03 | T-AUDIT-01 | stuck/缺关系 fail closed；旧链 guard | Audit/guard | backend unittest + diff check | ✅ | ⬜ pending |
| 12-01-07 | 01 | 1 | PAGE-14/PAGE-04/PAR-02 | T-RELEASE-01 | 七类回归、SLO、混合负载、回滚门 | integration/E2E/perf | full phase commands | ✅ | ⬜ pending |

## Wave 0 Requirements

- [ ] 在 `tests/test_etc_backend.py` 增加三 bucket、OA command、Audit 和 query I/O budget fixtures。
- [ ] 在 `web/src/test/EtcTicketManagementPage.test.tsx` 增加首屏 request/duplicate detail/staged durable 行为保护。
- [ ] 在 `tests/test_platform_runtime_boundary_guards.py` 增加旧 ETC 首屏链静态 guard。
- 现有 unittest/Vitest/Playwright 基础设施足够，不安装新 framework 或 dependency。

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OA provider idempotency/marker lookup 能力 | PAGE-14 | 外部 OA 合同不能由本地 mock 证明 | 使用 provider 文档或获准的非破坏性 probe，记录请求/响应合同，不创建生产业务草稿 |
| 当前生产 stuck batch 结果核实与恢复 | PAGE-14 | 必须由真实 OA 外部证据决定，不能自动猜测 | 先定位稳定 marker/draft；确认存在则采纳，确认不存在才允许 failed/retry；全程审计和 expected version |
| 生产 p95/p99 与混合页面隔离 | PAGE-14/PAGE-04 | 本地环境不能代表真实 Nginx/PostgreSQL/object storage/OA 网络 | 部署授权后按 baseline→canary→可回滚测试批次→混合负载顺序执行并保存样本 |

## Validation Sign-Off

- [x] 所有任务都有自动 verify。
- [x] 没有连续三个任务缺自动反馈。
- [x] Wave 0 仅增加现有 test files 中的必要合同，不新增测试框架。
- [x] 命令不使用 watch mode。
- [x] 迭代反馈目标小于 4 分钟；full phase 只在发布门运行一次。
- [x] `nyquist_compliant: true` 已设置。

**Approval:** pending execution
