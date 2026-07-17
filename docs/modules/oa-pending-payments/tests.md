# OA 待付款核对测试责任

日期：2026-07-17

## 风险模型

本模块跨 OA integration、PostgreSQL canonical snapshot、durable queue、专属 worker、read model、API、页面条件刷新和 Audit。测试不能只覆盖 fresh happy path，必须证明：

- 旧 rows 绝不会在 dirty/source mismatch 时伪装 fresh。
- 外部 OA 写回成功但 PG snapshot 失败时可安全重试，不形成永久旧页面。
- 旧 event/CAS 失败不能清除新 dirty 或发布 falsely-fresh rows。
- OA 优化不改变 Workbench、银行/发票、input/output invoice read model、共享 Page Audit 和其它页面。
- 旧 filter/live/snapshot/shared-worker 路径不能回流。

## 七类测试

### 1. 业务核心单测：适用

覆盖：

- `paymentStatus` 仅 `paid` / `unpaid`；候选、非 outflow、金额差异不能绕过写回校验。
- completed/in-progress 主行身份、flow id 解析、duplicate/empty/invalid input。
- 双视图 source batch 在通用 status filter 仅含 completed 时仍接纳 in-progress；合法草稿 amount/applicant/reason 未填仍准入且空金额落为 `NULL`；`all` 在校验/附件解析前排除 retention cutoff 以前的历史文档，保留期内 completed 缺既有必填字段仍 fail-closed；in-progress 不调用附件 parser/OCR，completed 保持现有附件处理。
- 精确月份 shard 即使命中跨月 relation，也只聚合该月份 OA 主行；其它月份成员不能污染当前 shard。
- writeback relation、金额、方向、幂等和 already-paid 重试。
- filters、sort、paging、view mode contract。

入口：`tests/test_oa_pending_payment_projection_rows.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_invoice_lifecycle_policy.py`。

### 2. Service-layer：适用

覆盖：

- OA sync 每个启用 form/scope 单次读取，一次 PG 事务提交 completed projection、admission、payment status、watermark、outbox；部分 form 失败必须零提交并记录 failed run。
- 相同 canonical snapshot 第二次提交必须保持 application/status `updated_at`、item/attachment 和 outbox count 不变，且 sync service 不 fan-out 任何页面 refresh；真实变化仍精确覆盖 changed month 与 `all` 聚合 consumers。
- admission/payment-status-only 变化只写 `oa_pending_payment:<month>`；completed canonical 真实新增、修改或删除才由 sync service 触发 shared owner fan-out。snapshot repository 不直接写 `workbench_relation`；queue 失败整体回滚。
- `all` 同步把旧 source watermark scopes 纳入删除比较，最后一条 completed 删除不能漏掉 shared change。
- snapshot replace/delete、空集合、非法 status、queue 失败全回滚。
- 页面 paid writeback 增量更新 PG snapshot/watermark/精确月份 outbox；already-paid 修复；缺初始化 watermark fail fast。
- external MySQL 已成功而 PG 失败时返回可重试错误；重复命令不丢修复机会。
- pending relation create/cancel/promotion 的 version/claim/transaction contract。

入口：`tests/test_oa_projection_sync_service.py`、`tests/test_oa_pending_payment_source_snapshot_repository.py`、`tests/test_oa_pending_payment_relation_repository.py`、`tests/test_oa_pending_payment_command_service.py`。

真实 PostgreSQL：`tests/test_oa_pending_payment_postgres_integration.py` 同时覆盖 canonical commit -> durable worker -> fresh/ETag 与 identical commit 零写/零 outbox。其中 admission-only 隔离用例保留稳定 completed canonical 行后再修改 in-progress admission，锁定 completed `updated_at` 不变、shared change set 为空、增量 outbox 只有 `oa_pending_payment:<month>`，随后 identical commit 再次零写入。

### 3. API contract：适用

覆盖：

- rows `200` shape 包含 rows/pagination/summary/filterConfig/filterOptions/freshness proof。
- ETag、`If-None-Match -> 304`、空 body、`Cache-Control`、`Vary`。
- fresh rows 版本化 cache 命中不得改变公开 response shape；tenant、query 和 version token 必须生成不同 key，`304` 必须在 Redis/payload SQL 前返回。命中路径只执行 statement 级 gate且不进入 read snapshot；miss 必须在 snapshot 内二次 gate，version race 返回 `202`且不得写旧 key。
- rows aggregate/facets 只能扫描 typed columns，page SQL 不读 `raw_payload`，公开 row DTO 不含内部 `searchText` / 逐行 `sourceVersions`。
- dirty/missing/mismatch -> `202`，无旧 rows，精确 `operationBarrierTargets`。
- 权限和 query validation 先于条件响应。
- OA 模块 auth owner：authenticated rows 每个请求只解析一次 identity；全部 read/write endpoint 缺 token 都返回 `401`，无页面权限的 read 返回 `403`，read-only 用户的 write 返回 `403`。global dispatcher 不得恢复第二次等价 session 解析。
- 旧 `/api/oa-pending-payments/filter-options` 不存在。
- write commands 的 200/409/503 shape、scope/barrier 和幂等。

