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

## release 8c6ffcb744 第四轮生产写门

- 三轮 confirm→fresh→withdraw→fresh 业务断言全部通过；最终 fixture 为 `unlinked`，无 active relation 或恢复残留。
- command：confirm `0.800–1.639s`，withdraw `0.918–1.800s`，p95/max `1.800s`，未达到 `<=1s`。
- response-to-fresh：首轮 confirm `5.802s`，其余 confirm `1.288–1.938s`，withdraw `1.391–2.116s`；p95/max `5.802s`，未达到 `<=2s` / hard max `<=3s`。
- AppHealth recent handler：`workbench_relation` p95 `862.121ms`，`turnover_ledger` p95 `1406.471ms`。首轮 timeline 中两个 turnover month scopes 在同一 worker 串行收敛，第二个 scope 到约 `5.802s`。
- 旧链定位：relation-only 事件已有 `relation_deltas + row_ids`，但 handler 忽略；projection 仍分页读取 scope 全部 rows，重套 relation context，再通过 `save_turnover_ledger_rows` delete/rewrite 整月。

## relation-only month delta 本地门

- Worker/projection/query/UoW/API/PostgreSQL repository/manifest/architecture：`541 passed + 72 subtests`。
- Audit/manifest/write SLO targeted：初次 `118 passed + 236 subtests`，仅 manifest 精确 port set 因新增两个正式 delta I/O 按预期失败；更新合同后 manifest `25 passed + 211 subtests`。
- 真实 disposable PostgreSQL 17：应用 0001–0115，`tests/test_turnover_ledger_postgres_integration.py` 5/5 passed；证明 overlap 只改目标 payload、非目标业务 payload 不变、同月 row/table source versions 一致；临时库自动删除。
- repository boundary：relation delta 不执行 `delete from read_model.turnover_ledger_rows`；完整 scope save 仍保留给 own-source/repair/首次构建。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。
- 下一门：提交、push main、部署精确 SHA并应用 0115；再运行三轮生产可逆探针。性能任一门失败则不进入下一页。

## release 75565d67e 第五轮生产写门

- 部署 release `main-75565d67-20260720145643` 成功，migration 0115 约 `39ms`；15/15 read models fresh、28/28 workers ready/idle、queue 0、write safety ready。
- 三轮可逆业务断言全部通过，最终 fixture 为 `unlinked` 且无需 recovery。
- `turnover_ledger` relation delta 已通过：recent 12 样本 p50/p95/p99 `72.853/126.677/143.571ms`，每轮首次 barrier 检查两个 turnover month scopes 均 fresh。
- 总门仍失败：command p95/max `5313.061ms`；response-to-fresh p95/max `6703.945ms`。`workbench_relation` recent p50/p95/p99 `602.831/3178.564/5376.672ms`，慢点位于整月 source-version/relation扫描而非 turnover projection或 operation barrier。
- API telemetry：confirm 3 样本数据库 p50/p95 `753.818/5132.376ms`、21 queries；withdraw `935.545/1497.237ms`、15 queries。先删除已证实的后台整月 I/O再复测同步 command，避免叠加未经证明的 command重构。

## shared relation-only delta 本地门

- Worker：显式 relation delta 进入专属 handler；普通 row ids继续通用 partial；force/`all`不进入 delta。
- Projection/repository：版本 query 只读取 scope proof + impacted canonical relation max；active relation和 pending claim只按 affected row ids读取；输出仍通过 `save_workbench_relation_distribution_rows`。
- Workbench relation/turnover/UoW/API/repository/manifest/scope/architecture targeted：`605 passed + 283 subtests`。
- 真实 disposable PostgreSQL 17：应用 0001–0115 后 `tests/test_turnover_ledger_postgres_integration.py` 6/6 passed；证明 withdrawn canonical relation也能推进 relation proof、其他 source versions保持不变；临时数据库自动删除。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。

## release 21d5490e3 第六轮生产写门

- 部署 release `main-21d5490e-20260720154514` 后，三轮 confirm→fresh→visible→withdraw→fresh→visible 业务断言全部通过；最终 fixture 为 `unlinked`，无需 recovery。
- response-to-fresh p95/max `934.515ms`，response-to-visible p95/max `1699.211ms`，均已达到 `<=2000ms` / hard max `<=3000ms`；`workbench_relation` recent p50/p95/p99 `107.620/290.120/316.764ms`，`turnover_ledger` `68.264/141.507/181.189ms`。
- command p95/max `3662.382ms` 仍失败；去掉首轮冷样本后 confirm/withdraw 稳定在约 `1.13–1.32s`，仍高于 `1000ms`。API telemetry 为 confirm 21 queries、withdraw 15 queries，数据库时间仍占主要部分。
- 剩余同步重复 I/O：月份逐笔读取 canonical bank facts；selected bank rows 被 expected-version 与 closure preview 各读一次；Turnover UoW 事务外 idempotency get 后事务内 reserve；cash-closure withdraw 在 command 前后重复 relation snapshot/freshness。

## command 重复 I/O 收口本地门

