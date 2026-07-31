# OA待付款核对 实施记录

## 2026-07-31 - 关联支出流水抽屉迁移到共享壳

- 只把 `OaBankLinkDrawer` 的自定义 backdrop/aside/header/close 展示壳替换为共享 `AppDrawer`，保留 560px、搜索、筛选、分页、选择、提交、AbortController、权限、loading/error 和写入时机。
- 删除 `if (!open) return null` 和旧 shell CSS，让 HeroUI right drawer 完成 240ms 进入与 180ms 退出；busy 期间共享关闭语义 fail closed。
- OA、流水、发票事实来源、API 请求/响应、模块 I/O 和 boundary 均未变化，因此不修改 `boundary-io.md`；没有新增动画依赖或兼容 fallback。
- 回归由 `OaPendingPaymentsPage.test.tsx` 的业务行为/源码负向门禁和 `drawer-motion.spec.ts` 的共享浏览器 motion 合同承担。

## 2026-07-27 - 页面 PostgreSQL canonical facts 直读迁移

- 页面 rows/details 从 `OaPendingPaymentReadModelService` 切换到页面专属 `OaPendingPaymentQueryService` + `PostgresOaPendingPaymentQueryRepository`。同一 rows 响应在一个显式 `REPEATABLE READ READ ONLY` snapshot 内读取 canonical OA/admission/payment status、active pending/formal relations、银行和进项发票事实；SQL 完成过滤、排序、服务端分页、summary、statistics 和 facets，当前页再固定次数批量 hydrate。
- 正式关系只读 `app.workbench_pair_relations.status='active'`，不读取 Workbench page payload 或 `workbench_relation` projection。页面请求热路径不访问 OA Mongo/MySQL、Redis、queue、worker 或对象存储。
- 删除页面 `read_model_status`、source versions、refresh enqueue、Redis versioned payload、ETag、202/304、条件 polling、visibility retry 和 Audit barrier wait。保留 loading/empty/error、手工刷新、晚响应隔离和写后 normal GET。
- 写命令继续保留权限、tenant、claim/promotion、审计、幂等、CAS/冲突和外部适配器；响应删除 `readModelRefresh`，外部写回后仍幂等收敛 PostgreSQL payment-status snapshot。
- `bank-transaction-candidates` 从 command service 的 `_import_service` 全量 Python 过滤/分页迁到 page query repository；单条 SQL 读取 canonical outflow bank facts 和 active formal/pending relations，并保留四个 relation status、全部月份、keyword、repeated `oa_row_ids` 回显和服务端分页合同。
- 共享 OA read model/projector/worker/registry 本分支不删除：`invoice_lifecycle` 仍有依赖，且全局 registry/deploy cleanup 由主控统一完成。

## 2026-07-26 - active relation membership freshness 证明

- 根因补强：仅记录 relation `updated_at` 上界无法识别“撤回较旧 relation、较新的 active relation 仍保持同一最大时间”这一集合成员变化，旧 OA summaries 因而可能继续被判 fresh。
- 最小修复：复用 OA source-snapshot owner 和 structured PostgreSQL relation repository。source vector 在一次 set-based SQL 中登记 active eligible relation 的数量、最大更新时间和确定性 membership digest；digest 绑定 case、typed members、mode、version 与 projector 实际消费 payload。projector 删除本地 `_active_relations` 状态推断，直接调用 active-only loader，并继续排除 Turnover 专属 closure mode。
- 边界不变：不新增 migration、依赖、worker、队列、read-model 串行依赖或写后 fan-out；Cost runtime 与 API response shape 不变。
- 本地验证：source snapshot、projector refresh 和 PostgreSQL integration 合同共 32 项测试通过，其中 6 项真实 PostgreSQL 用例因本机未配置测试数据库按既有条件跳过。新增真实数据库闭环会在可用环境中验证 active relation 投影后，仅修改 structured status 为 withdrawn（raw payload 仍残留 active）会触发 access-time mismatch/enqueue，并在重建后把银行/发票 `relationCount` 清零。生产部署与样本验证留给后续发布任务。

## 2026-07-25 - 删除 fresh/visibility 常驻轮询旧链

- 全量页面触发扫描发现 OA 页面在任意 fresh `200 + ETag` 后仍每 500ms 条件请求，并在 hidden→visible 时立即请求；这会让已打开页面在其它事实变化后自动更新，违反 Phase 27 的访问触发与隐藏页零业务 I/O 合同。
- 最小闭环是保留现有 rows endpoint、ETag/304、fresh gate 和 `202 -> current rows GET -> fresh`，删除 fresh 后的常驻检查与 visible 恢复入口。只有本次访问/查询/明确重试/本页写后 GET 返回 non-fresh 才按 500ms、单 in-flight、最多 60 次重试；fresh、页面隐藏、卸载、查询变化或 30 秒上限即停止。
- 不新增 coordinator、hook、endpoint、worker、queue、缓存或 fallback。组件回归锁定 fresh 后零请求、hidden→visible 零请求、202 有界收敛、单 in-flight 和旧 operation-barrier 为零。

## 2026-07-24 - 普通页面 202 收敛删除旧 operation-barrier I/O

- 生产证据：Phase 27 统一生产路由 smoke 在无用户点击时观察到 `POST /api/operation-barrier/status`。全量 caller 核对确认 `OaPendingPaymentsPage` 的普通 rows `202` 分支仍等待 barrier；覆盖矩阵却把该 caller 误记成显式 Audit/reconcile，属于旧链遗漏。
- 当日最小修复：删除普通页面对 `waitForOperationFreshness` 的依赖；`202` 立即隐藏旧 rows 后复用当前页 rows GET。其当时保留的 fresh 常驻轮询与 hidden→visible 自动检查已由 2026-07-25 合同删除。后端 `202` 精确 target DTO、显式 OA Audit 和银行规则显式 reapply 合同不变。
- 边界与测试：不新增 coordinator、hook、endpoint、worker、queue 或缓存。组件回归证明 `202 -> current rows GET -> fresh` 且 barrier 为 0；定向 Browser 与生产 17-route smoke 负责证明普通页面访问不再产生 barrier POST。

## 2026-07-23 - Workbench 撤回后的访问时 freshness 漏洞

- 生产证据：test-owned Workbench relation 通过正式 API 撤回后，`oa_pending_payment` queue 已 drained、scope 被标记 fresh，但 Page Audit 仍发现同一 case 的 OA、银行流水和进项发票 3 条 `consumer_edge_not_shared`；旧 OA rows 仍保存已撤回 relation summaries。
- 根因：OA projector 直接读取 `app.workbench_pair_relations`，但 expected/actual source vector 只包含 OA integration snapshot、pending relation 和 event version，没有登记 completed Workbench canonical relation 这个真实输入。Phase 27 又正确删除了普通写后 OA fan-out，因此访问 gate 没有任何依据识别撤回。
- 最小修复：复用 OA PostgreSQL source-snapshot owner，一次 set-based 查询计算各月份 completed OA 涉及的 canonical relation `updated_at` 上界；projector 发布与 query gate 写入/比较同一个 key。普通 confirm/withdraw 继续零 OA dirty/outbox，页面只在访问时 enqueue mismatch 的精确月份；不新增表、migration、worker、cache、read-model 依赖或 fallback。
- 测试：新增 canonical relation version 的月份去重/set-based SQL合同，以及“published OA vector=old、canonical relation=new 时 scope 必须 refreshing”的回归；保留 projector 不读取/等待 `workbench_relation` read model 的架构 guard。
- 生产关闭门：部署精确 SHA 后访问 `oa_pending_payment:2026-06`，要求一次精确 refresh 后 3 条 stale edge 消失；同时访问 `cost_statistics active:2026-06` 收敛其真实 upstream mismatch，再重跑 strict confirm→withdraw、零 fan-out、最终 System Audit 和 3 秒 access-to-fresh。

## 2026-07-22 - 标题统计覆盖月份闭环