入口：`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_read_model_query.py`。

### 4. Read model / cache / background job：适用

覆盖：

- dynamic expected/actual source vector、dirty/outbox gate、month/all token。
- `all` freshness gate 对跨 scope 重复 `row_id` fail closed；Page Audit 按全局 `row_id` 返回涉及 scopes；rows SQL 不再包含旧 `deduped_oa_pending_payment_rows` / `DISTINCT ON(row_id)` 隐藏去重。
- PG-only projector，按 relation member id 批量读取 canonical facts，纯函数组装，单次 values 批量写入，空 scope清理，原子 publish。
- projector/freshness SQL 不包含 `WorkbenchRelationReadFacade`、`workbench_relation_read_model_not_fresh`、`workbench_relation_source_versions` 或 `read_model.workbench_relation_scopes`。
- stale event在读取源前 skip，CAS lost不清新 dirty，all仅低优先级 fan-out；all 的 shard inventory 按 event tenant 读取 source watermarks，覆盖合法 empty month，禁止回退为 completed/admission 非空月份枚举。
- `oa-pending-payment` worker claim隔离；shared `invoice-usage-collection` 不含 OA handler。
- source snapshot/migration/permission/schema contract。
- OA 私有 rows cache 每次命中前仍执行 PostgreSQL freshness/version gate；同版本同 tenant/query 的重复 fresh `200` 跳过 payload SQL和 read transaction，版本、tenant 或 query 变化必须 cache miss。miss/Redis 故障路径在 repeatable-read snapshot 内重跑 gate，只有 version token 不变才读取/回填 payload；读中 version/status 变化必须 `202` fail-closed。key 已绑定 version token，因此不增加 writer invalidation/fan-out。

入口：`tests/test_oa_pending_payment_api.py`、`tests/test_read_model_query_gateway.py`、`tests/test_oa_pending_payment_read_model_refresh.py`、`tests/test_oa_pending_payment_read_model_query.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_postgres_migrations.py`。

### 5. Frontend component / interaction：适用

覆盖：

- initial loading、fresh/empty/error/refreshing、`202`立即隐藏旧 rows。
- 可见 tab 500ms 条件 GET、hidden暂停、恢复可见立即检查、最多一个 in-flight、unmount/query change cancel、晚响应隔离。
- `304` 保留 fresh rows；新 `200` 更新 ETag/payload；barrier后完整重读。
- mutation成功后隐藏旧 rows并等待 barrier；失败保留明确反馈。
- 搜索、筛选、排序、分页、view toggle、drawer、权限控制。
- OA 专属 Audit 五种中文文案和 issue samples；共享组件默认行为回归。

入口：`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/OaPendingPaymentAuditIcon.test.tsx`、`web/src/test/App.test.tsx`。

### 6. 端到端业务流：适用

本地 deterministic Browser 覆盖：

- fresh rows 首屏、筛选/排序、detail。
- `202 -> hide rows -> barrier -> fresh`。
- writeback-paid / link-bank -> barrier -> 新 rows。
- 旧 filter endpoint请求次数为 0。

入口：`web/e2e/oa-pending-payments-flow.spec.ts`、`oa-pending-payments-nonfresh-flow.spec.ts`、`oa-pending-payments-confirm-paid-flow.spec.ts`、`oa-pending-payments-bank-link-flow.spec.ts`。

真实 `T0 PostgreSQL commit -> OA worker -> browser T1` 需要统一部署后在真实 PostgreSQL/RabbitMQ/systemd/browser 环境执行，当前不得用 mock E2E 宣称 1 秒 SLO 已通过。

### 7. Existing feature regression：适用

覆盖影响面：

- input/output invoice worker和 read models不再被 OA event claim，原 API/rows仍正常。
- Workbench relation、pending relation promotion、bank claim、bank/invoice detail不回归。
- admission-only 同步前后 Workbench、成本统计及其它 shared dirty/outbox/source versions 不变；completed shared fact 变化仍保留合法 fan-out。
- 共享 `PageAuditIcon`、其它页面文案和权限不改变。
- server/runtime边界无 live fallback/private adapter/state-store snapshot。
- 旧 API response shape中仍受支持的 rows/detail/write contracts不丢字段。

