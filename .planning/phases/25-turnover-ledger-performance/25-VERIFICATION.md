# 外部往来款管理验证记录

日期：2026-07-20

## 发布前门禁

- 生产读取基线：shell p95 `117.557ms`、grouped p95 `284.012ms`、tag-selection p95 `177.869ms`、Page Audit p95 `323.220ms`；20/20 2xx/fresh/0 enqueue。
- 真实 PostgreSQL：`tests.test_turnover_ledger_postgres_integration` 3/3 passed；临时库应用 0001–0113 后自动删除。
- 后端目标回归：587/587 passed。
- 前端目标回归：5 files、46/46 passed。
- lint：passed。
- docs：passed。
- `git diff --check`：passed。
- 生产代码旧链扫描：`legacy_payload_builder`、`clear_turnover_ledger_rows`、v5 schema 和旧 Python turnover summary/source-version helpers 为零。

## 七类测试判定

1. Business core：适用；真实 PostgreSQL 覆盖显式/旧 fallback 金额、方向、family/status、空筛选和分页。
2. Service：适用；query fail-closed、mixed source versions、refresh enqueue、narrow port。
3. API contract：适用；turnover API 回归包含 grouped/list/freshness/权限及 mutation response。
4. Read model/cache/job：适用；PostgreSQL payload-only、child dirty 聚合、projection refresh、manifest/guards。
5. Frontend：实现不变；既有 TurnoverLedger API/Page/overlay/barrier/domain event 46 项回归。
6. E2E：本地主链由 API/UoW 覆盖；生产可逆 confirm/withdraw 待部署后执行。
7. Existing regression：适用；manifest、read-model architecture、platform runtime guards 和部署后跨页 Audit。

## 待发布后补齐

- 精确 code SHA / release。
- v6 turnover shard rebuild/drain。
- 40 样本 post-deploy 性能。
- 直接与交叉 Page Audit。
- 安全可逆写后 committed-to-fresh；若 fixture 不再安全，记录为最终系统门而不制造事实。

## release 7c25e9578 第一轮生产写门

- 部署成功，旧 `turnover-ledger-secondary` worker 已由 deploy control 退役，registry 只保留单一 `turnover-ledger` owner。
- 两轮安全可逆 confirm → fresh → withdraw → fresh 均完成，最终 fixture 恢复 `unlinked`，无 active relation 残留。
- 热态 response-to-fresh：confirm `1.456s`、withdraw `1.443s`，已满足 `<=2s`；热态 command：confirm `1.759s`、withdraw `2.684s`，未满足 `<=1s`。
- 部署后首轮 confirm 受冷态数据库/服务启动拖累为 `6.669s`，超过 hard max；因此该 release 不判定闭环，也不进入下一页面。
- AppHealth 请求拆分显示热态 relation command 数据库时间约 `0.67s`，其余同步耗时集中在 canonical repository save 后的全局进程镜像复制与重建。

## changed-case 镜像优化本地门

- domain + adapter + workbench relation command/UoW/idempotency + turnover domain/UoW/API/query/read-model：`414 passed + 28 subtests`。
- architecture guard + relation projection/read facade + write-operation smoke/SLO：`332 passed + 69 subtests`。
- 新回归明确证明 changed-case apply 不调用全局 `snapshot()`，并覆盖目标 case 删除、history 替换及无关 case/history 保留。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。
- 下一门：提交并部署精确 SHA，待 readiness 稳定后复用相同两轮可逆写探针；command p95 `<=1000ms`、response-to-fresh p95 `<=2000ms`、hard max `<=3000ms` 才能继续最终 40 样本与直接/交叉 Audit。

## release b4fce65f8 第二轮生产写门

- 三轮安全可逆 confirm → fresh → withdraw → fresh 均完成，最终 fixture 为 `unlinked`，无恢复操作或 active relation 残留。
- 热态 confirm command `0.804–1.025s`，withdraw command `1.530–1.757s`；热态 response-to-fresh `1.414–1.721s`。
- 首轮 confirm command `5.680s`、response-to-fresh `6.134s`；严格门仍失败，因此不进入下一页面。
- AppHealth：confirm 23 queries，热态数据库约 `0.708s`；withdraw 17 queries，数据库 p50 `0.532s`、p95 `0.973s`。调用图进一步定位 withdraw 请求前置 active-case 校验仍复制全局 snapshot/history。
- 下一修复只增加 canonical active-case 单行读取并删除 obsolete after-apply callback；事务 mutation、history restore、refresh fan-out 与 API 不变。

## release f18f62136 第三轮生产写门

- 三轮安全可逆 confirm → fresh → withdraw → fresh 均完成；最终 fixture 为 `unlinked`，无恢复操作或 active relation 残留。
- withdraw command 为 `0.787s`、`0.999s`、`0.824s`，response-to-fresh 为 `1.72–1.86s`；active-case 窄读取已消除 withdraw 的全局 snapshot/history 复制。
- confirm 首轮 command/response-to-fresh 为 `6.030s` / `6.035s`；两轮热态 command 为 `1.004s` / `1.211s`，response-to-fresh 为 `1.028s` / `2.253s`。严格 command、freshness 与 hard-max 门仍失败。
- AppHealth 记录 confirm 为 23 queries，服务 p50 约 `1.075s`、数据库 p50 约 `0.902s`，冷态数据库约 `5.77s`；调用图定位通用 overlap load 与 full case-history replacement 仍在 confirm 热链。
- App Health 在探针后为 15/15 read models fresh、28/28 workers ready/idle、queue 0、write safety ready；该健康状态不替代失败的写性能门。
- 下一修复只把 confirm overlap 改为 active/history-free 窄读，并把所有在线 command history 改为 append-only delta；不改变 API、状态机、read model、worker 或其他页面事实。

## command history append-only delta 本地门

- relation domain/adapter/command/UoW/idempotency、turnover domain/UoW/API/query/read-model、PostgreSQL repository 与 architecture guards：`696 passed + 72 subtests`。
- 共享调用方隔离回归：batch accounting/matching/no-OA/exception `94 passed + 4 subtests`；pending invoice/OA promotion/no-OA application/auth idempotency `107 passed + 2 subtests`。
- 真实 disposable PostgreSQL 17 应用 0001–0114 后，25 条旧 history + 1 条新 event 最终为 26 条；重复 delta 保持 26，active overlap 返回 relation 且不返回 history。临时数据库自动删除。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。
- 下一门：提交并部署精确 SHA，执行三轮可逆写探针；任何 command p95 `>1000ms`、response-to-fresh p95 `>2000ms` 或 hard max `>3000ms` 均继续本页，不进入税金抵扣。
