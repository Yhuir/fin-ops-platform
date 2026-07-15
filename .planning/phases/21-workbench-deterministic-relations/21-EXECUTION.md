# Phase 21 执行与闭环状态

日期：2026-07-15
状态：v3 生产审计 hotfix 本地全量验证完成；生产保持已验证旧 release，重新 cutover 待远程精确 SHA 门禁

## 已锁定产品合同

- Workbench 只有 `paired` 与 `unpaired` 两种页面关系状态。
- 任意 active 正式关系的全部 canonical members 都进入一个 paired group；历史 case 前缀、人工/历史/系统来源和业务 mode 只可作为审计/动作 metadata，不能改变可见分区。
- 没有 active 正式关系的每个 canonical fact 都必须作为 typed identity singleton unpaired 显示，不能合并、隐藏或形成第三种候选状态。
- 确定性匹配跨月读取 OA、银行流水和发票，支持有界 N:M:K；只有强证据闭合、唯一且无冲突的结果才通过正式 command/UoW 创建或扩展 active relation。弱证据、歧义、冲突和资源中止均零写入。
- 自动候选/decision 不再是业务持久化、API 或 UI 状态；旧 service/store/engine、repair CLI、前端组件和运行时分支已删除。旧表物理存储仅在 Release A 回滚窗口保留，Release B 才删除。

## 模块边界与 I/O

| 边界 | 输入 | 输出 | I/O 责任 |
| --- | --- | --- | --- |
| formal fact repository | scope、source versions、canonical tables、active/history relations | immutable typed fact batch | 唯一 SQL 读取 owner；bulk、bounded |
| pure matcher | immutable fact batch、budget | zero or more deterministic `FormalRelationPlan` | 无 I/O；fail closed |
| matching orchestrator | plan、tenant/actor、UoW dependencies | active relation command result、audit/history/outbox | 不读 HTTP，不写 SQL |
| relation command/UoW | typed members、expected versions、idempotency | atomic relation/history/dirty/outbox | repository 承担持久化 |
| grouping projection | canonical rows、active relations | exact paired/unpaired partition | 无 I/O；不得隐藏 ungrouped rows |
| API/UI | fresh read model DTO | paired/unpaired list/detail/actions | 不推断关系、不恢复候选状态 |

## 已完成的旧链路删除

- 删除 Workbench candidate grouping/match/rules、reconciliation decision engine/models/store/cleanup、special candidate adapters/detectors、repair decision CLI。
- 删除 candidate/decision HTTP/UI 语义、CandidateGroup components/tests 和 candidate Browser flow。
- Release A 不携带 migration 0104；Release B 在零访问和数据安全门通过后，才 forward-drop `read_model.workbench_candidate_matches`、`read_model.workbench_reconciliation_decisions` 与精确旧 app-setting，且不修改 canonical facts 或 active relations。
- runtime guard 禁止旧模块/import/状态术语重新进入 app/service/tool；仅允许 read-boundary 对旧 payload 字段做剥离，避免历史缓存泄漏到新 DTO。

## 本地证据

