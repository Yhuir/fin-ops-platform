---
phase: 34-workbench-performance-slo
plan: "01"
status: complete
completed_at: 2026-07-29
production_release: main-632dd2aa-20260729153028
commits:
  - f7a1787af
  - f386fe227
  - 798bbcf7d
  - 632dd2aa3
---

# Phase 34 Summary

## 结果

- 修复 `workbench_relation` scope writer 的 Python method binding，恢复正式 worker 投影链路。
- 相同且仍在进行的 combined-initial 请求复用一个 Promise；完成、失败或带独立
  `AbortSignal` 的请求不缓存、不合并。
- relation action 的 canonical row resolver 接回 active-generation SQL repository，删除
  live facts builder 的误回退。
- confirm/withdraw preview 删除重复 generation proof；active relation lookup 不再加载
  history。
- withdraw scoped snapshot 直接复用既有 `snapshot_for_row_ids(...)`，不再深复制并重建
  进程内全部 relation/history。
- 未接入 Redis：瓶颈是重复 SQL/proof 和进程内全量对象复制，不是稳定 payload 缓存缺失。

## 本地验证

- 后端定向回归：`550 passed`。
- 前端定向回归：`173 passed`，production build 通过。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 通过。

## 生产验证

正式入口 `./scripts/deploy-oa.sh` 已发布
`main-632dd2aa-20260729153028`。API、dispatcher 和 required workers 均为 active；
关联台 Page Audit 为 `pass / fresh / drained`，issues 为空。

浏览器等价 gzip 请求预热 2 次后各采样 20 次：

| 链路 | p50 | p95 | p99 / max |
|---|---:|---:|---:|
| combined initial | 221.362ms | 312.664ms | 317.076ms |
| paired groups 首屏 | 629.546ms | 712.718ms | 836.601ms |
| confirm preview | 190.279ms | 718.591ms | 1058.861ms |
| withdraw preview | 135.048ms | 557.145ms | 580.748ms |
| refresh status | 116.143ms | 138.925ms | 210.273ms |

withdraw preview 修复前同一生产样例 p50/p95 为 `936.006/1216.494ms`；修复后分别降低
约 `85.6%/54.2%`。全部用户交互链路达到 p95 `<=1000ms` 的性能目标。

生产验证只执行 fresh 读取和无副作用 preview，没有对真实财务关系执行 confirm/withdraw
mutation。当前生产 scenario 不具备 `fixture_ownership=test_owned` 和完整恢复检查点，强行写入
不符合数据安全门；正式写入的 CAS、幂等、审计、UoW、历史恢复和 zero fan-out 由本地定向
回归覆盖。