- 目标：让 `oa_pending_payment:all` 统计覆盖只有银行流水或进项发票、尚无 OA integration watermark 的月份，避免标题全期间库存漏月。
- 边界：worker inventory 一次 SQL union OA source watermark、未删除银行月份和未删除进项发票月份；coverage-only 月份只在 read-model metadata 写确定性 empty source vector，不写 `app.oa_sync_watermarks`。真实 OA source 后到会使该 vector stale；prune 只作用于 read-model shard。
- 测试：`tests/test_oa_pending_payment_read_model_refresh.py` 覆盖 inventory union 与不写 source watermark；`tests/test_oa_pending_payment_read_model_query.py` 覆盖 coverage-only fresh 和真实 OA source supersede。
- 验证：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_read_model_refresh tests.test_oa_pending_payment_read_model_query -v`。

## 2026-07-17 - Workbench 关联后 OA 可见性热路径去串行依赖

- 生产基线：正式关联操作后，OA 页面新数据约 `18.7s` 才可见；证据分解为 OA 事件首次 defer `1.510s`、等待约 `17.182s`、OA handler `12.180s`，另有约 `5s` queue 尾部。撤回同 scope 约 `2.106s`、handler `0.888s`，说明慢点不是页面查询，而是 OA projector串行等待 `workbench_relation` read model后又用 live query service做全量组装。
- 根因修复：Workbench UoW继续在 canonical relation 同一业务事务内投递受影响 `oa_pending_payment:<month>`；OA 专属 worker直接从 `app.workbench_pair_relations` 读取 active canonical relation，并按 relation member id批量读取银行/发票事实，不再读取或等待 `read_model.workbench_relation_*`。in-progress 仍只读 OA 私有 pending relation，附件/OCR保持不解析。
- 模块边界：新增 `oa_pending_payment_projection_rows.py` 作为无 I/O 的纯行组装边界；projector只负责 PostgreSQL repository I/O和编排；query/freshness gate只依赖 OA scope、source snapshot、pending relation和 event version。没有新增队列、缓存、worker、fallback或跨页面 invalidation。
- 旧链删除：删除 1,340 行 `oa_pending_payment_service.py` 及其 live-query测试，移除 server bootstrap/private accessor、invoice-lifecycle live fallback、projector `WorkbenchRelationReadFacade`、freshness SQL 的 `workbench_relation_scopes` join和 `workbench_relation_source_versions`。边界 guard禁止这些符号回流。
- 发布性能：月份 rows 由逐条 `executemany` 收敛为单次 values batch；projector输出 `load_ms/assemble_ms/publish_ms/total_ms`，便于统一部署后按 commit-to-fresh p95硬门验证。当前只完成本地实现和验证，未部署；生产 `<=1s` 只能在统一发布后用真实 confirm/withdraw样本确认。
- 回滚：代码回滚整个 release并重新 enqueue `oa_pending_payment:all`；不恢复已删除的 live fallback，也不让页面把旧 rows冒充 fresh。

## 2026-07-17 - OA 模块重复鉴权 I/O 收敛

- 生产证据：release `main-3f7acf70f-oa-cache-hit-gate-20260717` 已把 cache hit 的 read snapshot 删除；50 次公网 fresh `200` 仍为 `p50=178.343ms / p95=266.338ms / p99=273.771ms`。进程 rolling 样本显示 server `p95=177.431ms`、database `p95=65.394ms`，cache hit 固定 5 次数据库操作，严格 `p95<=250ms` 尚未闭合。
- 根因：`Application._enforce_route_access(...)` 先调用一次共享 `resolve_oa_request_session(...)`，`OaPendingPaymentApiRoutes` 随后又通过 read-session/write-auth port 执行同一鉴权。`AccessControlService.evaluate(...)` 每次都读取动态 readonly/admin policy，因此 fresh cache hit 的 5 次数据库操作由两轮权限 I/O 加一条 OA 私有 freshness gate 构成；这不是 rows cache、projection 或另两个页面的负载。
- 最小修复：仅把 `/api/oa-pending-payments` 精确路径树登记为 module-owned access control。全局 dispatcher 不再对该树执行重复 guard；模块现有每个 read endpoint 仍先执行 read-session，每个 write endpoint 仍执行 write-auth，identity service、access policy、错误码、tenant 和业务权限不变。
- 隔离与旧链删除：不缓存 session、不绕过权限、不改共享 auth 算法，也不改变其它 route；删除的只有 OA 路径上的第二份等价前置鉴权 I/O。回归测试锁定一次 authenticated rows request 只解析 identity 一次、全部 8 个模块 endpoint 缺 token 均 `401`、无页面权限 read 均 `403`、read-only write 均 `403`。
- 关闭门：相关/真实 PostgreSQL/全量 CI、精确 SHA 部署、rolling query count、1000 次公网 fresh `200`、三页面 mixed load 与负载后 Audit；只有权限门、p95/p99 和 Audit 同时通过才可完成。

## 2026-07-17 - 生产 cache-hit 门禁去事务化

- 生产证据：release `main-4a6c20a9b-oa-rows-cache-20260717` 部署后，三页面 Audit 均为 `pass/fresh/drained/0 issues`；OA “进行中”公网 fresh `200` 采样 1000/1000 成功，`p50=174.569ms`、`p95=281.536ms`、`p99=424.983ms`。p99 通过但 p95 仍高于 `250ms`，不能声明性能闭环。
- 真正热路径：versioned Redis 已把 payload SQL 从重复请求移除，但生产 rolling 512 样本仍显示 OA rows 的数据库 query count 固定为 6、DB `p95=81.148ms`。原因是 cache hit 仍进入 OA `repeatable read read only` snapshot，承担事务进入、`SET TRANSACTION`、freshness statement 和事务退出；cache 没有缩短 gate 外围的事务 I/O。
- 最小修复：每次请求继续执行同一 OA 私有 PostgreSQL freshness/version statement；`202` 和 `304` 仍在 Redis/payload I/O 前返回。只有 cache miss/Redis fallback 才进入 repeatable-read snapshot，并在读取 rows 前重新执行 gate，要求 snapshot 内 `status=fresh` 且 `version_token` 与外层 gate 完全相同；竞态变化返回 `202`，不得把 payload 写入旧 version key。cache hit 因此只有一次 statement 级 PostgreSQL gate，不启动 snapshot transaction。
- 隔离边界：不改 canonical、projection、repository SQL、schema/migration、queue/worker、API DTO、共享 `ReadModelQueryGateway` 或其它页面 read model。新增测试锁定 cache hit 不进入 snapshot、miss 二次 gate、version race fail-closed、Redis 故障回退和原有 tenant/query/version 隔离。
- 待关闭门：相关/真实 PostgreSQL/全量测试、精确 SHA CI、部署后 rolling query count、1000 次公网 fresh `200`、三页面 mixed load 与负载后 Audit；只有 p95/p99 与 Audit 同时通过才可完成。

## 2026-07-17 - 生产 1000 样本后的 OA 私有 rows cache 收敛

- 部署基线：release `main-1ce3bc8bf-oa-admission-cutoff-20260717` 完成 `oa.sync:all` 后，页面显示 `in_progress=88`；同步扫描 retained completed `244`、in-progress `151`，首次 OA 私有 affected scopes 为 6 个月，completed shared change 为空。第二次相同同步两个 change scope 集合均为空，三页面 Audit 均为 `pass/fresh/drained`。
- 性能事实：公网认证 in-progress fresh `200` 正式 1000 次为 `1000/1000` 成功且全部 fresh，`p50=183.030ms / p95=292.945ms / p99=424.546ms`；严格 `p95<=250ms` 未通过。相同进程 512 滚动样本为 server `p95=188.503ms`、database `p95=87.450ms`、固定 7 queries；重复 payload 聚合是当前可消除的 OA 私有 I/O，不能再用此前 500 次 isolated 成绩声明生产闭环。
- 最小设计：不改 canonical、projection、queue、worker、schema、API 或其它页面。每次 rows 请求仍先执行 OA 私有 PostgreSQL freshness/version gate；`202` 和 `304` 均在 cache/payload SQL 前返回。只有非条件 fresh `200` 使用现有 `ReadModelQueryGateway`，以现有 ETag（tenant + normalized query + contract revision + version token）构成 OA 私有 Redis key；miss 执行现有单条聚合 SQL并缓存 300 秒，版本变化自动换 key，Redis 故障 fail-open 到 PostgreSQL但不绕 freshness gate。
- 测试责任：新增同版本重复读取只执行一次 payload SQL、每次仍执行 fresh gate、`304` 不读 cache、tenant/query/version key 隔离、Redis 读写故障回退、生产 runtime Redis 装配和公开 response 不泄露 cache metadata；沿用 dirty/source mismatch `202`、ETag、真实 PostgreSQL与三页面回归门。
- 待关闭门：本地/CI/真实 PostgreSQL全量验证、精确 SHA 再部署、cache hit 1000 次公网 fresh `200`、条件 `304`、三页面 simultaneous mixed load、同步/安全写操作后 Audit。live Nginx 未转发 `If-None-Match` 的既有 root-owner 门保持独立，禁止用应用 query fallback规避。

## 2026-07-17 - 进行中 OA 准入源与跨页面 fan-out 隔离

- 真实根因：通用 OA 导入 `statuses` 同时控制 shared projection 与 OA 待付款 admission，生产配置只接纳 completed 时，in-progress 在进入 PostgreSQL 前已被过滤，页面因此稳定显示 0。旧 snapshot result 又把 completed/admission/payment-status 变化混成一个 scope 集合，repository 对任一变化都隐式 enqueue Workbench relation，无法证明 admission-only 不影响其它页面。
- 设计：Mongo adapter 每个启用 form/scope 只读一次，输出 `projection_records` 与 `admission_records` 双视图；前者遵守通用配置，后者固定接纳 completed + in-progress。任一 form 失败或目标文档无法投影时整轮 fail-closed，sync service 记录 failed run且不提交部分集合。
- 性能：in-progress 只保留原始/上下文化附件文件元数据，完全绕过附件证据解析、发票识别和 OCR；completed 保持现有附件处理。没有新增表、索引、cache、worker、endpoint 或第二套同步链。
- 隔离：snapshot repository 分别返回 `oa_pending_payment_changed_scopes` 与 `completed_projection_changed_scopes`，自身只 enqueue OA 私有 refresh。admission/payment-status-only 不再触发 Workbench/shared consumers；completed canonical 真实新增、修改或删除仍由 sync service 交给既有 shared owner fan-out。
- 删除闭环：移除 sync service 的 months/list/all-list 旧编排和 adapter 无生产调用方的 fingerprint polling/helper/test；架构 guard 禁止这些旧链、混合 change set 与 repository Workbench fan-out 回流。
- 边界补漏：`all` 同步把旧 source watermark scopes 纳入 completed 删除比较，覆盖“最后一条 completed 被删除”；相同 snapshot 继续零时间戳漂移、零 admission replace、零 downstream fan-out。
- 本地验证：cutoff 顺序修复后，真实 PostgreSQL 0001–0110 环境中后端全量 `4133 passed / 6 conditional skipped`；空 amount/applicant/reason 的 in-progress 草稿以稳定 identity 准入、金额落为 `NULL`，completed `updated_at` 不变、shared change set 为空、增量 outbox 只有 OA 私有精确月份；新增测试锁定保留期外历史脏文档在校验前被排除、保留期内 completed 缺必填字段仍整轮失败。前端 `72 files / 857 tests`、production build、Playwright `179/179`、lint、docs 与 diff-check 全部通过。
- 两次生产激活均对同一 Mongo 文档 fail-closed 并立即回滚到 `main-d3fc16026-oa-outbox-index-20260717`，未产生部分 PostgreSQL 写入。脱敏源检查最终确认该文档不是 in-progress，而是 retention cutoff 以前的 2023 completed payment：amount/reason 存在但 applicant 缺失。旧 service 先按保留月份选 scope；新 dual-view service 却在 adapter 完成全历史字段校验后才过滤 cutoff，顺序错误使本不应进入本轮 snapshot 的历史文档阻断同步。最终修复把 `retention_cutoff_month` 作为 source batch 显式输入，在任何字段校验/附件解析前排除保留期外文档；不恢复旧月份循环，不把 `repairer` 猜成申请人，也不放宽保留期内 completed 的严格合同。合法 in-progress 空字段准入修正继续保留。
- 生产门：精确 SHA 部署后执行 `oa.sync:all`，核对 completed/in-progress 扫描计数、admission/status、水位和 queue drain；验证 OA 进行中数据、三页面 Audit、操作后 Audit、页面性能及 admission-only shared outbox/version 不变。结果未采集前不把本次修复标记为生产闭环。

## 2026-07-17 - 周期同步刷新风暴与 rows 热路径收敛

- 生产证据：fresh 首屏 `page_size=20` 的 12 次浏览器等价 gzip 请求 `p95=859.634ms`，且周期性 `oa.sync` 期间反复返回 `202/refreshing`；相同 ETag 的公网条件请求仍返回完整 `200`。同期混合负载使 OA、Workbench、成本统计同时进入 refreshing，证明瓶颈不只是页面渲染。
- 根因：OA projection 对相同 completed records 仍无条件更新 `synced_at/updated_at`、删除重插 item/attachment；status/admission snapshot 也无条件 rewrite；sync service 再根据全部扫描 records 无条件 fan-out。rows aggregate 又把 `payload/raw_payload` 带入 materialized CTE，列表响应把 read-model 内部 `searchText` 和逐行 `sourceVersions` 一并返回。
- 修复：projection/status 使用 `IS DISTINCT FROM` 条件更新，未变化 record 不改子表；admission 只 replace 真实变化 scope；sync service 只消费 authoritative snapshot 的 `affected_scope_keys`，空集合不 fan-out。rows summary/facets 只 materialize typed columns，page SQL 在数据库侧移除内部 search/version 字段，顶层 source version 与惰性 detail API 合同不变。
- 隔离：没有新增 cache、worker、API、表、索引或共享 gateway；成本统计、Workbench 和其它页面只会少收到无业务变化的错误 refresh，真实 OA 变化仍按精确月份通过原 owner fan-out。
- 验证：相关后端 246 tests 通过；隔离真实 PostgreSQL 应用 0001–0108 后，重复同一 canonical commit 证明第二次 `affected_scope_keys=()`、`upserted_completed_count=0`，application/status `updated_at` 与 outbox count 均保持不变。
- 待生产门：发布后重跑 fresh 200/304、周期 sync 稳定窗口、三页面混合负载和 Page Audit；公网 `If-None-Match` 转发仍需用 live Nginx 配置证据闭合，不能用应用层自定义 query fallback。

### 生产二次根因：freshness inventory 扫描已完成历史

- 首轮发布后 100 次 fresh 首屏中 OA `p95=839.898ms`、`p99=927.939ms`；同机直连条件请求 30/30 返回 `304`，但 `p95=613.221ms`，证明瓶颈位于 ETag 前的 freshness gate，而非 rows/summary/传输。
- `oa_pending_payment_query_state` 的 `all` target inventory 原先把该 event type 的全部历史 outbox scope（包括 `done`）做 UNION。修复后只保留当前 blocking queue 状态；canonical watermark 与现存 projection scope 仍完整覆盖 fresh inventory，pending/processing/failed/dead-lettered 继续 fail closed。
- 该修复不新增表、索引、cache、worker 或 API，也不改变其它页面 query state；已完成历史仍保留在 durable queue 供审计/retention owner 使用，只是不再污染 OA 页面热路径。

### 生产三次根因：`all` rows 仍执行隐藏跨月去重

- freshness inventory 修复发布后，100 次公网 fresh 首屏为 `p50=172.319ms / p95=281.562ms / p99=332.722ms`；同一时段月分片 40 次为 `p95=148.708–157.301ms`，`all` 40 次为 `p95=264.499ms`，瓶颈限定在 OA 私有 `all` 读取。生产 7 个月份分片行数之和为 236，`all` 也是 236，当前没有跨 scope 重复。
- 旧链是 `all` rows 每次执行 `DISTINCT ON(row_id)`，用排序静默吞掉跨月重复；但 relation row identity 已包含月份，OA 主 row identity 稳定，重复应当作为 projection 错误暴露，而不是页面兼容行为。
- 修复删除 `deduped_oa_pending_payment_rows` 和 helper；fresh rows 直接读月份 projection。`oa_pending_payment_query_state` 在同一 set-based freshness statement 中检查跨 scope 重复并返回 `202`，Page Audit 改为按全局 `row_id` 报告涉及 scopes。没有新增缓存、索引、endpoint、read model、worker 或兼容分支。
- 隔离性：只改变 OA repository/freshness/Audit owner；成本统计、关联台、共享 read model、全局 PostgreSQL 配置和其它页面 response shape 不变。发布后仍以 100 次 fresh HTTP、三页混合负载和写后连续 Audit 作为最终门禁。

### 生产四次根因：summary/facets 与 bounded page 的数据库往返

- 隐藏去重删除后，100 次公网 fresh 首屏为 `p50=181.964ms / p95=265.130ms / p99=354.795ms`；正确率、freshness 和 Audit 均通过，但 `p95` 仍比 `250ms` 硬门高 `15.130ms`。同批服务端 profile 显示固定 8 个 query、数据库 `p95=124.852ms`，剩余瓶颈是 OA 私有读取编排，不是前端 render、共享连接池或其它页面 read model。
- 收敛方案：保留独立 freshness gate 和只读 repeatable-read snapshot，把 summary/facets 与 bounded page 合并为一个 repository data statement；typed summary CTE 仍不 materialize `payload/raw_payload`，page 仍按原 sort/filter 做 `limit/offset`，数据库直接移除内部 search/version 字段，response shape 不变。
- 不引入 cache、索引、cursor、第二 API、worker、schema 或共享抽象；只减少 OA repository 的一次 client/server roundtrip。真实 PostgreSQL canonical commit -> dependency worker -> OA worker -> fresh rows/ETag 集成测试通过，并由 SQL contract test 锁定单次有界 data statement。
- 最终门禁：精确 SHA 发布后重新采集 OA 100 次 isolated fresh HTTP；只有 `p95 <= 250ms`、`p99 <= 500ms`，且三页 mixed load、操作后连续 Audit 仍通过，才关闭生产性能任务。

### 生产五次根因：freshness gate latest dirty lookup 缺少同形索引

- 单 data statement 发布后，isolated 100 次为 `p50=160.674ms / p95=255.847ms / p99=336.651ms`；扩大到 500 次为 `p50=162.569ms / p95=290.028ms / p99=359.906ms`，500/500 均为 `200/fresh`，证明正确性稳定但 `p95` 仍未达标。
- 进程 rolling 512 样本为服务端 `p95=214.470ms`、数据库 `p95=110.519ms`、固定 7 queries；internal `304` 与 full `200` 对照进一步证明 freshness gate 占主要长尾。gate 对每个月份按 `source_version DESC, updated_at DESC, id DESC` 读取 latest dirty state，但现有通用索引只以 `updated_at DESC` 结尾。
- 修复只新增 `scope_type='oa_pending_payment'` 的 partial index，使索引顺序与 fail-closed latest-version 语义完全一致；不修改 SQL 判断、source vector、API、read model、cache、worker 或其它 scope_type 的索引行。该模式与成本统计已上线的 scope-private latest-version index 一致。
- 该索引发布后仍必须重新跑 isolated 500 次、三页 mixed load、Page Audit 和安全可逆操作后 Audit；不能仅凭索引存在宣称性能闭环。

### 生产六次根因：active OA outbox 证明缺少私有覆盖索引

- latest-dirty 私有索引发布后，isolated 500 次已达到 `p50=133.444ms / p95=218.414ms / p99=293.654ms`；成本统计和关联台各自 isolated 也达标，三页基线 Audit 均为 `pass/fresh/drained`。但 OA 单页面 3 并发 150 次为 `p50=310.866ms / p95=441.414ms / p99=508.731ms`，证明剩余长尾属于 OA 自身 freshness gate，并非另两页串扰。
- gate 同一 statement 既从 active OA outbox 枚举目标 scope，又为每个 scope 执行 blocking `exists`。现有 outbox 索引服务全局 App Status、worker claim 或历史指标，均包含其它 event type/status；没有与 OA 页面精确 predicate 同形的私有索引。
- 修复新增 migration `0110`，只索引 `event_type='oa_pending_payment.read_model.refresh'` 且 status 为 `pending/processing/failed/dead_lettered` 的 `(tenant_id, scope_key)`；`done` 历史和其它 read model 不进入索引。它同时覆盖 target inventory 与 blocking probe，不改变 SQL、freshness 语义、API、queue、worker、连接池或其它页面 read model。
- 50,000 条已完成 OA 历史加 1 条 active envelope 的隔离 PostgreSQL 计划为 `Index Only Scan`，执行 `0.026ms`、2 个 shared buffer、索引 `16kB`；0001–0110 全迁移和 canonical -> durable queue -> worker -> fresh rows/ETag 集成测试通过。发布后仍以三页 simultaneous mixed load 与操作后 Audit 作为关闭门，不用 isolated 成绩替代隔离性证据。
- 生产发布：精确 SHA `d3fc16026` 的 Nightly CI 成功，release `main-d3fc16026-oa-outbox-index-20260717` 完成激活；0110 应用 `248ms`，API、dispatcher、22 workers、readiness、前端 hash 和公网 session route 全部通过。
- 最终性能：浏览器等价持久连接 isolated 500 次为 `500/500 200/fresh`、`p50=127.936ms / p95=217.272ms / p99=262.054ms / max=393.551ms`；同一生产进程包含 mixed 样本的 rolling server profile 为 `p95=207.831ms / p99=272.479ms`，DB `p95=85.465ms`、连接获取 `p95=0.183ms`、固定 7 queries，达到服务端 `250/500ms` 门槛。
- simultaneous 隔离：三页每页一个并发请求、50 轮共 150 次全部 `200/fresh`；成本与关联台公网持久连接通过各自门槛。OA 公网客户端为 `p95=357.947ms / p99=379.540ms`，但同窗服务端仍在 `250/500ms` 内；差值来自同一探针同时传输关联台大 payload 的 WAN/client 竞争，不是 DB pool、query count 或跨页 read model 污染。不得为该探针差值扩大共享池或修改关联台合同。
- 操作后 Audit：test-owned turnover relation 通过正式 API confirm，旧 2026-07-13 场景的成本 query 参数/关联台数组位置和隔离页瞬时 202 已漂移，runner 因 post-probe 失败跳过自动撤回；随后复用确认的幂等响应取得精确 relation ID，并通过正式 turnover withdraw API恢复 `inactive`，未写 SQL。恢复后两轮三页 Audit 均为 `pass/fresh/drained`、`issues=0`、`database_snapshot=true`；OA Audit 约 `0.419s` 与 `0.374s`。
- 尚未关闭的代理门：公网首个 gzip 响应返回弱 ETag，但携带同一 `If-None-Match` 的持久连接请求仍返回完整 `200`、`99,958` bytes、约 `136ms`；live `/www/server/nginx/conf/nginx.conf` 的 `/fin-ops-api/` location 缺少模板已声明的 `proxy_set_header If-None-Match $http_if_none_match;`。应用弱比较已经正确，禁止添加应用 fallback。当前 `finops-deploy` sudo 白名单没有 Nginx test/reload 权限，因此 full `200` 的 `250/500ms` 门槛已通过，`304 p95<=30ms` 仍需 root/Nginx owner 同步一行配置、`nginx -t` 和 reload 后复验。

## 2026-07-17 - 生产 rows freshness Port 装配修复

- 生产证据：OA Page Audit 已返回 `pass/fresh/drained`，但相同发布版本的 `/api/oa-pending-payments/rows` 持续返回 `202/refreshing`，且 payload 没有 stale reasons；因此不是 source version、dirty/outbox 或 worker 未收敛。
- 根因：`PostgresStateStore` 已按模块边界提供 `OaPendingPaymentReadModelRepositoryPort`，`OaPendingPaymentReadModelService` 构造时又把它包装为第二层同类型 Port。外层无法发现内层底层 repository 的 snapshot/freshness 方法，固定进入 `api_freshness_proof_unavailable` fail-closed 分支。
- 修复：service 构造器保留已经是目标窄 Port 的依赖，只对原始 repository 做一次包装；没有增加 fallback、双读、缓存、兼容 API 或新抽象。
- 隔离性：只改变 OA rows query service 的依赖归一化；API shape、read model、worker、queue、scope、其它页面 repository 和共享 Page Audit 均不变。
- 测试责任：新增 API/service 回归，使用生产相同的预包装 Port 装配并锁定 freshness gate 与 rows query 各执行一次、结果为 `200/fresh`。


## 2026-07-16 - 生产 all fan-out 补齐 empty month scope inventory

- 生产证据：跨月 row 修复发布后，受影响的 33 个 canonical expected-set mismatch 已归零；显式 `oa_pending_payment=all --force-refresh` 后仍只有 7 个 read model scopes，而 dynamic fresh gate 从当前 tenant source watermarks 正确识别出 37 个月份，留下 37 个 `scope_missing/source_versions_mismatch`。
- 根因：projector 的 `list_scope_shards(all)` 从 completed/admission 非空数据枚举月份，遗漏已经有权威 source watermark 但 OA rows 为零的月份；query/readiness owner 则正确以 watermarks 为 scope inventory，两个 owner 不一致。
- 修复：all fan-out 显式接收 event tenant，并只从 `oa_pending_payment_source:<tenant>:<month>` watermarks 枚举月份；普通精确月份、month rebuild、CAS、prune 和 durable queue 语义不变。
- 旧链删除：all fan-out 不再调用 completed/admission `list_available_months()` 猜 scope；没有保留 union、fallback 或第二 inventory。
- 验证责任：repository test 锁定 tenant prefix 与 empty month；refresh service test 锁定 tenant 透传；发布后必须由同一正式 all force-refresh 自动生成全部月份并取得 OA Page Audit pass/fresh/drained。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-07-16 - 高性能、freshness 与 Audit 本地闭环

- 目标：将 OA 待付款首屏和刷新链路收敛为 PostgreSQL-only、精确月份、无 stale 展示的独立 read model 链路；目标 fresh API `p95 <= 250ms`、PostgreSQL commit-to-visible `p95 <= 1s`，500ms作为挑战目标。
- 架构：OA sync在一次PG事务中提交completed projection、in-progress admission、payment-status snapshot、source watermark和durable outbox；OA专属projector/worker只访问PostgreSQL。页面首屏只用rows聚合API，filter options随rows返回；500ms条件GET使用ETag/304，202立即隐藏旧rows并等待operation barrier。
- 写回一致性：`writeback-paid`和匹配成功的link-bank在MySQL成功后调用窄PG writer，同事务更新status snapshot、月份watermark和精确月份outbox。若MySQL已paid也继续尝试PG reconcile，解决“事实源已变但页面仍旧”的重试死角；PG失败返回可安全重试错误，下一次OA sync也可恢复。
- Audit：新增OA页面专属wrapper，输出“App内部数据一致 / 新数据正在生成 / 发现N个一致性问题 / Read model未在时限内更新 / 无法完成”五态中文文案；共享`PageAuditIcon`默认行为不变。
- 旧代码删除：移除旧filter route/client、`all_rows`和Python全量filter扫描、shared invoice worker OA分支、projector Mongo/MySQL I/O、snapshot relation/state-store fallback、server private OA adapter fallback；普通命令不再enqueue OA `all`。
- 测试：新增/更新snapshot原子提交和rollback、paid增量reconcile/idempotent retry、ETag 200/304/202、source-version/CAS、worker隔离、前端条件检查/202/barrier/Audit、旧路径guard和E2E请求计数。完整矩阵见`tests.md`。
- 本地性能守门：in-process test adapter各采集1000次，fresh 200为`p50 4.960ms / p95 5.874ms / p99 7.086ms`，ETag 304为`p50 4.807ms / p95 5.755ms / p99 7.484ms`，错误率均为0；304不执行rows aggregation。该结果未连接PostgreSQL，只证明HTTP/ETag编排开销，不作为生产SLO证据。
- 真实PostgreSQL闭环复核：隔离临时数据库执行全部107个migration后，发现并修复两个会阻断生产的窄缺口：snapshot writer把`YYYY-MM`直接cast为date，以及组合式`PostgresReadModelRepository`漏暴露OA的repeatable-read snapshot/freshness gate。修复后canonical commit、durable outbox、专属projector、CAS publish、queue complete、expected/actual vector、fresh rows和ETag/304全链通过，并固化为`test_oa_pending_payment_postgres_integration.py`。
- 本地真实PG性能门：在单月500行、连接池上限12、合成8并发下，fresh `200` 1000次为`p50 8.710ms / p95 9.938ms / p99 11.300ms`，8并发1000次为`p50 22.484ms / p95 33.243ms / p99 45.531ms`，304 1000次为`p50 0.361ms / p95 0.520ms / p99 0.629ms`，错误率均为0。200次canonical mutation从commit返回到fresh API为`p50 403.675ms / p95 544.178ms / p99 593.683ms`，200次均先fail-closed返回202，错误率0；projector `p95 435.400ms`，最终fresh API `p95 131.274ms`。冷启动commit返回到fresh为`282.284ms`。500行是2026-06-17文档所记历史生产总量210行的2.381倍，但当前生产峰值、浏览器500ms检测和render未测，因此只证明本地服务端性能门，不证明当前生产T0到T1 SLO。
- SQL证据：500行scope的`EXPLAIN (ANALYZE, BUFFERS)`为freshness gate `0.090ms`、aggregate/facets `5.755ms`、bounded page `0.306ms`；均为shared-buffer hit，无physical/temp read/write。fresh路径是1个gate加2个有界数据statement；304只有gate，不执行aggregate/page。没有性能证据要求新增索引、缓存或分区。
- 验证结果：OA后端/service/API/read-model/worker/manifest/边界目标矩阵`266/266`通过；真实PG集成`1/1`通过；OA组件测试`40/40`、OA Chromium链路`8/8`、全量前端`72 files / 849 tests`和production build通过；lint、docs、diff-check通过；隔离PG runtime-check返回`ready`且schema version 107。全量backend discovery运行4273 tests，因并行Workbench SQL initial-page测试夹具和Cost Statistics共享guard漂移仍为`125 failures / 55 errors / 34 skipped`；这些失败不在OA目标矩阵内，本任务未修改或放宽其断言。
- 状态：本地为`READY_FOR_UNIFIED_DEPLOYMENT`。按用户要求未部署、未访问生产、未执行migration/backfill/refresh。统一部署时必须先`oa.sync:all`建立canonical snapshot，再低优先级`oa_pending_payment:all`重建，最后采集1000次API/304和200次mutation样本；在此之前不宣称生产SLO已达标。

## 2026-07-07 - 付款状态二态化

- 目标：OA 待付款核对页只展示 `已支付` / `未支付`，移除 `待核对`、`支付少了` 等付款状态。
- 关键决策：付款状态以 active linked 付款关系为事实源；只要已配对，即使金额有差额、银行事实缺失或流水方向异常，也显示 `已支付`。这些异常只保留在 reason、金额字段和写回强校验中，不再污染状态枚举。
- I/O 边界：状态判定仍在 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService`；前端不按金额自算。OA 写回继续由 `writeback-paid` 命令复核 active relation、outflow、金额相等和 `flow_id`，前端只在 `oaPaymentWriteback.syncStatus=ready` 时展示写回按钮。
- 测试覆盖：更新 lifecycle policy、OA pending query service、页面 Vitest 和 Browser mock/fan-out 用例，锁定 `partially_paid` / `pending_review` 不再作为公开状态。

