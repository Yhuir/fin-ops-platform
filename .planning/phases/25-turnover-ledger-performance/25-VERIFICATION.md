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