- `bash scripts/verify.sh all` 后端：4182 passed、33 skipped；skipped 均为未配置外部集成环境的显式门禁。首次远端分支 CI 发现 `tests/test_invoice_lifecycle_sql_projection.py` 使用未声明的 `pytest`，且其中 4 个顶层函数不会被标准 `unittest discover` 收集；已改为 `unittest.TestCase`，本地统一入口实际执行 4/4 通过。`tests/test_import_processing_service.py` 的 3 个顶层函数也已收敛到 `unittest.TestCase`，并新增持久化失败零发布测试，总计 4/4 纳入统一入口。
- `cd web && npm test -- --run`：71 files、835 passed。
- 第二次远端 CI 的 21 个前端失败横跨无共同业务改动的页面，并伴随 `MaxListenersExceededWarning`；固定 Vitest `fileParallelism=false`、`maxWorkers=1` 后，本地两次全量均为 835/835。三个下载 API 测试移除 cross-realm `instanceof Blob`，改为验证非空 bytes 与 XLSX MIME，保持业务合同而不依赖 VM realm。
- 第三次远端 CI 在 GitHub Node 20 上仍有 14 个测试失败；失败 DOM 均停留在明确的 loading/零行首帧，根因是测试等待页面或抽屉容器后立即同步读取异步数据，而不是产品链路失败。测试现等待账户/OA/流水/发票行、详情字段、正式关系行或刷新后的当前 DOM 节点；没有提高全局超时、没有 retry 掩盖、没有放宽业务结果。随后用 Node 20 全量串行扫描补齐同类相邻断言，最终 71 files / 835 tests 一次通过，且本轮无 `MaxListenersExceededWarning`。
- 第四次远端 CI 在异步历史行稳定出现后暴露时间展示依赖 runner 时区：`2026-06-10T10:30:00+08:00` 在 UTC runner 被渲染为 `02:30`。OA 反提已提交历史现显式使用 `Asia/Shanghai` 业务时区；测试先等待已提交发票语义表格，再精确断言 `2026-06-10 10:30`，不会用时间文本兼任加载就绪信号。
- 第五次远程 CI 为 176/177；唯一失败是待找发票文本选择 E2E 用元素 bounding-box 中线做像素拖拽，在 CI 字体/换行布局下落到空白区。测试现对同一可见文本节点执行 Playwright 浏览器文本选择，仍精确断言 `window.getSelection()` 包含“智能工厂设备”；未改产品 UI、未增加 retry、未放宽业务结果。
- 第六次远程 CI 的唯一失败是 ETC 统一批次列表测试等待静态 list 容器后同步读取异步批次行；现以 `etc-batch-unsubmitted-01` 业务行作为 readiness anchor，不改 ETC 业务链路与 I/O。
- 第七次远程 CI 已通过后端、835 前端与 177 浏览器流，最后 docs gate 因 runner 未安装 `rg` 而把命令缺失误报为文档缺失。验证入口现集中选择 `rg` 或 `grep`/`git grep`，并移除未使用的固定 `/tmp` 文件写入。
- 第八次远程 CI 的后端已通过，前端仅有 3 个异步首帧时序失败：成本统计测试把页面标题误当成表格或 refreshing 状态已完成，税金抵扣测试把静态统计卡误当成发票选择行已完成。测试现直接等待对应表格、refreshing 文案和业务复选框，不改产品链路、不加 retry、不放宽业务结果。
- Release A 首次生产激活后，OA sync fan-out 暴露 PostgreSQL OA projection 历史 payload 仍含 `section=open`，新 Workbench core 按两态合同 fail fast。生产已立即回滚到 `etc-import-e5d6e6a4e-20260714-visibility`；hotfix 只在 repository 反序列化 I/O 边界把 legacy `open`/缺失值归一化为 `unpaired`，核心继续拒绝旧状态和未知状态。
- Release A 已通过 PR #2 合并到 main（merge SHA `85ec4c26195bd7d2320b90c6c92ff3529d920d52`），分支与 main 精确 SHA 远程 CI 均成功；故障版本未留作 active release，hotfix 必须再次通过本地全量门禁、分支精确 SHA CI、main 精确 SHA CI 后才能重新激活。
- legacy section hotfix 分支精确 SHA CI 成功后，main 精确 merge SHA CI 暴露两个旧测试边界竞态：OA 待付款测试只等待静态页面容器便同步读取异步业务行；Workbench mock server 对同列多值使用 OR，而正式 repository 与本地 display model 使用 AND。测试现等待 OA 业务按钮，并让 mock 复刻正式 AND 合同；不改生产业务链路。
- `cd web && npm run build`：成功。
- 全量 Chromium 业务流：177 passed，覆盖权限、导入、关联确认/撤回、异常、freshness、跨页 fan-out 与大数据集交互。
- 旧链路 guard、migration contract、formal repository/orchestrator/grouping 定向门禁：292 passed、24 subtests passed。
- 520 fixture：`oa-pay-2169` + `inv_imported_0369` + 发票号 `26532000000716859331` 保留原 active relation，历史 `decision:*` identity 仍显示 paired，不新建关系。
- 13-row fixture：13 个 canonical invoice identities 各自 unpaired singleton，minor units 合计 170949，无隐藏/重复/伪配对。
- lint、docs 和旧链路静态 guard 通过。
- 全量门禁首次运行发现两处历史 E2E 证据锚点仍引用旧候选语义；修正后在 clean commit `a4b9e6276` 从头复跑并全部通过。
- CI 稳定化后的统一门禁曾捕获 file import confirm 先 enqueue Workbench matching、后 `save_import_delta` 的真实 I/O 竞态：后台状态写入可把 durable session 从 `confirmed` 覆盖回 `preview_ready`，独立 worker 也可能在 canonical facts 提交前消费 scope。`ImportProcessingService` 现严格执行 durable delta → tax/read-model invalidation → matching enqueue；持久化失败时下游发布为零。重启集成用例连续 50 次通过，最终 `verify.sh all` 再次零失败。
- main `1f1ec5324bc7dde9987b51f79d4d2a6ebe502841` 首次重新激活并完成受控 rehydrate 后，page Audit 捕获 51 个 ETC summary/detail equality mismatch 和 2 个 override/candidate ownership mismatch；freshness/queue 正常但 integrity 阻断，因此立即回滚并重新 rehydrate `etc-import-e5d6e6a4e-20260714-visibility`。旧 release 恢复 219 active relations、19 active generation scopes、876 relation row ids、1296 group rows、零问题；migration 仍为 0001–0103，0104 未执行。
- v2 hotfix 将 collapsed summary/detail 变换保留在纯 grouping 边界、独立 summary/detail 物化保留在 repository 边界、retired decision decoration 保留在既有 read-model sanitation 边界；projection/all-scope/Redis cache schema 同步升级。未恢复 candidate/decision runtime、第三种状态或 fallback。
- v2 本地门禁：受影响面 660 tests + 33 subtests；`bash scripts/verify.sh all` 为 backend 4190 passed / 33 explicit environment-gated skipped、frontend 71 files / 835 tests、production build、Chromium 177/177；lint、docs、旧链路 guard 和 diff check 均通过。
- v2 已通过 PR #5 合并到 main `a127c58c7d3cdfc8fd0a34216eb9cf1523f30bef`，分支/main 精确 SHA CI 均成功。生产 rehydrate 后 51 个 ETC mismatch 归零，但出现 5 个 override mismatch；release 当场回滚，旧版本重新 rehydrate 后恢复零问题。
- v3 只修复两个已由生产证据确认的边界：active row override 优先于同 row exception projection；未配对 grouping 不得用正式 relation-mode registry 删除合法 override 字段。projection/all-scope/cache schema 升级到 v3，仍不含 0104。
- v3 本地全量门禁：`bash scripts/verify.sh all` 为 backend 4192 passed / 33 explicit environment-gated skipped、frontend 71 files / 835 tests、production build succeeded、Chromium 177/177；lint、docs 与 diff check 均通过。