## 2026-07-06 - oa_pending_payment refresh 热路径 I/O 收敛

- 目标：压低生产 `oa_pending_payment:2026-06` read model refresh handler 耗时，消除外部往来款/进行中 OA worker 刷新时的可见抖动。
- 关键决策：不新增缓存层、不改 read model/API shape。月份 refresh 继续由 `invoice-usage-collection` worker 执行，但 completed 视图优先调用 OA projection 的 `list_application_records(month)`，同一 refresh 内复用 `DistributedInvoiceRelationContext` 的进项发票索引，且 `PaymentAdmittedOAProjectionAdapter` 已按 `t_payment_simple.flow_id` 准入过滤时跳过 query service 的二次支付状态表过滤。`oaPaymentWriteback` 复用单次 `list_payment_statuses` 结果，不再对每行调用 OA MySQL `get_payment_status`。
- 测试覆盖：更新 `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_projection_builder_reads_completed_from_unified_projection_and_in_progress_from_admission`，锁定单次 refresh 的 projection/发票/支付状态读取次数，并断言逐行 `get_payment_status` 调用数为 0。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 移除自动匹配写回并改为逐行写回

- 目标：移除 OA 待付款核对页“自动匹配写回”按钮和对应后端 route/service 旧链路；对支付状态为“已支付”且写回状态为“未写回”的行提供行内“写回”按钮。
- 关键决策：`writeback-paid` 不做候选匹配、不创建 relation，只复核已存在的 completed Workbench active relation 或 in-progress active pending relation，并校验 outflow、金额合计和 `flow_id` 后写回 `t_payment_simple.pay_status=1`。已写回行不显示按钮；已写回重复请求 no-op 且不 enqueue refresh。
- I/O 清理：删除前端 toolbar 旧按钮、`autoReconcile...` API/type、后端 `/api/oa-pending-payments/auto-reconcile-bank-transactions` route、`OaPendingPaymentCommandService.auto_reconcile_bank_transactions(...)` 和历史 promotion 中按旧 `source_action` 特判 `normal_match` 的分支；边界守卫保留旧 route/command 不可回流断言。
- 测试覆盖：后端 command/API 覆盖 completed relation 写回、in-progress pending relation 写回、已写回 no-op、无 paid relation 409；前端 Vitest 覆盖按钮显示/隐藏、写回请求 body、operation barrier、失败重试和 refreshing 时不展示；Playwright 覆盖真实浏览器逐行写回成功/失败闭环。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 模块边界 close 与旧写入口删除

- 目标：完成 OA 待付款核对模块的模块化 close，确认页面读路径、写路径、候选抽屉和 read model refresh 都有清晰边界和 I/O，删除会污染当前链路的旧模块代码。
- 关键决策：当前写入口是逐行 `writeback-paid` 与 `link-bank-transactions` 成功后的自动写回。删除旧人工 `/api/oa-pending-payments/confirm-paid` route 和 `OaPendingPaymentCommandService.confirm_paid(...)`，避免前端已移除的手工确认按钮在后端继续形成隐藏写入口。
- I/O 清理：`bank-transaction-candidates` 继续返回全部支出流水候选池并回显 `oaRowIds`，不再输出 `monthScopes`；API 合同同步删除“按 OA 月份收敛”和“写 Workbench active relation”的旧说法，明确 link-bank 写 OA 待付款独立 pending relation 与 bank claim。
- 测试覆盖：更新 API/command/runtime boundary guard，锁定旧 confirm-paid route/command 不可回流；更新候选 filters 断言，锁定不再输出 `monthScopes`；删除前端 Vitest 和 Playwright fixture 中的旧 confirm-paid handler。
- 验证命令：见本轮最终说明。

## 2026-06-30 - 月份选择器合并全部视图

- 目标：在 OA 待付款核对页顶部月份筛选中提供用户可见的“全部”视图，并把“全部”与原生月份选择合并成同一个控件。
- 关键决策：不新增 API 字段或 read model scope；“全部”继续使用空 `month` 查询值，具体月份继续传 `YYYY-MM`。控件用分段按钮 + `type="month"`，默认高亮“全部”，选择月份后取消高亮，点击“全部”清空月份。
- 文档影响：页面筛选 UI 和测试矩阵更新；模块边界、API response shape、read model/worker 合同不变。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，锁定默认不传 `month`、选择月份传 `month=YYYY-MM`、点击“全部”清除 `month`，并补充合并控件 CSS contract。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。