入口：`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_workbench_*` 相关回归、`web/src/test/App.test.tsx`。

## 性能验收

### 本地门槛

- 证明 `304` path 不执行 rows/facet aggregation。
- 证明 sync source 每个启用 form/scope 只读取一次，in-progress 跳过附件/OCR 热路径。
- 证明 rows query 是一个有界 set-based data statement，同时返回 summary/facets 与 bounded page；不存在第二次 page roundtrip，也不存在 `all_rows()` 每 200 行循环。
- 关键 SQL 在生产等量级副本保存 `EXPLAIN (ANALYZE, BUFFERS)`；没有数据证据不新增索引。

### 2026-07-16 本地真实 PostgreSQL 证据

- 环境：`/tmp`隔离loopback PostgreSQL，全部107个migration；单月500行、pool max 12、合成8并发。500行是2026-06-17历史实施记录中生产总量210行的2.381倍，但当前生产峰值和当前数据分布未知，不能标记为当前生产等量副本。
- fresh `200`：顺序1000次，`p50 8.710ms / p95 9.938ms / p99 11.300ms / max 109.441ms`；8并发1000次，`p50 22.484ms / p95 33.243ms / p99 45.531ms / max 53.749ms`；错误率均为0。
- ETag `304`：1000次，`p50 0.361ms / p95 0.520ms / p99 0.629ms / max 1.038ms`，错误率0。statement recorder证明只有repeatable-read setup和1个freshness gate query，没有aggregate、facet或page query。
- 200次canonical mutation：commit返回到fresh API为`p50 403.675ms / p95 544.178ms / p99 593.683ms / max 650.951ms`，错误率0；200/200次在worker收敛前返回202且rows为空。分段为queue claim `p95 1.567ms`、projector build+CAS publish `p95 435.400ms`、queue complete `p95 1.534ms`、最终fresh API `p95 131.274ms`。canonical commit本身另计`p95 292.530ms`；冷启动commit返回到fresh为`282.284ms`。
- SQL `EXPLAIN (ANALYZE, BUFFERS)`：freshness gate execution `0.090ms`/10 shared hit blocks；aggregate+facets逻辑段 `5.755ms`/128 hits；bounded page 20行逻辑段 `0.306ms`/128 hits；三者physical read和temp read/write均为0。2026-07-17 根据生产 profile 把后两段合并为同一个有界 data statement，fresh路径现在是1个gate加1个data statement；无新增索引证据。
- 结论：本地服务端分段性能门通过。该harness没有真实浏览器500ms条件检测、React render、真实网络、真实worker进程调度、当前生产峰值或其它页面延迟对照，因此不能用`544.178ms`宣称生产commit-to-visible已通过；这些仍属于统一部署后硬门。
- 可重复集成保护：`tests/test_oa_pending_payment_postgres_integration.py`在配置`FIN_OPS_TEST_DATABASE_URL`时验证 canonical snapshot/date、Workbench 写事务直接产生 OA target、OA worker无需先完成 relation read model即可投影、202、CAS、queue complete、source vector、fresh 200 和 304 完整链路。
- 生产 latest-dirty 长尾保护：migration contract 锁定 OA-only partial index 的 predicate 与 `(tenant_id, scope_type, scope_key, source_version DESC, updated_at DESC, id DESC)` 顺序；query contract 锁定 freshness gate 使用同一 latest-version order，避免索引与业务语义漂移。

### 本地验证结果

- 2026-07-17 dual-view/fan-out 隔离变更：全量 backend `4130 passed / 6 conditional skipped`；真实 PostgreSQL 0001–0110 `4 passed`；全量前端 `72 files / 857 tests`、production build、Playwright `179/179`、lint/docs/diff-check 全部通过。6 项 backend skip 仅为当前机器未提供的外部依赖条件；真实 PostgreSQL 链未跳过。
- OA后端目标矩阵：266 tests passed；真实PG集成：1 passed。
- OA前端组件：40 tests passed；OA Playwright：8 tests passed。
- 全量前端：72 files / 849 tests passed，production build passed；构建仅保留既有CSS minify/chunk size warning。
- `verify.sh lint`、`verify.sh docs`、`git diff --check`通过；107 migrations隔离PG上的`verify.sh runtime-check`返回ready。
- 全量backend discovery：4273 tests，125 failures、55 errors、34 skipped。失败集中在并行Workbench改造下旧characterization fixture没有配置SQL initial-page repository、expected read-model version合同，以及Cost Statistics共享guard allowlist漂移；OA目标矩阵、OA manifest和OA边界guard单独通过。本模块不通过改OA断言或改其它thread文件掩盖这些失败。