## 未完成的生产门

- 当前环境未设置 `FIN_OPS_TEST_DATABASE_URL`，因此没有执行真实 disposable PostgreSQL migration/catalog/data-hash 集成；Release A 不包含 schema 变更，Release B 在补齐真实 0001–0104 disposable PostgreSQL 证据前不得发布。
- Release A 已隔离到干净 `codex/workbench-formal-relations-release-a` 分支；0104 保留在独立 Release B 候选提交，不进入 A。
- 当前生产运行已回滚的 `etc-import-e5d6e6a4e-20260714-visibility`，其 Workbench rehydrate/page Audit 已再次恢复通过；v3 targeted 与全量本地门禁均已通过，commit/remote CI/合并/部署仍待执行。
- 本轮两次激活均未执行新 migration 或 canonical/relation 写入；受控 rehydrate 只原子发布 read-model generation。重新 cutover 后仍必须完成 worker drain、page/System Audit、520 与 13 个真实 identities 的恢复证据。

## 生产闭环门

1. 从经过审阅的干净 `codex/*` commit 构建 release；先运行 lint、backend、frontend、build、Chromium 和 disposable PostgreSQL migration gates。
2. 发布前在同一只读 snapshot 记录 canonical OA/invoice/bank counts/hashes、active relation/history hashes、520 relation ID/members 和真实 13 invoice identities/金额。
3. 仅通过 `./scripts/deploy-oa.sh` 发布不含 0104 的 Release A；保留旧表，确认 API/frontend/required workers 都来自同一 release。
4. 通过正式 refresh gateway/queue rehydrate `workbench`、`workbench_relation` 及注册下游，等待 dirty/outbox/dead-letter drained、workers 同 release、read models fresh。
5. 运行对象 identity、Workbench page Audit 和 System Audit；证明 520 paired、13 identities 各自恰好一次 unpaired、`P=R`、`U=C-R`、无 overlap/omission、下游 linked/unlinked 一致，并在稳定窗口证明旧表运行时零访问。
6. 只有 Release A 全部证据通过，才从独立、经过审阅的 Release B 提交发布 migration 0104；先在 disposable PostgreSQL 证明精确 drop 和数据哈希不变，再在生产确认旧 catalog objects 消失、canonical/relation hashes 不变并复跑 freshness/Audit。
7. 只有上述两个发布的证据全部通过，才能把 Phase 21 与用户任务标记为 complete。