## 2026-06-30 - 右侧抽屉候选流水增加分页入口

- 目标：候选接口返回 `100 / 743` 这类超过首屏的结果时，用户可以继续浏览后续支出流水。
- 关键决策：复用既有 `bank-transaction-candidates` 的 `page/page_size/total` 合同，只在 `OaBankLinkDrawer` 内增加页码状态和上一页/下一页按钮；筛选和搜索变更回到第 1 页，翻页保留已选 `oa_row_ids` 与 relation status。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，锁定候选抽屉页码显示、下一页请求参数、切换分类重置页码。

## 2026-06-30 - 右侧抽屉候选流水改为全量支出流水池

- 目标：进行中 OA 右侧“关联支出流水”抽屉不再因 OA 月份或 OA 月份解析失败显示空候选；用户可以在全部支出流水中按全部、未配对、已配对、已关联进行中 OA 分类筛选。
- 关键决策：`oa_row_ids` 仍由前端传给候选接口和提交接口，但候选读取不再用它推导月份 scope；候选服务直接读取 `month=all` 的支出流水，再用 Workbench active relation 与 OA pending payment bank claim 计算 relation status。只有 `unmatched` 流水可提交关联。
- 测试覆盖：更新 `tests/test_oa_pending_payment_command_service.py`，锁定已选 OA 返回全部月份候选、OA 缺月份仍返回候选、四个 relation status tab 分类；更新 `tests/test_oa_pending_payment_api.py`，锁定应用组装后的 in-progress OA source 与全量候选行为；继续跑 `web/src/test/OaPendingPaymentsPage.test.tsx` 保护前端请求携带 `oa_row_ids`。

## 2026-06-25 - route-owner local server.py audit

- 目标：在 `/api/oa-pending-payments*` route callback collapse 后，审计 OA 待付款剩余 `Application` 表面是否还有本地 implementation gap。
- 结论：本地 `server.py` route-owner 支持已 accounted；剩余方法是 query/route/command/read-model service composition、pending relation repository provider、payment-admitted projection/source adapter provider、source-version provider、refresh gateway port、auth/session adapter 或 shared invoice-usage invalidation fan-out，不再承载 OA 待付款私有 HTTP callback、read-model payload 或 command 业务实现。
- 文档影响：更新 modular IO autonomous state；产品/API 长期语义未变化。
- 测试覆盖：沿用 OA pending payment API 回归和 `test_oa_pending_payment_routes_use_route_owner` Guard；本条为审计 slice，无运行时代码变更。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_pending_payment_routes_use_route_owner -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/OA/worker/App Status/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - route callback collapse

- 目标：把 `/api/oa-pending-payments*` HTTP dispatch 从 `Application` 移入 `OaPendingPaymentApiRoutes.route(...)`。
- 改动：route owner 新增 `route(...)` 和 `configure_platform_ports(...)`；通过显式 read-session、write-auth、body loader、JSON response 和 error response ports 处理 rows/filter-options/detail/candidates/confirm-paid/auto-reconcile/link-bank；`server.py` 删除 `_handle_api_oa_pending_payments*` callbacks 和 `_oa_pending_payment_sql_payload_status(...)`。
- 保持不变：read-model freshness/source-version/detail unavailable 仍由 `OaPendingPaymentReadModelService` 负责；自动匹配、写回和支出流水关联仍由 `OaPendingPaymentCommandService` 负责；API payload 和业务语义不变。
- 测试覆盖：更新 `tests/test_oa_pending_payment_api.py`，不再依赖被删除的 app callback 名称；新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_oa_pending_payment_routes_use_route_owner` 防止 callback 回流。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_oa_pending_payments.py backend/src/fin_ops_platform/app/server.py tests/test_oa_pending_payment_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_pending_payment_routes_use_route_owner -v`。
- 未测风险：真实 PostgreSQL/OA/worker/App Status/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-25 - route-owner audit

- 目标：审计 `/api/oa-pending-payments*` 在 `server.py` 中的剩余 HTTP callback 是否仍承载业务/read-model/command 逻辑。
- 结论：`OaPendingPaymentApiRoutes` 已拥有 rows/filter/detail/candidates/confirm-paid/auto-reconcile/link-bank 方法；`OaPendingPaymentReadModelService` 拥有 freshness/source-version/detail unavailable 语义；`OaPendingPaymentCommandService` 拥有自动匹配、写回和支出流水关联语义。`server.py` 剩余 callbacks 是 auth/session、body、write actor、JSON/error/status mapping。
- 下一步：选择 `server-py:oa-pending-payment-route-callback-collapse`，把 HTTP dispatch 移到 `OaPendingPaymentApiRoutes.route(...)`，用显式 read-session/write-auth/body/JSON/error ports 替代 app-owned callbacks。
- 文档影响：更新 modular IO autonomous state；产品/API 长期语义未变化。
- 未测风险：真实 PostgreSQL/OA/worker/App Status/browser evidence 仍保留到后续生产验证阶段；本 slice 不声明模块或全局闭环。

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 `pending_invoice` 本地实现支持 accounted 后，评估 OA 待付款是否适合作为下一个非 Go read model 试点。
- 决策：选择 `oa_pending_payment`，下一条边界为 `read-models:oa-pending-payment-repository-port-extraction`。
- 理由：本模块同时覆盖 completed OA projection、in-progress payment-admitted OA、Workbench relation、invoice lifecycle 和 pending bank claim，是高可见、跨事实源、容易出现 stale-read bug 的页面；已有 read model service、manifest 合同和测试矩阵，适合延续 repository port 首切模式。
- 首切范围：新增 `OaPendingPaymentReadModelRepositoryPort`，只暴露 rows/detail/save/mark/prune read model 方法；不改 OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service、UI workflow 或 shared worker event semantics。
- 状态：Go/Fiber/Go Worker admission 继续 blocked。

## 2026-06-24 - read model repository port extraction

- 目标：把 OA 待付款 rows/detail 读取和 projection save/mark/prune 从宽 read model repository surface 收敛到 `OaPendingPaymentReadModelRepositoryPort`。
- 改动：新增 OA pending payment read-model port；Postgres runtime 下 `oa_pending_payment_sql_read_repository` 返回该 port；`InvoiceUsageCollectionSqlProjectionBuilder` 和 worker 的 OA pending payment projection 写入路径使用该 port。
- 边界决策：Workbench relation source-version proof 不挂在 OA port 上，改由 Workbench relation port 提供，防止关系事实源污染 OA read-model repository 边界。
- 保持不变：completed/in-progress rows、filter-options/detail API shape、OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service、UI workflow 和 shared worker event semantics 不变。
- 测试覆盖：新增 port shape guard 和 source-version owner 回归；复跑 OA API fresh/stale/source-version 目标测试，以及 invoice usage collection projection save/mark/prune/fan-out 目标测试。
- 后续事项：继续执行 `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`。

## 2026-06-24 - read model freshness / operation barrier audit

- 目标：审计 OA 待付款 read model fresh gate、force refresh、`all` fan-out/month proof、source-version proof 和写后 operation barrier 行为。
- 当时发现：后端命令响应会返回具体月份 scope 与 `all`，例如 `["2026-05", "all"]`；但前端默认 all 视图会优先等待 `oa_pending_payment:all`，容易把 fan-out-only control scope 当作写后可见性证明。该历史契约已在 2026-07-16 被 exact-month-only 写后响应与 barrier 契约替代，当前响应不得再暴露 `all`。
- 改动：`OaPendingPaymentsPage` 在当前视图为 `all` 且 mutation 响应包含具体月份时，改为等待具体 `oa_pending_payment:<YYYY-MM>` barrier target；只有没有具体 scope 时才 fallback 到 `all`。
- 保持不变：OA 支付状态语义、OA MySQL 写回、payment-admitted source adapter、pending relation promotion、command service、API response shape、worker event semantics 不变。
- 当时测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，锁定 auto-reconcile 与 link-bank 成功后，历史响应中的 `scopeKeys: ["2026-05", "all"]` 会请求 `oa_pending_payment:2026-05` barrier，而不是优先请求 `all`；2026-07-16 起当前测试直接锁定响应只含 exact month。
- 后续事项：继续执行 `read-models:oa-pending-payment-local-implementation-closure-audit`，确认是否还有本地非 Go 实现缺口，并记录真实生产 PostgreSQL/worker/App Status/high-row/browser evidence defer。

## 2026-06-23 - 右侧抽屉候选流水按已选 OA 月份收敛