### 统一部署后的硬门槛

- fresh rows API：至少 1000 次，报告 p50/p95/p99/error rate；`p95 <= 250ms`、`p99 <= 500ms`。
- 条件 `304`：至少 1000 次；`p95 <= 30ms`。
- 普通 canonical mutation：至少 200 次完整 `T0 -> T1`，包含失败/202样本；`p95 <= 1s`。
- `500ms` 是挑战目标，只有真实样本通过后才能提升为承诺。
- 同时记录 queue pickup、build、CAS publish、API、browser render、DB连接和其它页面 latency，证明隔离性。
- 三页 simultaneous gate 使用每页一个并发请求、至少 50 轮；每页仍按各自页面门槛判断，不能用总吞吐或 isolated 结果替代。更高并发压力结果作为容量证据单独报告，不通过扩大共享连接池修复 OA 私有瓶颈。

### 2026-07-17 生产结果

- isolated 浏览器等价持久连接：500 次全部 `200/fresh`，`p50=127.936ms / p95=217.272ms / p99=262.054ms / max=393.551ms`；服务端 512-window 为 `p95=207.831ms / p99=272.479ms`。
- 三页 simultaneous 50 轮：150/150 `200/fresh`；OA 公网 client `p95=357.947ms`，同窗服务端 `p95=207.831ms`，DB `p95=85.465ms`、connection acquire `p95=0.183ms`、query count 固定 7。服务端门槛与模块/数据库隔离通过；公网客户端差值按 WAN/同探针大 payload 竞争单列，不把它伪装成 OA SQL SLO，也不改共享资源修复。
- 部署后基线与正式 confirm -> withdraw 恢复后两轮 Page Audit 均为 `pass/fresh/drained`、`issues=0`、`database_snapshot=true`。
- 公网条件请求仍为完整 `200`、`99,958` bytes、约 `136ms`；live Nginx `/fin-ops-api/` 未同步仓库模板的显式 `If-None-Match` 转发。应用端 weak ETag contract 已通过测试且 full-response SLO 已通过，但 `304 p95<=30ms` 必须在 root owner 修正并 reload Nginx 后复测，当前不得标记该子门完成。

## 本地验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest -q \
  tests.test_oa_pending_payment_projection_rows \
  tests.test_oa_pending_payment_command_service \
  tests.test_oa_pending_payment_api \
  tests.test_oa_pending_payment_postgres_integration \
  tests.test_oa_pending_payment_read_model_query \
  tests.test_oa_pending_payment_read_model_refresh \
  tests.test_oa_pending_payment_source_snapshot_repository \
  tests.test_oa_pending_payment_relation_repository \
  tests.test_oa_projection_sync_service \
  tests.test_runtime_worker_registry \
  tests.test_postgres_migrations

PYTHONPATH=backend/src python3 -m unittest -q \
  tests.test_platform_runtime_boundary_guards \
  tests.test_read_model_architecture_guards \
  tests.test_invoice_usage_collection_sql_runtime

bash scripts/verify.sh lint

cd web && npm test -- --run \
  src/test/OaPendingPaymentsPage.test.tsx \
  src/test/OaPendingPaymentAuditIcon.test.tsx \
  src/test/App.test.tsx

cd web && npm run build

cd web && npx playwright test \
  e2e/oa-pending-payments-flow.spec.ts \
  e2e/oa-pending-payments-nonfresh-flow.spec.ts \
  e2e/oa-pending-payments-confirm-paid-flow.spec.ts \
  e2e/oa-pending-payments-bank-link-flow.spec.ts
```

## 当前剩余风险

- 未部署，因此尚未执行 migration/backfill、真实专属 worker drain、生产 Audit和性能样本。
- 已在500行合成本地PG运行 `EXPLAIN (ANALYZE, BUFFERS)`、1000次fresh/304和200次mutation；但当前生产数据量、峰值并发、网络、浏览器render和其它页面延迟未测，仍不能宣称生产p95/p99已达标。
- MySQL与PostgreSQL不存在分布式事务；已通过幂等命令重试和下一次 OA sync恢复，但仍需生产故障注入/运维演练验证告警与恢复时间。
- 若全仓测试出现其它进行中 task 的 Workbench/cost-statistics失败，必须单独记录，不能放宽 OA 断言或修改无关模块掩盖。