- 月份改为单次 `list_transactions_by_ids(...)`；request-scoped selection port 复用 selected bank facts；幂等只保留事务内原子 reserve；cash-closure withdraw 复用 owner-bound preparation。未新增 API、schema、worker、queue、跨请求 cache 或 fallback。
- API/UoW/Workbench command 定向回归：`253 passed`；扩大到 relation/domain/read-model/architecture：`635 passed, 3 skipped, 285 subtests passed`。
- disposable PostgreSQL 17 实际应用 0001–0115：`10 passed + 6 subtests`；事务幂等、durable outbox/dirty scope、relation delta 均通过，临时数据库自动删除。
- whole-repo production scan：旧 `TurnoverLedgerBankRowStalePreconditionPort` 为零；Turnover UoW 事务外 `_idempotency_get(...)` 为零；cash-closure withdraw 不再调用旧 current-relation helper，该 helper 仅由仍在使用的其他校验链保留。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：通过。下一门为提交、push、部署精确 SHA 后复用同一三轮可逆探针；全部性能门通过后才执行 40 样本、直接/交叉 Audit，并停在本页闭环节点。

## release ffdcfcdcb 第七轮生产写门

- 部署 release `main-ffdcfcdc-20260720164444` 后三轮 confirm/withdraw 业务与恢复断言全部通过，最终 fixture `unlinked`、recovery `null`。
- response-to-fresh p95/max `1210.886ms`、response-to-visible p95/max `1805.972ms`，继续满足 freshness/visible 门；command p95/max `5443.004ms` 失败。热态 confirm `1273.308–1320.104ms`、withdraw `1089.893–1337.189ms`，仍高于 `1000ms`。
- API telemetry：confirm 固定 17 queries、DB p50 `1089.088ms`；withdraw 固定 14 queries、DB p50 `897.667ms`。一次性 PostgreSQL 同链 SQL trace 复现 confirm 17 queries，并证明 relation repository 先执行 3 条 scope 解析 + 1 次 outbox batch，Turnover UoW 随后又执行第二次 outbox batch。

## repository fan-out 单 owner 本地门

- Turnover 专属 command factory 改为 `PostgresWorkbenchRelationRepository(transaction, enqueue_refreshes=False)`；repository 只保存 canonical relation/history，read-model dirty/outbox 只由 Turnover UoW 输出。关联台和其他页面 repository composition 不变。
- 定向 API/UoW/Workbench command：`254 passed`；disposable PostgreSQL 17 应用 0001–0115 后 `10 passed + 6 subtests`，必需 durable events 完整且临时库自动删除。
- 新 architecture guard 防止 Turnover repository 恢复默认 fan-out。下一门：lint/docs/diff-check、提交/push、部署精确 SHA，并复用三轮生产可逆探针。

## release 188a9fdc3 最终生产门

- 精确代码 SHA `188a9fdc3f91c84f7870bbc167e11bee59db14c4` 已推送 `origin/main` 并部署为 `main-188a9fdc-20260720170432`；`/health/ready` 返回 `ready`、release metadata 一致、PostgreSQL schema `115`、required worker missing/stale/mismatched 均为 `0`、queue backlog 与 stale dirty scope 均为 `0`。
- 发布邻接的第一轮探针记录到一次 confirm command `4542.127ms`，但 response-to-fresh / response-to-visible 仅 `731.948/1120.433ms`，业务断言和最终恢复均通过。API telemetry 显示该次 `4393.272ms` 服务耗时中数据库为 `4343.046ms`、连接获取仅 `30.864ms`；同一窗口 `/health/ready` 与运维 Audit 也出现数据库 I/O 长尾，因此该样本保留为发布邻接数据库竞争风险，不用于 readiness 稳定前宣告通过。
- release readiness、queue 和 worker 稳定后的正式三轮 confirm → fresh → visible → withdraw → fresh → visible 全部通过。六次 command 为 `243.341–604.266ms`，p95/max `604.266ms`；response-to-fresh p95/max `699.225ms`；response-to-visible p95/max `1006.562ms`，均满足 `<=1000ms`、`<=2000ms` 和 hard max `<=3000ms`。最终 fixture 为 `unlinked`，`recovery=null`。
- AppHealth 证明同步 I/O 已收口为 confirm `14` queries、withdraw `11` queries；稳定窗口 API 中位数约 `243/233ms`。Turnover 专属 relation repository 不再输出第二套 dirty/outbox，关联台与其他调用方仍保持原 composition。
- authenticated 40-sample 全部 2xx：页面 shell p95 `98.970ms`；grouped p95 `283.792ms`，40/40 `fresh`；tag selection p95 `160.112ms`；Page Audit p95 `342.569ms`。四组共 160 个正式样本、0 failure、0 refresh enqueue。
- 写操作后的直接 Audit `turnover-ledger` 与交叉 Audit `reconciliation-workbench`、`bank-details`、`cost-statistics`、`oa-pending-payments` 全部 HTTP 200、`integrity=pass`、`freshness=fresh`、`queue=drained`、issues 为空。
- 判定：外部往来款管理在 release 稳定生产窗口达到本阶段性能、正确性、隔离、Audit 和可恢复性门，可停在当前页面的安全暂停点；不自动进入“税金抵扣”。发布邻接数据库竞争长尾继续作为平台容量观测项保留，但不再用页面内 cache、兼容链或跨页面 I/O 掩盖。