- 目标：修复 OA 待付款核对进行中视图中，勾选 OA 后打开“关联支出流水”右侧抽屉长期停留在“加载中”的问题。
- 影响范围：`OaPendingPaymentCommandService.bank_transaction_candidates`、`fetchOaPendingPaymentBankCandidates`、`OaBankLinkDrawer`、API/command/page 回归测试和本模块维护文档；`link-bank-transactions` 提交、pending relation、bank claim 和自动写回语义不变。
- 真实原因：抽屉虽然从一个已选 OA 打开，但前端没有把已选 OA row id 传给候选接口；后端因此每次都按 `month=all` 读取全部历史支出流水，并为这些历史流水计算 Workbench active relation 与 OA pending bank claim 状态。生产历史流水多时，金额搜索如 `2152` 仍要先完成全量候选与关系状态扫描，页面就表现为右侧抽屉一直“加载中”。这不是流水不存在，也不是前端筛选按钮问题。
- 关键决策：抽屉有已选 OA 上下文时，前端必须传 repeated `oa_row_ids`；后端基于这些 OA 的 `month` 得出候选月份，只读取对应月份的支出流水并去重，再执行 relation status 和关键字筛选。没有 OA 上下文的旧调用继续保留 `all` 语义；有 OA id 但无法解析月份时返回空候选，不回退到全量历史扫描。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md` 和 `e2e-coverage.md`；产品口径仍是“人工抽屉作为自动匹配失败后的兜底”，只是候选读取边界从全量历史收敛到已选 OA 所在月份。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_bank_transaction_candidates_uses_selected_oa_month_scope` 和 `::test_bank_transaction_candidates_with_selected_oa_does_not_fallback_all_when_month_missing`；更新 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_bank_transaction_candidates_route_delegates_to_command_service` 锁定 repeated `oa_row_ids` 透传；更新 `web/src/test/OaPendingPaymentsPage.test.tsx::switches to in-progress OA view and links bank payment with automatic writeback` 锁定抽屉候选请求携带已选 OA row id。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地自动化没有连接真实生产 OA/Mongo/PostgreSQL/银行流水库和真实浏览器会话；发布后仍需用截图中的 `2152.80` 进行中 OA 样本确认候选接口返回对应月份流水，并观察生产请求耗时。

## 2026-06-23 - 准入源消失后释放进行中 OA pending relation

- 目标：修复进行中 OA 曾经通过 `t_payment_simple.flow_id` 准入并关联支出流水，但后续不再出现在当前准入集合时，流水被 active pending claim 占用，既不在 OA 待付款 read model 展示，也不回到关联台的问题。
- 影响范围：`InvoiceUsageCollectionSqlProjectionBuilder.rebuild_oa_pending_payment_read_model_scope`、`PostgresOaPendingPaymentRelationRepository` / snapshot repository、OA pending read model refresh 和 Workbench pending claim 排除链路；不改变 completed OA promotion 语义。
- 关键决策：只有在支付状态 repository 存在且 read model refresh 成功读取当前准入集合后，才取消同月 active pending relation 中 `oa_row_ids` 完全不在准入集合内的关系，并释放对应 `app.bank_transaction_relation_claims`。准入源不可用时跳过释放，避免把外部依赖故障误判为 OA 不再准入。
- 文档影响：同步本实施记录和 `tests.md`；产品口径仍是 in-progress 只以 `t_payment_simple.flow_id` 当前准入为主行事实源。
- 测试覆盖：新增 `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_projection_builder_releases_pending_relation_when_oa_admission_disappears`，覆盖已不准入 OA 的 active pending relation 被取消、bank claim 被释放，仍准入 OA 正常进入 read model；新增 `::test_projection_builder_does_not_release_pending_relation_when_oa_admission_projection_is_refreshing`，锁定 OA admission projection 非 ready 时不释放 claim。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地测试使用 synthetic repository，不连接真实生产 MySQL；发布后需要在生产/预发确认对应 flow_id 当前不在 `t_payment_simple` 准入集合，并通过正式 worker refresh 释放 claim。

## 2026-06-23 - 多 OA 多流水 relation 聚合成员补全

- 目标：修复 OA 待付款核对中同一 Workbench active relation 已包含多条 OA 与多条支出流水时，OA 侧可能只显示主 OA 金额、缺少 `+N`，并把支出合计大于主 OA 金额误判为 `pending_review` 的场景。
- 影响范围：`OaPendingPaymentQueryService` relation group 构建、`DistributedInvoiceRelationContext` OA row lookup 使用、服务层回归测试和本模块测试矩阵；前端 API contract 不变，继续消费 `oa.relationCount/detailMode/summaries` 与 `bankTransaction.relationCount/detailMode/summaries`。
- 关键决策：relation 分组时不能只使用当前视图首轮 `list_all_application_records()` 中已经枚举到的主 OA；必须基于 relation 的 OA row ids 通过 OA projection lookup 补齐同一 relation 内可权威读取的 OA records，再计算 OA 合计、付款状态和 `+N`。进入聚合行的 OA 成员继续作为同一 relation owner，不再生成 standalone OA pending row。
- 文档影响：更新 `tests.md`；产品/API 长期口径不变，这是对既有“多 OA/多流水 relation 聚合成一行”合同的补漏。
- 测试覆盖：新增 `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_relation_group_loads_all_oa_members_from_projection_lookup_and_suppresses_standalone_rows`，复现 list-all 只返回主 OA 但 relation lookup 能读出 3 条 OA 的场景，断言 rows 只返回 1 条聚合行、OA 合计 `587000.00`、OA `relationCount=3`、流水 `relationCount=4` 且付款状态为 `paid`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地 synthetic projection 不替代真实生产 OA Mongo/Postgres projection、真实 worker drain 和截图样本 read model 重建；发布后需要用该 relation 样本确认 rows payload 的 `oa.summaries` 完整并且页面显示 OA `+2`。

## 2026-06-22 - completed OA 已匹配流水自动写回补漏

- 目标：修复 OA 待付款核对页 completed OA 已显示支出流水配对但 `oaPaymentWriteback` 仍为“未写回”的场景，并处理截图中自动写回请求被 `/fin-ops/api/*` SPA HTML fallback 吞掉后无法命中后端 API 的问题。
- 影响范围：`OaPendingPaymentCommandService` active relation ID 解析、共享 `apiClient` HTML fallback、`OaPendingPaymentsPage` 自动写回失败后的重试行为、command/api/page 前端测试和本模块状态机/测试矩阵；业务口径不变，仍是 completed/in-progress 已有有效支出流水 active relation 且金额相等时自动写回 `t_payment_simple.pay_status=1`。
- 关键决策：自动写回处理 existing active relation 时，不能只依赖 `row_ids/row_types` 同时存在；部分 relation/distribution payload 可能有 `oa_row_ids`、`bank_transaction_ids` 或 camelCase 字段但 `row_types` 为空。命令服务现在先读显式 OA/银行 ID 字段，再按 `row_ids` 和 row id 前缀推断类型，避免静默跳过 completed 写回。前端 API fallback 同时兼容根 `/api/*` 和 `/fin-ops/api/*` 返回 HTML 的路径错配；自动写回请求失败后不把 scope 永久标记完成，用户刷新后可重试。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；部署长期口径仍要求 Nginx `/api/`、`/fin-ops/api/`、`/fin-ops-api/` 都返回 JSON API，不应依赖前端 fallback 作为唯一修复。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_writes_completed_oa_from_explicit_relation_ids_when_row_types_are_missing`；新增 `web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when a fin-ops relative API request returns HTML`；新增 `web/src/test/OaPendingPaymentsPage.test.tsx::retries auto reconcile after a failed attempt when the user refreshes rows`；既有 API/page 回归继续覆盖 auto-reconcile 路由、写后 barrier 和页面自动写回。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地没有真实 OA MySQL、生产 Nginx、真实 OA/Mongo/PostgreSQL/RabbitMQ worker drain；发布后仍需用截图中 completed OA 样本确认 `/fin-ops-api/api/oa-pending-payments/auto-reconcile-bank-transactions` 返回 JSON，`t_payment_simple.flow_id` 对应记录变为 `pay_status=1`，read model fresh 后页面显示“已写回”。

## 2026-06-22 - 自动匹配等待 read model fresh 与 API fallback

- 目标：修复 OA 待付款核对页在 rows/read model 仍显示“同步中”时仍立即触发后台自动匹配/写回，并且当根 `/api/*` 请求被前端 HTML fallback 吞掉时把 `接口返回了 HTML 页面` 错误直接暴露给用户的问题。
- 影响范围：`OaPendingPaymentsPage` 自动匹配 effect、共享 `apiClient` HTML fallback 处理、前端回归测试和本模块状态机/测试矩阵；后端 API endpoint、匹配规则、read model freshness gate 和 OA MySQL 写回语义不变。
- 关键决策：自动匹配/写回是写命令，必须在 rows/filter-options 加载完成且 `oa_pending_payment` read model 为 fresh 后才触发；refreshing/stale/unavailable 或 rows 加载失败时只展示同步/错误状态，不叠加写命令。前端 API 仅在 `/fin-ops/` 页面下确认根 `/api/*` 返回 HTML shell 时重试 canonical `/fin-ops-api/*`，JSON 错误和非 HTML 响应仍按原契约处理。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；部署/Nginx 长期口径不变，真实代理仍应保证 `/api/`、`/fin-ops/api/`、`/fin-ops-api/` 返回 JSON API 而不是 HTML。
- 测试覆盖：新增/更新 `web/src/test/OaPendingPaymentsPage.test.tsx::does not auto reconcile while OA pending payment read model is still refreshing` 和 `web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when root API returns the SPA shell under fin-ops`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：生产 App Status 中 `Workbench read model generation consistency failed` 仍表示运行时/worker/readiness 层有独立问题，需要用生产只读 App Health、dirty scopes、outbox 和 worker journal 继续定位；本地修复只防止页面在 non-fresh 状态下额外发写命令，并提高 API prefix 临时错配恢复能力。

## 2026-06-22 - 自动匹配跳过诊断

- 目标：排查“金额、对方名和日期看似满足规则但未自动配对”的进行中 OA 场景，补齐自动匹配失败的可观测性。
- 影响范围：`OaPendingPaymentCommandService.auto_reconcile_bank_transactions` 响应、前端 `AutoReconcileOaPendingPaymentBankTransactionsResponse` 类型、command service 回归测试和本模块测试矩阵；自动匹配业务规则不变。
- 关键决策：规则层已能对“云南心诚环保科技有限公司 / 7000 / 2026-04-16 -> 2026-04-23”生成 `oa_bank_exact_amount` 候选；当候选在确认 relation、解析 `flow_id` 或 OA MySQL 写回阶段失败时，后端不再静默吞掉，而是在 `skippedAutoMatches` 返回 OA/流水 row、规则码、错误码、消息和 details，便于现场判断是 row 占用、`flow_id` 缺失、写回不可用还是 relation 冲突。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、状态机和 read model freshness 语义不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_reports_skipped_exact_match_when_flow_id_is_missing`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地没有真实生产 OA/Mongo/MySQL/PostgreSQL 数据，无法直接确认截图中那条记录的生产 `flow_id`、active relation 占用和写回错误；发布后需要用该月份调用 auto-reconcile 接口查看 `skippedAutoMatches`。

## 2026-06-22 - 自动匹配 relation 持久化闭环

- 目标：修复生产 `威斯达昆明信息技术有限责任公司 / 163000 / 2026-02` 自动匹配返回成功后，页面 read model 仍显示未关联支出流水，且重复执行 auto-reconcile 仍继续返回相同 3 条自动匹配的问题。
- 影响范围：`Application._oa_pending_payment_command_service` 的 Workbench relation command service 组装、OA 待付款自动匹配 relation 持久化、重复执行幂等性和 read model 刷新；匹配规则、前端 API contract、OA MySQL 写回逻辑不变。
- 关键决策：真实原因不是规则不匹配，也不是 OA 支付状态未写回。生产验证显示目标 `flow_id=69a262c6db8c0a3633bd74a2` 已经 `pay_status=1`，但 `active_relations_for_row_ids` 查不到 `oa-pay-69a262c6db8c0a3633bd74a2` / `txn_imported_1185` 的 active relation，read model 因没有持久化 relation 继续判定“未关联支出流水”。OA 待付款命令服务原来注入默认 `_workbench_relation_command_service()`，该默认 repository 只更新当前进程内存 snapshot；不像 Workbench 主路由那样在路由层另行调用 `_persist_workbench_pair_relations`。现在 OA 待付款命令服务注入 `repository=self._state_store`，让自动确认 relation 同步落持久层，worker/read model 和后续进程都能读到。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、匹配规则、状态机和接口字段不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_persists_relation_and_reload_is_noop`，断言第一次 auto-reconcile 后 state store 持久化 OA-bank relation；用同一 data dir 重建应用后再次 auto-reconcile 必须 `autoMatchedCount=0`、`writebackCount=0`、不重复写回。
- 生产验证：发布 release `main-6652abe4-20260622124730` 后，目标自动匹配 relation `OA-PAY-63d72411227871d3` 已持久化，row_ids 为 `oa-pay-69a262c6db8c0a3633bd74a2` 与 `txn_imported_1185`；重建应用实例后 active relation 可读，重复 auto-reconcile 返回 `autoMatchedCount=0`、`writebackCount=0`；`oa_pending_payment:2026-02` read model fresh，目标行 `paymentStatus=paid`，`bankTransaction.primaryBankTransactionId=txn_imported_1185`，金额 `163000.00`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：未跑浏览器端截图验证；后端生产 read model payload 已确认页面表格使用的 `bankTransaction` 字段完整。

## 2026-06-22 - 进行中 OA 自动匹配投影源闭环

- 目标：修复生产 `威斯达昆明信息技术有限责任公司 / 163000 / 2026-02` 页面 fresh 展示进行中 OA，但页面级 auto-reconcile 没有自动关联同名同额支出流水的问题。
- 影响范围：`Application._oa_pending_payment_projection` 的服务组装缓存边界、`OaPendingPaymentCommandService.auto_reconcile_bank_transactions` 的 in-progress OA 输入、应用层 API 回归测试和本模块测试矩阵；匹配规则、API endpoint、read model freshness 语义不变。
- 关键决策：真实原因不是 OA-bank 规则不匹配。生产诊断显示 read model 中目标 OA `oa-pay-69a262c6db8c0a3633bd74a2` fresh 存在，支出流水 `txn_imported_1185` eligible；但命令服务的 payment-admitted projection 被生产启动时显式传入的 `PostgresOAProjectionAdapter` 缓存污染，实时扫描 `in_progress_records=0`。显式 `source_adapter` 创建的 OA 待付款投影现在只作为调用点局部对象，不写入默认 lazy projection 缓存；自动匹配命令默认 lazy path 会重新使用 Mongo-backed source adapter，确保与页面 in-progress OA 可见性一致。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、状态机、匹配规则和 read model freshness 语义不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_uses_payment_admitted_source_after_completed_projection_cache`，复现生产初始化顺序：先用 completed/Postgres 投影创建显式 projection，再执行 auto-reconcile，断言仍能读取 payment-admitted in-progress OA 并生成 `oa_bank_exact_amount` 写回。
- 验证命令：本轮最终说明列出完整命令。
- 生产验证：发布 release `main-6652abe4-20260622124730` 后，目标 2026-02 样本能生成并确认 `oa_bank_exact_amount`；详见上方 relation 持久化闭环验证。
- 未测风险：未跑浏览器端截图验证。

## 2026-06-22 - 撤销 completed 指纹排除，进行中只按 flow_id 准入

- 目标：修正“completed 正本排除 in-progress 影子行”的错误口径。业务允许同项目、同供应商、同金额、同事由发起多张不同 OA；这些字段不是付款申请唯一身份。
- 关键决策：`in_progress` 主行身份只由 `t_payment_simple.flow_id` 准入、OA Mongo `_id` 匹配和当前 workflow status 决定。不得再用 completed projection 的业务字段指纹反向排除进行中 OA；不同 `flow_id` 必须作为不同付款申请保留。
- 测试覆盖：更新 `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_in_progress_view_keeps_payment_admitted_record_when_completed_projection_has_same_business_record`，锁定 completed 中存在同业务字段正本时，payment-admitted 的进行中 OA 仍展示。
- 风险控制：展示层保留不同 flow id；自动匹配层若同一支出流水同时命中多张同额 OA，不能强行确认，应按既有冲突/歧义路径留给人工关联或更强证据判定。

## 2026-06-22 - 已完成 OA 的进行中影子行去重（已撤销）

- 目标：修复生产 `云南心诚环保科技有限公司 / 7000 / 2026-04` 在“进行中 OA”中显示未配对，但真实 completed 行已关联支出流水的重复展示问题。
- 影响范围：`OaPendingPaymentQueryService` 的 in-progress 视图过滤、`invoice-usage-collection` 重建 `oa_pending_payment` read model 的结果、服务层回归测试和本模块测试矩阵；Workbench relation、自动匹配规则和前端 API contract 不变。
- 关键决策（历史，已撤销）：当时认为生产中旧 in-progress 行使用 Mongo 旧 row id（如 `oa-pay-69e5c2a3...`）、真实 completed 行使用请求号 row id（如 `oa-pay-2094`），两者业务字段相同但 row id 不同，因此用月份、类型、申请人、项目、对方、金额、申请日期、开户行、收款账号和事由组成业务指纹排除 in-progress payment-admitted 记录。该假设后来被确认不成立，因为业务允许相同业务字段的不同 OA。
- 文档影响：更新本实施记录和 `tests.md`；产品口径不变，仍是 completed/in-progress 两视图，只是避免同一业务单跨投影重复展示。
- 测试覆盖（历史，已替换）：原 `test_in_progress_view_hides_payment_admitted_shadow_when_completed_projection_has_same_business_record` 已由保留不同 flow id 的回归测试替代。
- 生产验证：发布 release `main-6652abe4-20260622115629` 后重建 `oa_pending_payment:2026-04`，rows API 返回 `in_progress.total=0`、`summary.viewCounts.in_progress=0`；completed 视图保留 `oa-pay-2094`，付款状态 `paid`，支出流水 `txn_imported_1521`。
- 未测风险（历史，已关闭）：真实业务已确认允许同日同申请人同项目同对方同金额同账号同事由的两张不同付款申请，因此不能使用业务指纹作为跨 flow id 排除依据。

## 2026-06-22 - 刷新态分页与自动写回幂等闭环

- 目标：修复 OA 待付款核对页 rows read model 刷新中时分页显示 `NaN-NaN / undefined`，并避免已有 active 支出流水 relation 且 OA 已写回时，页面级自动写回每次进入页面都重复入队刷新，导致用户长期看到“数据正在刷新”。
- 影响范围：`OaPendingPaymentsPage`、`OaPendingPaymentsTable`、`OaPendingPaymentReadModelService.refreshing_rows_payload`、`OaPendingPaymentCommandService` 自动写回分支、组件/API/command 回归测试和本模块测试矩阵；业务匹配规则、read model freshness gate 和 API endpoint 不变。
- 关键决策：刷新态 payload 也必须返回稳定 `summary.rowCount=0` 与 `summary.viewCounts` shape；前端分页只信任有限数值并把缺失/非数值 total 归零，不用 `0 || undefined` 这类 truthy fallback。已有 relation 的自动写回先读取同一 `flow_id` 当前支付状态，已经 `pay_status=1` 时视为 no-op，不增加 `writebackCount`、不返回写回记录、不触发 read model refresh。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug 回归库；长期产品/API 口径不变。
- 测试覆盖：后端 command 测试覆盖“active relation 且 OA 已写回”no-op，不重复 mark-paid 或入队；API 测试覆盖 rows/filter-options refreshing payload summary shape；前端 Vitest 覆盖 refreshing rows 空 summary 时不显示真实空态，也不渲染 `NaN` 或 `undefined` 分页。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service -v`；`cd web && npx vitest run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地自动化没有连接真实 OA MySQL/PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实环境仍需在发布后确认 App Health 的 `oa_pending_payment` read model 从 refreshing 回到 fresh，且 rows 分页不再出现 `NaN/undefined`。

## 2026-06-22 - 写后 operation barrier

- 目标：修复写操作成功后前端立即刷新 rows，可能读到旧 `oa_pending_payment` read model 的缺口。该记录创建时覆盖进行中 OA `confirm-paid`、`link-bank-transactions` 和支出流水无需开票规则保存；2026-06-22 自动匹配/写回上线后，前端主写回入口由 auto-reconcile 替代 `confirm-paid`。
- 影响范围：`OaPendingPaymentsPage`、`PendingInvoiceRulesDrawer` async callback contract、`operationBarrier` 前端 label、`OaPendingPaymentsPage.test.tsx` 和本模块测试矩阵；后端 API contract 不变，confirm/link 继续复用响应中的 `readModelRefresh.scopeKeys`。
- 关键决策：前端写 API 成功后先用当前页面可见 scope 构造 `oa_pending_payment` operation barrier target，barrier fresh 后才 `loadRows("refresh")`；barrier blocked/timeout 属于 post-commit 同步未完成，只显示“后台同步尚未完成”，不把已成功写入渲染成操作失败，也不提前读取旧投影。
- 测试覆盖：新增/维护 Vitest 回归，锁定写回、link-bank 和规则保存，在 barrier resolve 前不得增加 rows 请求；当后端返回具体月份 scope 与 `all` 时，写回和 link-bank 优先等待具体 `oa_pending_payment:<YYYY-MM>`，无具体 scope 的规则保存 fallback 到当前可见 scope。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`。

## 2026-06-22 - OA 自动匹配支出流水并自动写回

- 目标：取消 OA 待付款页面的人工写回入口，让进行中 OA 自动匹配未配对支出流水；completed 和 in-progress 只要已有有效支出流水 active relation 且金额相等，都自动写回 `t_payment_simple.pay_status=1`。
- 影响范围：`OaPendingPaymentCommandService`、`/api/oa-pending-payments/auto-reconcile-bank-transactions`、`link-bank-transactions` 响应、`OaPendingPaymentsPage` 自动 reconcile effect、`OaPendingPaymentsTable`、前端 API/types、Browser mock、模块/API/E2E 文档和相关测试。
- 关键决策：自动匹配只复用关联台 OA-bank 精确金额/精确合计规则；不做模糊匹配。候选 relation 不写回；写回必须基于 completed Workbench active relation、in-progress active pending relation 或自动命令刚确认的 pending relation，并通过 outflow、金额相等和 `flow_id` 校验。支出流水抽屉保留为自动匹配失败后的人工兜底，但提交成功后同样自动写回。
- 文档影响：更新 README、state-machine、tests、e2e-spec、e2e-coverage、implementation-notes 和 `docs/dev/api-contracts.md`。
- 测试覆盖：后端 command/API 覆盖自动匹配未配对支出流水、已有 relation 写回、link-bank 自动写回和金额不匹配不写回；前端 Vitest 覆盖 auto-reconcile、无人工按钮、operation barrier、link-bank 写回消息；Playwright 覆盖自动写回成功/失败和抽屉关联后自动写回。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地 mock/单测不替代真实 OA MySQL、真实 OA Mongo 字段变体、真实 Workbench 大数据和生产 worker drain；需要 staging 用真实进行中 OA 与支出流水样本做 smoke。

## 2026-06-22 - 进行中 OA relation 独立事实源与 promotion 闭环

- 目标：修复进行中 OA 自动/人工关联支出流水后进入关联台的问题，并解决 OA 从进行中变为已完成后的关系归属闭环。
- 影响范围：`OaPendingPaymentCommandService`、`OaPendingPaymentQueryService`、`OaPendingPaymentRelationPromotionService`、`PostgresOaPendingPaymentRelationRepository`、`SnapshotOaPendingPaymentRelationRepository`、`OAProjectionSyncService`、`WorkbenchRelationSqlProjectionBuilder`、Postgres migration 0073、worker 组装链路、模块文档和测试矩阵。
- 关键决策：进行中 OA 的 OA-流水关系写入 `app.oa_pending_payment_bank_relations`，支出流水占用写入 `app.bank_transaction_relation_claims`，不写 `app.workbench_pair_relations`。关联台 read model 读取 active pending bank claim 后排除对应流水，避免它作为未配对/候选进入关联台。OA sync 发现 active pending relation 的所有 OA row 已 completed 后，复用 Workbench relation command promotion 成普通 `manual_confirmed`/`normal_match` active relation，并把 pending relation 标记为 `promoted`、释放 claim。
- 迁移决策：migration `0073_oa_pending_payment_bank_relations.sql` 将历史 `special_metadata.origin=oa_pending_payment_in_progress` 的 Workbench active relation 迁移到 OA 待付款独立 pending relation 和 bank claim，同时撤回旧 Workbench active relation，避免关联台继续显示进行中 OA。
- 性能决策：候选排除走月度 active claim 集合和索引，Workbench active generation 与 workbench relation projection 每个 scope 各一次查询 active pending bank claim，避免逐行查库；pending relation 查询使用 GIN overlap 索引。
- 测试覆盖：新增/更新 command/API/query service 测试、Workbench relation SQL projection 测试、promotion service 测试、OA sync promoter fan-out 测试、migration schema/allowlist 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_sql_projection tests.test_oa_pending_payment_relation_promotion_service tests.test_oa_projection_sync_service tests.test_postgres_migrations -v`。
- 未测风险：未在真实生产 Postgres 上执行 migration 0073、真实 OA sync promotion、真实 worker drain 和真实页面 smoke；发布后需确认历史 `origin=oa_pending_payment_in_progress` Workbench active relation 已撤回，pending relation promotion 后关联台出现普通 completed relation。

## 2026-06-22 - OA 待付款表格 OA 区域五列压缩

- 目标：让 OA 大列内直接显示“申请人 / 项目 / 申请事由 / 对方户名 / 金额”，同时压缩申请人内部列和发票大列宽度，降低用户横向滚动成本。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentOaSummary` 前端类型、`styles.css` OA pending table 规则、`OaPendingPaymentsPage.test.tsx` 和本模块测试矩阵；后端 rows 已输出 `oa.reason` 与 `oa.counterpartyName`，API contract 不变。
- 关键决策：不新增前端伪筛选字段；申请事由和对方户名只作为 OA payload 展示，若后端为空则显示 `-`。发票列继续纵向展示但从 20% 收窄到 13%，支付状态列收窄到 8%，OA 大列扩到 40% 以容纳五个内部字段。
- 文档影响：更新本实施记录、`state-machine.md` 历史变更和 `tests.md` 布局回归口径。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 OA 内部五列 DOM、申请事由/对方户名内容、压缩字号、发票列/支付状态列宽和 OA grid CSS contract；Browser e2e 继续覆盖真实 Chromium 无横向滚动。
- 验证命令：本轮最终说明列出完整命令。

## 当前决策

- OA 待付款列表以 OA application 为主行；银行流水、进项发票和 relation 只是付款证据或详情证据。
- completed 视图以 Workbench active relation 作为 OA/支出流水/进项发票关联关系事实源；in-progress 视图以 OA 待付款独立 pending relation 作为 OA/支出流水关系事实源。多 OA、流水或发票在同一 relation 中必须聚合成一条核对行，并通过 `relationCount`/`summaries` 展开详情。
- `paymentStatus` 由 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` 判定，前端不得按金额字段自行推断。
- `paymentStatus` 只输出 `paid` / `unpaid`；active linked 付款关系即判定 `paid`，金额差额、缺失银行事实或非支出流水只保留 reason/金额字段并继续阻断写回。
- `/oa-pending-payments` 通过 `view_mode=completed|in_progress` 承载同一页面的两类 OA：completed 是原待付款核对，in_progress 只展示 OA 系统仍进行中的支付申请/日常报销。
- OA 待付款核对的 OA 范围以 OA MySQL `t_payment_simple.flow_id` 为准。页面/read model 先用该字段匹配 OA Mongo `form_data._id`，再按 OA 当前 workflow status 分配到 completed/in-progress；未进入 `t_payment_simple` 的重复/异常 OA 不进入正常表格。
- `t_payment_simple.id` 不是 OA ID，只能作为支付状态记录诊断字段；支付状态展示、tab 统计和写回闭环都必须围绕同一 `flow_id`。
- 页面切换按钮数量来自 rows `summary.viewCounts.completed/in_progress`，统计口径与当前搜索/筛选条件一致，并且使用同一批 `t_payment_simple.flow_id` 准入后的 OA。
- completed 与 in_progress 视图展示同一套 OA、支付状态、支出流水和进项发票证据四分组表格；没有发票证据时发票列显示 `-`。
- OA/支付状态/支出流水/发票是表格主体的固定四段：OA 单元格内按“申请人 / 项目 / 申请事由 / 对方户名 / 金额”五栏展示，支出流水单元格内按“对方户名 / 金额 / 摘要”三栏展示；支付状态列保持窄列，只展示付款状态和“未写回/已写回”；发票列纵向展示发票号、发票方、日期 chip 和金额，不显示“价税合计”chip。表格优先避免横向滚动，必要时通过紧凑字号、紧凑 chip、换行和行高增长承载信息。
- 进行中 OA 的候选流水不能写回；页面级自动匹配只接受关联台 OA-bank 精确金额/精确合计规则确认的无冲突匹配。已有 completed Workbench active relation、in-progress active pending relation 或自动确认 pending relation 通过 workflow/outflow/金额/flow_id 校验后，自动写回 OA MySQL `t_payment_simple.pay_status=1`。
- 进行中 OA 自动匹配、`link-bank-transactions` 和规则保存成功后，页面必须先等待 `oa_pending_payment` operation barrier fresh，再重新读取 rows；barrier blocked/timeout 只能提示后台同步尚未完成，不能提前读旧投影或把已提交写入显示成操作失败。
- OA MySQL `t_payment_simple.flow_id` 使用 OA Mongo `form_data._id`。该结论来自 2026-06-17 服务器实机脱敏验证：现有 `t_payment_simple.flow_id` 为 24 位 ObjectId 形态，能匹配 Mongo `_id`，未匹配 Flowable `PROC_INST_ID_`；流程实例 ID 和流程请求 ID 只作为详情/诊断信息，不作为最终写回 ID。
- 生产 rows、filter-options 和 detail 必须走 `OaPendingPaymentReadModelService` 的 freshness/source-version gate；非 fresh 返回 refreshing/unavailable 并入队 `oa_pending_payment.read_model.refresh`，不能 live scan。
- `invoice-usage-collection` worker 同时负责 `input_invoice_usage`、`output_invoice_collection` 和 `oa_pending_payment` read model；OA all scope 只 fan-out month shards，不同步重建全量历史。
- `invoice-usage-collection` refresh handler 必须在 rebuild/fan-out 前校验 event source_version 是否仍为当前 dirty scope；旧事件只能返回 `skipped/stale_source_version`，不能覆盖较新的 read model。
- OA pending `all` scope 的 source version 判定优先从 `read_model.oa_pending_payment_rows` 的实际行聚合；只有完全没有实际行时才退回 scope 表，避免历史空月份 scope 把默认视图误判为 stale。
- 2026-06-17 生产已通过 release `main-e8de2711-20260617182353` 更新/重启服务器 `invoice-usage-collection` worker；后续不得只用本地手工 rebuild 代替标准 release/worker helper。
- 生产 OA MySQL 支付状态写回必须显式配置 `FIN_OPS_OA_PAYMENT_STATUS_*`。2026-06-17 已创建最小权限 MySQL 账号 `finops_oa_payment_status` 并写入 root-only 生产 env；该账号仅有 `smart_oa.t_payment_simple` 的 `SELECT`、`INSERT(flow_id, pay_status)`、`UPDATE(pay_status)` 权限。
- pending invoice rules 不参与 OA 待付款判定，`pending_invoice_rules_changed` 不投递 `oa_pending_payment_read_model`；OA freshness 只由本模块 boundary 声明的 source vector 与 writer fan-out 驱动，不得恢复 workbench invalidation 的隐藏副作用。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-24 - Local read model implementation closure audit

- 目标：执行 `read-models:oa-pending-payment-local-implementation-closure-audit`，核对 repository port、fresh gate、source-version proof、scope policy、worker fan-out、operation barrier、legacy contamination 和测试/文档是否已本地闭合。
- 影响范围：移除 `Application` 上已无运行时调用者的 OA pending payment app-level rebuild/list/mark/live helper；真实 worker 路径继续使用 `InvoiceUsageCollectionReadModelRefreshService`、`InvoiceUsageCollectionSqlProjectionBuilder` 和 `OaPendingPaymentReadModelRepositoryPort`。
- 关键决策：旧 `Application.rebuild_oa_pending_payment_read_model_scope(...)` 路径会 live scan 后直接写 read model，属于可删除旧链路；删除后 OA pending payment 的本地 read model 实现支持已可进入 `production-evidence-deferred`，但模块不声明全局 closed。
- 文档影响：新增 modular IO analysis，更新 read-models/OA pending payments 实施记录、测试矩阵、state machine、autonomous queue/state/next prompt；状态定义不变。
- 测试覆盖：`tests/test_oa_pending_payment_api.py` 中原 legacy 行为测试改为防回归 guard，证明旧 `Application` helper 不能返回；OA API fresh gate 和 invoice usage collection projection/worker 回归继续覆盖真实路径。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-local-implementation-closure-audit.md`。
- 未测风险：无 local `PGSQL_URL`/staging DB；真实 PostgreSQL dirty/outbox/readiness、`invoice-usage-collection` worker drain、App Status、high-row API 和 authenticated browser smoke 仍记录为 production evidence deferred。

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐 OA 待付款核对页的本地 `NETWORK-RECOVERY` 负面链路，防止 rows 首屏暂时失败时显示普通空态或用户无法从页面恢复。
- 影响范围：`OaPendingPaymentsPage` 显式刷新入口和错误/刷新状态、`OaPendingPaymentsTable` 错误态空行文案、Playwright deterministic mock、`web/e2e/oa-pending-payments-flow.spec.ts`、`OaPendingPaymentsPage.test.tsx` 和测试闭环文档。
- 关键决策：不改后端业务语义或真实 API contract；mock 表达 `/api/oa-pending-payments/rows` 暂时 503，页面必须显示错误提示和错误态空行，不显示普通空态，并允许用户点击显式刷新恢复 fresh rows/pagination。
- 文档影响：更新本文件、`e2e-coverage.md`、`tests.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-flow.spec.ts::recovers rows after a transient load failure when refreshed`；扩展 `web/src/test/OaPendingPaymentsPage.test.tsx` 验证刷新入口会重新请求 rows。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts --project=chromium`；本轮最终说明列出额外 Vitest/类型/docs 验证。
- 未测风险：本地 deterministic Browser 不证明真实 OA Mongo/MySQL、PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实网络中断、生产大数据和真实用户 confirm-paid/link-bank 写流恢复。
- 后续事项：继续补其它页面或 mutation 级网络恢复；真实 rows/detail non-fresh 恢复和 confirm-paid/link-bank worker drain 仍走 staging/runtime gate。

## 2026-06-19 - OA pending rows/detail non-fresh Browser E2E

- 目标：补齐 `OA-PENDING-E2E-008`，让真实 Chromium 覆盖 rows/detail read model 非 fresh 时的页面诊断，避免把 refreshing 空 rows 当成真实空态。
- 影响范围：`OaPendingPaymentsPage`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块状态机/coverage/tests 和全局 Spec-first E2E 文档。
- 关键决策：这是 Spec-first 产品行为修复。rows/filter-options 返回 `read_model_status=refreshing` 或 202 且 rows 为空时，页面显示中性“OA 待付款核对数据正在刷新”，不展示真实空态，也不向业务用户暴露 stale reason；detail 202 继续通过 drawer 展示“详情暂不可用”。
- 文档影响：更新 `state-machine.md`、`e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` 两条 Browser 测试；更新组件测试覆盖 rows refreshing 诊断和 detail unavailable。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npx playwright test e2e/oa-pending-payments-nonfresh-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 worker 停止/恢复、source-version stale 到 fresh 的恢复链路仍需要 staging/生产 smoke。
- 后续事项：补真实基础设施 confirm-paid/link-bank/rows-detail worker drain smoke，以及真实生产大数据、网络恢复和视觉遮挡 smoke。

## 2026-06-19 - 进行中 OA bank-link Browser E2E

- 目标：补齐 `OA-PENDING-E2E-007`，让真实 Chromium 覆盖进行中 OA 勾选后打开“关联支出流水”抽屉、筛选/禁选/提交和刷新闭环。
- 影响范围：`web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：只加固 Browser E2E 和 deterministic mock，不改产品逻辑；link-bank 成功流只模拟 Workbench relation/read model 更新，断言页面仍 `未写回` 且 `confirm-paid` 零调用，避免把抽屉关联误当成 OA MySQL 支付状态写回。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-bank-link-flow.spec.ts` 两条 Browser 测试，覆盖抽屉默认全部、已配对/已关联禁选、relation_status 筛选、提交 body、rows/read model refresh、失败错误可见、零半写和不调用 confirm-paid。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-bank-link-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 Workbench active relation 和 OA pending read model fan-out 仍需要 staging/生产样本 smoke。
- 后续事项：补 `OA-PENDING-E2E-008` rows/detail non-fresh Browser 诊断，以及真实基础设施 confirm-paid/link-bank worker drain smoke。

## 2026-06-19 - 进行中 OA confirm-paid Browser E2E

- 目标：补齐 `OA-PENDING-E2E-006`，让真实 Chromium 覆盖进行中 OA 用户点击“确认已支付并写回”的成功刷新、重复提交防护和失败零半写。
- 影响范围：`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：只加固 Browser E2E 和 deterministic mock，不改产品逻辑；mock 成功流模拟 confirm-paid 返回 `readModelRefresh` 后 rows/read model 重新请求并显示 `已写回`，失败流模拟后端 409 并断言页面保留 `未写回`、不触发 rows refresh。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` 两条 Browser 测试，覆盖成功写回、防重复提交、POST body、read model refresh、失败错误可见和零半写。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-confirm-paid-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 confirm-paid 写回仍需要 staging/生产样本 smoke。
- 后续事项：补 `OA-PENDING-E2E-007` 进行中 OA 关联支出流水 Browser 流、`OA-PENDING-E2E-008` rows/detail non-fresh Browser 诊断，以及真实基础设施 confirm-paid worker drain smoke。

## 2026-06-19 - Spec-first OA pending linked fan-out Browser E2E

- 目标：补齐 Workbench confirm 后 OA 待付款页面必须通过 read model 重新读取并从候选/少付状态更新为 linked/已支付状态的 Browser 保护。
- 影响范围：`web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：新增 opt-in deterministic mock `oaPendingPaymentRelationFanout`，不影响既有 OA 页面 smoke；Browser flow 先进入 OA 待付款确认候选状态，再通过 Workbench confirm，回到 OA 待付款断言 rows 重新请求、状态变为 `已支付`、候选标记消失并显示 `关联台已确认`。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 README、tests 和本实施记录，并同步全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/workbench-relations-oa-pending-fanout.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；进行中 OA 确认写回和关联支出流水仍缺完整 Browser 流。
- 后续事项：补进行中 OA confirm-paid Browser 流、link-bank-transactions Browser 流和 rows/detail non-fresh 浏览器诊断。

## 2026-06-18 - OA 待付款准入源改为 t_payment_simple.flow_id

- 目标：把 OA 待付款核对的 OA 范围从“扫 OA 系统所有进行中/已完成 OA”调整为“以 `t_payment_simple.flow_id` 为支付状态管理准入表”，避免网络波动导致的重复 OA 污染付款核对页面。
- 影响范围：`OaPendingPaymentQueryService` live query、OA payment status repository、Postgres OA pending read model rows summary、前端视图切换按钮、模块/产品/API/页面架构文档和相关测试。
- 关键决策：`flow_id` 必须匹配 OA Mongo `form_data._id`；查到 OA 后按当前 workflow status 进入 completed/in-progress。`t_payment_simple.id` 不是 OA ID；写回时更新同一 `flow_id` 的 `pay_status=1`。查不到 OA 的 `flow_id` 不进入正常表格，后续可作为异常计数/诊断扩展。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py` 和 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 latest flow_id 列表、准入过滤、`summary.viewCounts` 和 tab 数量展示。
- 未测风险：本地自动化没有连接真实 OA Mongo/生产 MySQL 同步链路；生产中 `t_payment_simple.flow_id` 找不到 OA Mongo `_id` 的记录需要后续异常列表或运维报表承接。

## 2026-06-18 - 拆分 completed OA projection 与 OA 待付款准入 projection

- 目标：落实长期设计，避免 `app.oa_applications` 同时承担“普通已完成 OA 投影”和“OA 待付款支付准入 OA 投影”两个语义。
- 影响范围：`PaymentAdmittedOAProjectionAdapter`、Postgres OA projection repository、`OAProjectionSyncService`、`InvoiceUsageCollectionSqlProjectionBuilder`、`InvoiceLifecycleSqlProjectionBuilder`、API server/worker 装配、workbench SQL projection、workbench relation projection/repository、模块/产品/API 文档和相关测试。
- 关键决策：普通 `app.oa_applications` 只写入/读取 completed 或历史未知 workflow status，`oa.sync` 扫到 in-progress 时仍入队 `oa_pending_payment` refresh，但不再把 in-progress 写入普通 projection，并会清理旧 in-progress 残留。OA 待付款 read model 使用专用 `PaymentAdmittedOAProjectionAdapter`，先读取 `t_payment_simple.flow_id`，再生成 `oa-pay-/oa-exp-` row_id 候选向 OA Mongo 精确读取当前 OA。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_invoice_usage_collection_sql_runtime.py` 和 `tests/test_invoice_lifecycle_page_integration.py`，并跑 workbench relation、worker registry、migration、runtime boundary 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards tests.test_workbench_relation_repository tests.test_workbench_relation_sql_projection tests.test_invoice_lifecycle_page_integration -v`。
- 未测风险：本地未连接真实 OA Mongo/生产 MySQL 做 read model rebuild smoke；部署后仍需触发 `oa.sync:all` 和 `oa_pending_payment:all`，确认普通 projection 中 in-progress 被清理，OA 待付款进行中数量来自 `t_payment_simple.flow_id` 准入后的专用投影。

## 2026-06-18 - completed/in-progress 统一四分组表格 UI

- 目标：按最新 UI 要求，让“已完成 OA / 进行中 OA”使用同一个表格 UI：第一行大分组固定为 OA、支付状态、流水、发票；第二行保留各分组筛选/排序入口；发票列纵向展示发票号、发票方、日期 chip 和金额。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentsPage` 调用、表格 CSS、`OaPendingPaymentsPage.test.tsx`、本模块 README/state-machine/tests/implementation-notes；后端 API、read model、付款判定和写回流程不变。
- 关键决策：`view_mode` 只控制数据范围，不控制表格列结构。进行中 OA 缺少发票证据时发票列显示 `-`；发票方改为普通文本，不使用 chip；移除“价税合计”chip。
- 文档影响：更新本实施记录、README、state-machine 和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖统一发票列、发票筛选、进行中视图发票空值 `-`、发票方非 chip、移除价税合计 chip。

## 2026-06-18 - OA pending 四分组表格取消横向滚动

- 目标：保证用户不需要左右滑动即可看见 OA、支付状态、流水和发票四组信息。
- 影响范围：表格 CSS、`OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-flow.spec.ts` 和本模块文档；后端数据契约不变。
- 关键决策：取消固定 `1420px` 表格宽度，改为 100% 自适应；列宽按百分比分配，内部 grid 使用 `minmax(0, ...)` 允许文本换行，局部缩小表格字号、chip、详情按钮和确认按钮。
- 文档影响：更新本实施记录和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：Vitest 覆盖紧凑 CSS contract，Playwright 在真实 Chromium 数据行渲染后断言 `scrollWidth <= clientWidth + 1`。

## 2026-06-18 - OA pending 主体三段表格内部布局调整

- 目标：按最新 UI 要求调整 OA 待付款核对的 completed/in-progress 表格主体，让 OA 区域内部固定展示申请人、项目、金额三栏；流水区域内部固定展示对方户名、金额、摘要三栏；支付状态列收窄并只展示“未支付/已支付”“确认已支付”和“未写回/已写回”。
- 影响范围：`OaPendingPaymentsTable`、表格 CSS、`OaPendingPaymentsPage.test.tsx` 和本模块测试/实施文档；后端 API、read model、付款判定和写回流程不变。
- 关键决策：保持 HTML 主表格仍以 OA、支付状态、流水为主体；completed 视图按既有状态机继续保留发票情况列，in-progress 视图继续隐藏发票列。写回状态不展示失败标签，外部依赖不可用仍只展示同步状态异常。
- 文档影响：更新本实施记录和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 OA/流水内部三栏结构、流程状态 chip 文案、支付状态列宽、写回状态文案和缺流水 `-` 展示。

## 2026-06-18 - 修复进行中 OA 投影后页面不刷新的链路

- 目标：修复生产“OA 待付款核对 / 进行中 OA”为空。排查确认 Mongo 中 2026 年后存在进行中支付申请/日常报销，Postgres OA projection 与 `read_model.oa_pending_payment_rows` 中没有 `in_progress` 行；直接原因是生产未用当前 projection 逻辑重跑，且 `oa.sync` 完成后没有把 `oa_pending_payment` read model 标脏。
- 影响范围：`OAProjectionSyncService`、生产 `oa.sync` / `oa_pending_payment.read_model.refresh` worker drain、本模块测试文档。
- 关键决策：OA projection sync 仍是统一事实源；页面不 live scan Mongo。`oa.sync` 完成后必须同时 fan-out `workbench`、`search`、`pending_invoice` 和 `oa_pending_payment`，让进行中 OA 通过 worker/read model 进入页面。
- 测试覆盖：新增 `tests/test_oa_projection_sync_service.py`，锁定 `in_progress` OA 同步后会入队 `oa_pending_payment` 月份和 `all` refresh。
- 生产修复动作：部署后触发一次 `oa.sync:all`，确认 `app.oa_applications.workflow_status='in_progress'` 和 `read_model.oa_pending_payment_rows.oa_workflow_status='in_progress'` 均有数据。

## 2026-06-18 - OA pending completed 视图恢复发票证据列

- 目标：修复 Playwright smoke 暴露的回归：`oa-pending-payments` rows payload 已返回 `invoice.digitalInvoiceNo`，但表格只渲染 OA/支付状态/流水三列，导致真实浏览器首屏看不到发票号，也无法打开发票详情。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentsPage`、表格 CSS、`OaPendingPaymentsPage.test.tsx`、本模块测试/实施文档；后端 API contract 不变。
- 关键决策：按当时状态机保留 view-mode 区分。`completed` 视图显示发票情况列，支持单发票详情和多发票 relation 明细；`in_progress` 视图当时继续隐藏发票列。该展示口径已被 2026-06-18 “completed/in-progress 统一四分组表格 UI”替代。
- 文档影响：更新本实施记录和 `tests.md`；状态机既有“completed 视图保留 invoice detail 能力、in_progress 不展示发票列”的口径不变。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 completed 发票列/发票筛选/开票日期排序/单发票详情/多发票 relation 明细，并保留当时的 in-progress 隐藏发票列断言；`web/e2e/oa-pending-payments-flow.spec.ts` 重新通过。该断言已在后续统一四分组 UI 中改为发票列空值 `-` 断言。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm run e2e:smoke`。
- 未测风险：未做真实大数据横向滚动截图；新增列宽由 deterministic browser smoke 和 Vitest 覆盖基本可读性，真实生产宽表仍需 staging/人工抽样。

## 2026-06-17 - OA 支付状态 MySQL 写回生产配置闭环

- 目标：解除 Phase 08 最后一项生产 blocker，使“进行中 OA 确认已支付”具备可用的 OA MySQL 写回路径。
- 影响范围：生产 MySQL `smart_oa.t_payment_simple` 最小权限账号、`/etc/fin-ops/fin-ops.secrets.env`、fin-ops API/worker/dispatcher 重启、`oa_pending_payment` read model refresh。
- 关键决策：不重置 MySQL root；通过一次 MySQL init-file 重启创建 `finops_oa_payment_status` 的 `127.0.0.1` 和 `localhost` host entry；临时 init-file/drop-in 创建后立即删除；验证写权限使用事务 rollback，不落业务 probe 行。
- 文档影响：更新本实施记录；`deploy/oa/README.md` 保留后续运维 runbook。
- 测试覆盖：生产侧验证 `MySQLOAPaymentStatusRepository.from_environment()` 可实例化并读取 sentinel flow_id；MySQL 最小权限账号对 `t_payment_simple` 的读、插入、更新通过 rollback smoke；`MySQLOAPaymentStatusRepository.mark_paid()` 真实 SQL 路径通过 rollback-on-commit smoke；重启后 `oa_pending_payment:all` durable refresh 由生产 worker 消费。
- 验证命令：root SSH 生产脚本创建账号并执行 PyMySQL rollback smoke；`sudo -n /usr/local/sbin/finops-deploy-control restart`；生产 env repository smoke；`/fin-ops-api/health/ready`；投递 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：`finops_oa_payment_status@127.0.0.1` 与 `finops_oa_payment_status@localhost` 均可读取 `smart_oa.t_payment_simple`，事务内 insert/update 后 rollback 剩余 probe 行数为 `0`；`SHOW GRANTS FOR CURRENT_USER()` 显示 `USAGE` 以及 `SELECT, INSERT(flow_id, pay_status), UPDATE(pay_status)` on `smart_oa.t_payment_simple`。生产 env 七个 `FIN_OPS_OA_PAYMENT_STATUS_*` key 均存在，repository configured/read_ok；`mark_paid()` rollback-on-commit smoke 返回 `pay_status=1` 且 probe 剩余行数为 `0`。
- Worker 证据：重启后 source_version `123` 的 `oa_pending_payment.read_model.refresh` event `a8a7eee2-04ff-4033-8f07-7276f0c1ccd2` 已 `done`，dirty scope `done`，月份 shard 更新在 `2026-06-17 18:44:56` 至 `18:44:58`，`invoice-usage-collection` heartbeat current。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `210`。当前仍没有可执行真实 confirm-paid 的进行中 OA 行，因此没有改动真实业务支付状态；写回能力通过生产权限和 rollback smoke 验证。
- 未测风险：真实用户点击 confirm-paid 需要未来出现一条真实进行中 OA + 支出流水候选/关系时再做业务级 smoke；当前生产事实数据没有 in-progress 行可用于不造数验证。
- 后续事项：当出现真实进行中 OA 样本时，执行一次确认已支付，核对 `t_payment_simple.flow_id=<OA Mongo form_data._id>` 最新记录 `pay_status=1`，并核对页面 `oaPaymentWriteback.label=已写回`。

## 2026-06-22 - 全部月份自动匹配接口 500 修复

- 目标：修复 OA 待付款核对页月份为空（全部月份）时，页面级 `auto-reconcile-bank-transactions` 报“接口处理失败，请联系管理员查看后端日志”的生产故障。
- 真实原因：生产日志显示后端调用 Workbench 候选匹配服务时传入 `scope_month=all`，而候选匹配服务只接受 `YYYY-MM`；异常为 `ValueError: scope_month must be YYYY-MM for workbench candidate matches.`。页面 rows 已经 fresh 并能展示数据，失败发生在 rows 加载后的自动匹配写命令。
- 影响范围：`OaPendingPaymentCommandService._auto_confirm_in_progress_bank_matches`、自动匹配候选生成、OA-bank relation confirm、OA MySQL 写回和 read model refresh enqueue。
- 关键决策：`month=all` 不再把 `all` 传给候选匹配服务；改为按进行中 OA 自身月份分组，并只用同月未配对支出流水生成候选，避免跨月匹配和 matcher contract 违规。
- 文档影响：更新本实施记录和测试矩阵历史 bug 回归库；业务口径不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_all_months_groups_matches_by_month`，覆盖全部月份下跨月 OA/流水按月分组、分别确认 relation、写回对应 flow id 并入队对应月份 read model refresh。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service -v`；`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py backend/src/fin_ops_platform/services/oa_pending_payment_service.py`。
- 未测风险：本地单测使用 fake repository，不替代真实浏览器携带登录态触发生产 HTTP；生产发布后仍需通过线上日志和页面刷新确认不再出现同一异常。

## 2026-06-17 - Phase 08 生产发布与 worker smoke

- 目标：按 GSD 主控闭环完成 Phase 08 发布后验证，确认进行中 OA 视图的生产 read model/worker/页面数据路径不是只在本地可用。
- 影响范围：生产 release、PostgreSQL durable queue、`invoice-usage-collection` worker、`oa_pending_payment` read model、公开前端入口和 OA MySQL 写回配置核验。
- 关键决策：生产 smoke 使用 `ReadModelRefreshGateway` 入队 `oa_pending_payment:all`，等待已部署 worker 消费；不通过手工 rebuild 伪造 fresh。支付状态 MySQL 只做只读连通性核验，不在没有样本 flow_id 时写入。
- 文档影响：更新本实施记录，明确生产 release 已闭合以及 OA MySQL 写回 env/凭据仍未闭合。
- 测试覆盖：沿用 Phase 08 后端 service/API/read model、migration/boundary、前端 Vitest 和 docs/build 验证；生产侧补 durable queue smoke 和 repository 同源读取。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`bash scripts/verify.sh docs`；`cd web && npm run build`；`./scripts/deploy-oa.sh --dry-run`；`./scripts/deploy-oa.sh`；生产入队 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：生产 release metadata 为 `main-e8de2711-20260617182353` / commit `e8de27118e15403ff0b256a6c40ab82b13a69932`；`/fin-ops-api/health/ready.status=ready`，runtime release consistent；deploy-control 显示 API、dispatcher 和 `fin-ops-worker@invoice-usage-collection.service` active。post-deploy event `cade4a8b-d7e3-40f8-a704-9b591803dbf0` source_version `122` 已 `done`，all scope fan-out 到 `2026-06` 至 `2025-12` month shards，最近生产 rows 更新在 `2026-06-17 18:27:19` 至 `18:27:21`。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `211`。当前进行中视图空表是 OA 投影事实数据，不是页面未加载。
- 未测风险：当时未能完成生产 OA MySQL 写回配置验证；文件层已确认目标表在 MySQL datadir 的 `smart_oa/t_payment_simple.ibd`，但缺少可用 MySQL 管理凭据。该 blocker 已由后续“OA 支付状态 MySQL 写回生产配置闭环”记录解除。
- 后续事项：已由后续记录补齐最小权限账号、生产 env、只读 repository smoke 和 rollback 写权限 smoke；真实业务级 confirm-paid smoke 仍需等待生产出现进行中 OA 样本。

## 2026-07-06 - payment status 单次 refresh 复用

- 触发事实：生产 `read_model_slo_smoke --apply --critical-only --target-ms 1000` 中 `oa_pending_payment:2026-06` 首次采样 handler `2849.815ms`、enqueue-to-fresh `2873.731ms` 超过目标；随后远端 breakdown 的完整 rebuild 约 `905ms`，其中 `payment_statuses_by_flow_id` 与 in-progress OA admission projection 存在同一 refresh 内重复读取 payment status 的风险。
- 决策：`PaymentAdmittedOAProjectionAdapter` 增加可选 `payment_statuses_provider`；`InvoiceUsageCollectionSqlProjectionBuilder.rebuild_oa_pending_payment_read_model_scope(...)` 先批量读取一次 payment statuses，再让 in-progress projection 复用同一 map。默认 adapter 行为不变，只有 builder 明确传入 provider 时才减少重复 MySQL 读取。
- 测试覆盖：新增 `tests/test_oa_payment_status_service.py::OAPaymentStatusServiceTests::test_payment_admitted_projection_can_reuse_payment_statuses_provider`，防止 provider cache 可用时再次调用 repository list。
- 未测风险：真实生产 1s SLO 需发布后重跑；该修复不改变 OA admission、写回状态、关系清理或页面 API shape。

## 2026-06-17 - OA pending read model runtime freshness 闭环

- 目标：修复 Phase 08 runtime smoke 中发现的默认 `all` 视图持续 `refreshing`、手工 v3 rebuild 后又被旧刷新路径写回 v1/空 workflow status 的问题。
- 影响范围：`InvoiceUsageCollectionReadModelRefreshService`、`PostgresReadModelRepository.list_oa_pending_payment_rows`、当时仍存在的 `Application.rebuild_oa_pending_payment_read_model_scope` 兼容路径、SQL runtime 测试、生产发布/worker 运维；该 app-level 兼容路径已在 2026-06-24 local closure audit 中删除，当前 rebuild owner 是 `InvoiceUsageCollectionSqlProjectionBuilder`。
- 关键决策：刷新事件处理前复用 durable queue 的 `read_model_refresh_is_current` guard；stale event 不 rebuild、不 complete dirty scope；OA pending `all` freshness 优先从实际 rows 的 `source_versions` 聚合，历史空 scope 不参与有行视图的新鲜度证明。
- 文档影响：更新本模块 implementation-notes、tests、state-machine；生产发布仍按 `scripts/deploy-oa.sh`，不能手工绕过 release/worker helper。
- 测试覆盖：新增/更新 `tests/test_invoice_usage_collection_sql_runtime.py::test_oa_refresh_handler_skips_stale_source_version_before_rebuild`、`test_oa_repository_all_scope_aggregates_monthly_scope_source_versions`，以及当时的 `tests/test_oa_pending_payment_api.py::test_legacy_application_rebuild_includes_completed_and_in_progress_rows`；该 legacy 行为测试已在 2026-06-24 改为 removed-helper guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`cd web && npm run build`；本地 Playwright 打开 `/oa-pending-payments` 并切换“进行中 OA”。
- 运行时证据：当前源码 rebuild 后 7 个活跃月份 scope 均写入 `oa-pending-payment:v3` / `2026-06-17-workflow-status-v1`；HTTP smoke 显示 `view_mode=in_progress` fresh 且 total=0、`view_mode=completed` fresh 且 total=210。当前 OA projection 没有 `in_progress` 行，因此页面空表是事实数据，不是未加载。
- 未测风险：生产服务器 heartbeat 显示 `invoice-usage-collection` worker 仍在运行旧部署；未完成 release activate 前，服务器 worker 可能继续用旧逻辑覆盖 read model。由于当前工作树包含未提交 Phase 08 改动，`scripts/deploy-oa.sh` 标准发布会拒绝 dirty worktree，必须先提交/发布/重启 worker 后再做生产 smoke。
- 后续事项：完成干净 release 发布后，重跑 `oa_pending_payment:all` refresh，确认 worker heartbeat 更新时间、scope source versions、HTTP rows/filter-options 和页面空态/数据态一致。

## 2026-06-17 - 进行中 OA 支付确认与 OA 写回

- 目标：在 OA 待付款核对页新增 `已完成 OA / 进行中 OA` 切换，把进行中支付申请/日常报销拉入三列视图，并支持候选流水确认后写回 OA 支付状态。
- 影响范围：OA Mongo adapter/projection、OA pending payment query/read model/service/API、OA MySQL payment status adapter、Workbench relation confirm command、`OaPendingPaymentsPage`/table/API types/styles、模块/产品/API 文档和相关测试。
- 关键决策：继续复用 Workbench relation 作为关联事实源；历史 candidate relation 术语只表示当时未正式确认的自动匹配证据，当前口径下必须按未关联/未正式化 decision 处理，不直接判定 `paid` 或写回；confirm-paid 后端负责金额相等、outflow、workflow_status、flow_id 和 relation command 校验，页面只提交用户确认。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py` 和 `web/src/test/OaPendingPaymentsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_mongo_oa_adapter.MongoOAAdapterTests.test_list_application_records_maps_payment_requests_and_reimbursement_details tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_external_oa_mysql_client_is_confined_to_role_sync_adapter tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_raw_postgres_sql_in_services_is_classified_by_platform_boundary -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_command_service tests.test_oa_pending_payment_api -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA MySQL/Mongo，不覆盖真实网络超时、账号权限、生产锁等待、真实 OA 字段变体和 worker drain；需要 staging 用真实进行中 OA、候选流水和 `t_payment_simple` 样本 smoke。
- 后续事项：部署前配置 `FIN_OPS_OA_PAYMENT_STATUS_*` 环境变量并在 staging 验证 `flow_id` 解析命中率、confirm-paid 审计链和 2 秒目标 refresh。

## 2026-06-17 - OA待付款Browser e2e闭环

- 目标：补齐 OA 待付款核对页面真实浏览器层的首屏、筛选/排序和详情抽屉保护，降低只靠 Vitest 时漏掉实际导航、drawer、请求参数编码或规则抽屉复用 endpoint 回归的风险。
- 影响范围：Playwright deterministic API mocks、`web/e2e/oa-pending-payments-flow.spec.ts`、smoke 脚本和 OA 待付款测试文档；后端业务代码和 API 契约不变。
- 关键决策：本轮选择只读高价值链路，覆盖 rows/filter-options、搜索、支付状态筛选、交易时间排序、OA/流水/发票详情和支出流水无需开票规则抽屉；真实 OA/Mongo、真实 Postgres 和 worker drain 仍留给 staging/生产 smoke。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并同步 `docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-flow.spec.ts`，并加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`。
- 未测风险：真实 OA/Mongo 字段变体、真实生产 PostgreSQL 大数据 EXPLAIN/锁等待/长分页、真实 RabbitMQ/Redis/systemd worker drain、虚拟滚动压力、像素级视觉和网络中断恢复仍需 staging/生产 smoke。
- 后续事项：继续按 fan-out 风险补 `no-oa-bank-batches` 等页面的 Browser e2e。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止 OA 待付款核对首屏请求把超大 page size 透传为全量读取。
- 影响范围：`OaPendingPaymentQueryService.list_rows` 的分页 contract、`OaPendingPaymentsPage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/OaPendingPaymentsPage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service.OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和网络中断恢复仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-11 - OA待付款关联台分组关系闭环

- 目标：修复多条 OA/支出流水/进项发票在关联台已清晰配对时，OA 待付款页拆成多行并误显示“支付多了”或“多条OA合并支付”的问题。
- 影响范围：`InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService`、OA pending payment read model detail builder、SQL projection 复用路径、`/api/oa-pending-payments/rows/{row_id}/relation-details`、`OaPendingPaymentsTable`、前端 OA pending payments 类型、模块/API 文档和相关测试。
- 关键决策：关联关系完全来自 Workbench active relation；同一 relation 下的 OA、有效 outflow 支出流水和进项发票分别汇总为一条核对行，列表只显示合计金额和 `+N`，点击 `+N` 分别以 `kind=oa|bank|invoice` 查看明细。
- 文档影响：更新模块状态机、测试矩阵、实施记录、产品口径和 API 合同。
- 测试覆盖：新增/更新 lifecycle policy、query service、API/read model detail、SQL projection runtime 和前端交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_lifecycle_policy tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA/Mongo、生产 Postgres 大数据、真实 RabbitMQ/Redis/systemd worker drain 和真实浏览器截图 smoke。
- 后续事项：如需发布前进一步验证，使用截图中的真实月份在 staging 触发 relation 确认/撤回、`oa_pending_payment` scope refresh 和页面浏览器 smoke。

## 2026-06-11 - OA待付款测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `oa-pending-payments` 模块轮次，确认 OA 单据、支出流水、进项发票、Workbench relation、SQL read model、worker 和前端交互的回归保护。
- 影响范围：`docs/modules/oa-pending-payments/README.md`、`docs/modules/oa-pending-payments/tests.md`、`docs/modules/oa-pending-payments/state-machine.md`、`docs/modules/oa-pending-payments/implementation-notes.md`；未改变业务代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖付款状态、缺失证据、API shape、权限、read model freshness、detail stale/missing、SQL projection/repository、worker fan-out、App Status registry 和前端交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`。
- 未测风险：未连接真实 OA/Mongo，不验证真实 OA sync 字段变体和权限菜单；未在真实生产 Postgres 跑大数据 EXPLAIN/锁等待/长分页；未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain；未做真实浏览器大数据表格和网络中断 smoke。
- 后续事项：下一轮处理 `turnover-ledger`，重点审计手动闭环、extra、relation stale precondition、read model freshness 和前端筛选/抽屉交互。
