# 银行明细实施与本地验证

**日期：** 2026-07-20
**状态：** `READY_FOR_UNIFIED_DEPLOYMENT`

## 变更结果

- 已删除 disconnected `bankdetail_write_uow.py`；
- 已删除其唯一 test consumer；
- 已在现有 platform boundary guard 中加入旧 module/class/import 防复活门禁，并锁定三个真实 owner marker；
- 已修正当前银行明细、权限审计和 testing closure 文档；
- 未增加 replacement UoW、API、migration、schema、read model、worker、cache、dependency、feature flag 或 fallback；
- 未修改任何前端实现或其他页面实现。

## TDD 证据

新增 guard 在旧文件存在时先失败，报告：

- `disconnected bankdetail_write_uow.py must stay deleted`
- production source 仍引用旧 class

删除文件后同一 guard 通过。

## 本地验证结果

| 检查 | 结果 |
| --- | --- |
| backend lint | pass |
| bank-details route/application/category/read model/account balance/refresh/architecture/audit/permission | 359 tests passed |
| no-OA application + Workbench integration/UoW regression | 69 tests passed |
| BankDetails frontend API/Page | 2 files，56 tests passed |
| docs gate | pass |
| git diff check | pass |
| runtime import/caller scan | production code/scripts/deploy/web 为零 |

## 七类测试

1. Business core unit：本轮没有新增/改变业务规则，因此不新增；现有 category/auto-category 规则由定向 backend suite 回归。
2. Service-layer：适用；真实 bank application/category side-effect、no-OA application 和 Workbench UoW 已通过。
3. API contract：适用；bank details routes 和 auto-tag/category API 已通过，API shape 未变。
4. Read model/cache/background job：适用；bank detail SQL runtime、account balance、refresh producer 和 architecture guard 已通过。
5. Frontend interaction：适用；BankDetails API/Page 56 项通过，前端实现无 diff。
6. End-to-end integration：适用；本地 no-OA/Workbench 69 项真实 owner 回归通过；完整 production fan-out 留到部署后执行。
7. Existing regression：适用；architecture、permissions/audit、no-OA/Workbench 回归通过，其他页面实现无 diff。

## READY 检查

- `HEAD == origin/main == 39ca39f42922e5893ef11c36d9f0235adf8dab00`（提交前基线）；
- 当前 worktree 只包含本 phase 的删除、guard、docs 和 `.planning` 证据；
- 无 migration、数据库、queue、worker 或生产数据操作；
- 无并发 thread 修改混入；
- 精确提交/部署后仍需完成 production read/write/Audit/isolation gate。

## 发布后门槛

- warm authenticated UI data-visible p95 ≤ 1000ms；
- accounts/transactions/rules/Page Audit p95 ≤ 1000ms；
- controlled fan-out write enqueue-to-fresh p95 ≤ 1000ms，p99 ≤ 3000ms；
- bank-detail fresh 且读取到写后事实；
- Page Audit pass，dirty/outbox/failed queue 为零；
- Workbench/no-OA/turnover 和至少一个不相关页面 smoke 无回归。
