---
phase: 05-cost-statistics-improvements
plan: 06
status: completed
completed_at: 2026-07-16
result: PASS
next_state: IMPLEMENTING
deployment: hold
---

# 05-06 Summary：View-specific cursor explorer

## 结果

成本统计页面已在原 `/api/cost-statistics/explorer` 路径完成无双读切换：请求必须携带 `scope + view`，响应只包含完整 summary、当前 view 的小型 facets、当前层级 bounded rows、row count 与 version-bound cursor。旧 full explorer HTTP shape 不再作为页面 fallback。

本轮没有新增 `/v2`、read model、表、worker、year scope、消息通道、共享 cache/pool 变更或第三方依赖；其他页面和其他页面 read model 未被修改。保持 `DEPLOYMENT_HOLD`。

## 已落地合同

- PostgreSQL durable freshness gate 位于 ETag、Redis 与 page SQL 之前；non-fresh 返回空 rows/facets 的 `202`，不能读取旧 cache/rows。
- fresh cache miss 通过 cost-owned repository port 执行一个 set-based SQL，返回 summary、available years、facets、row count 与 `page_size+1` rows；默认 50、最大 100。
- month 使用 month gate；`year:YYYY` / `all` 使用 parent gate，不新增 year projection。
- cursor 绑定 schema、scope/view/filters/page size、稳定排序键与 `published_source_version`；版本或 query 变化后明确拒绝，禁止跨版本追加。
- ETag/cache key 绑定 query、published version 与 tag-selection token；匹配 `If-None-Match` 时跳过 page SQL。
- available years 独立于当前 month/year filter，避免时间控件锁死在当前范围。
- 页面切换 scope/view/filter 时 abort 旧请求、清除旧可操作数据并只接受最后一代响应；“加载更多”只追加同 identity cursor。
- 项目/费用类型导出选项只在用户动作后并行读取两个 bounded all-scope facet 请求；time/bank-tag 不承担该 I/O。

## 旧链路删除与保留边界

已删除页面热链路中的：

- `fetchCostStatisticsExplorer` full DTO client/mapper/types；
- `timeRows` / `bankFlowTimeRows` 全量页面 state；
- 浏览器端 scope filter、project/bank/expense/tag group-by、summary/percentage 重算；
- full `active:all` 导出参考 payload；
- detail 接口失败后从列表行拼装本地详情的 fallback。

current production code scan 对上述符号与旧 response 字段为零。endpoint 缺少 `view` 会返回 `400`，不回退旧 shape。

`get_cost_statistics_view()` 暂未删除：CodeGraph/whole-repo impact 证明它仍由内部 month/summary/export 与 projection unchanged-check 路径动态调用。它不再服务页面 explorer；后续必须先迁移这些已登记调用方，再删除 port/repository/full payload helpers，禁止误删造成导出或 worker 回归。

## 测试覆盖（七类）

1. Business core：scope/view/filter、金额/方向 facets、cursor binding/version/boundary、empty 与分页。
2. Service-layer：gate-before-cache/SQL、single statement repository、tag selection、ETag 304、cursor invalidation。
3. API contract：唯一 page shape、200/202/304/400、headers、非法参数与 project scope。
4. Read model/cache/job：versioned cost-local cache 与 PostgreSQL gate；worker 本轮未改，由既有 source-version CAS 回归保护。
5. Frontend interaction：五视图、range、层级请求、loading/empty/error/non-fresh、lazy export facets、分页和详情失败。
6. E2E：Chromium 五视图、详情/导出、non-fresh 防伪成功、390px 120+ 行 cursor 追加。
7. Regression：旧 month/summary/export/manifest、cost route/runtime boundary 与 relation fan-out 责任。

## 验证结果

- `bash scripts/verify.sh lint`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_sql_runtime tests.test_read_model_manifest`：91 tests 通过。
- 成本统计专属 platform boundary guards：3 tests 通过。
- `cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx --reporter=verbose`：33 tests 通过。
- `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`：10 tests 通过。
- `cd web && npm run build`：通过；仅保留既有第三方 CSS minify/chunk warning。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- `FIN_OPS_TEST_DATABASE_URL`：未配置，因此未运行 disposable PostgreSQL integration/EXPLAIN；不得伪造该证据。

共享工作树中的全量 `tests.test_platform_runtime_boundary_guards` 有 14 个失败，全部指向另一 thread 正在修改的 Workbench route/row-detail freshness guard；成本统计专属 3 个 guard 均通过，本轮未覆盖或修改对方代码。`cost-statistics-relation-fanout` Browser 回归也因同一共享 Workbench“确认关联”按钮被禁用而超时，发生在成本页面 fan-out 之前；本轮 cost flow 自身 10/10 通过。统一收口其他 thread 后必须重跑这两项。

## 未完成门禁

- 未部署、未运行生产 migration/rebuild、未访问生产。
- 未做生产 `EXPLAIN (ANALYZE, BUFFERS)`、真实 browser/API SLO 或索引决策。
- Impeccable 轻量锁定遮罩、Audit 拆分/修复、请求期 expected-source provider 删除、streaming export、剩余内部 full loader/warmup/summary route 清理仍未完成。
- 整体 `/goal` 继续 active，不能标记 complete；本轮按约定不预生成 05-07。
