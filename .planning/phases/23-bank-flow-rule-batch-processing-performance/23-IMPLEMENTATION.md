# 第 3 项实施结果：流水规则批量处理链路

## 已落地的性能收敛

- 列表从两次全量 read-model rows 读取、Python 分页和摘要，改为 `BankFlowRuleBatchReadModelRepositoryPort.read_page(...)`：SQL 当前页、过滤范围 total、完整 summary filter 聚合和 source-version/readiness proof 均为固定查询数。
- 页面默认 page size 从 200 收窄为 50；API response shape、筛选、分页和 freshness 语义保持不变。
- 详情和选中提交通过 `ImportNormalizationService.list_transactions_by_ids(...)` 一次 bulk 读取 canonical 银行流水，并按输入 ID 稳定排序；生产 PostgreSQL 不再逐成员查询。
- reset 不再逐 relation command，也不再在 HTTP 请求中逐月 `refresh_batches(...)`；它使用一次 `cancel_relations_by_case_ids(...)`、一次原子 mutation persistence，read model 由既有 month-scoped worker 后台 reconcile。
- submit/withdraw/reset command 成功后，前端立即更新本页 committed state并结束前台阻塞；freshness wait/reload 只在后台执行，完整跨页 targets 继续广播给其它页面。

## 一致性与失败闭环

- `save_bank_flow_rule_batch_mutation(...)` 新增显式 `changed_batch_ids` 输入；reset 即使遇到历史 active relation 已缺失，也会原子保存 withdrawn batch，不依赖 relation 反推 batch identity。
- bulk cancel 只加载目标 case IDs、只取消目标 active relations、只写一次 history/save，不触及无关 relation。
- reset 无 submitted candidate 时是 O(1) no-op：零 relation 写、零 batch 写、零同步 rebuild。
- persistence 仍位于现有单事务 state-store 边界；没有新增 UoW、表、cache、queue、worker 或外部依赖。
- reset 从 submitted bucket 切回 unsubmitted 后，后台 reconcile 显式携带目标 bucket/page，避免异步闭包把旧 bucket payload 写入新页面；command 后的抑制自动选择标志跨空列表保留，避免自动触发下一批 detail GET。

## 旧链删除

- bank-flow 使用独立 schema version `2026-07-bank-flow-rule-batch-v1` 和新 ID prefix `bank_flow_rule_batch_`；历史 ID 仍可读、提交和撤回，但新批次不再生成 no-OA ID。
- bank-flow runtime application/refresh wrapper 使用中性 bank rows/source versions/stale reasons I/O；不再直接调用 `no_oa_*` application 方法。
- shared batch core 由显式 relation mode 直接产生正式 bank-flow 领域错误；删除 route `BANK_FLOW_RULE_BATCH_LEGACY_ERROR_CODES`、message fallback 和错误翻译。
- bank-flow display tags、idempotency namespace、history operation、persistence error和 worker application class 均使用正式 bank-flow 合同。
- server/worker 的重复 no-OA/bank-flow source-version provider 合并为中性共享 provider；no-OA legacy 模块保留自身真实入口，不进入 bank-flow 运行链。
- architecture guard 禁止 bank-flow route/application/refresh wrapper/frontend重新出现 `no_oa`、`NO_OA`、`免OA` 或 legacy error map。

## 模块边界

- 页面只读 `bank_flow_rule_batch` read model，写入只通过 bank-flow application service。
- canonical 银行流水只通过 import/core repository 窄读 I/O；本模块不写银行事实。
- canonical relation 只通过 `WorkbenchRelationCommandService`；本模块不直接 SQL 写 relation。
- state store 只原子持久化 changed relation snapshot和 bank-flow batch delta，不同步写 Workbench read model。
- 其它页面只收到既有 canonical relation fan-out/domain event，不读取本页面私有 UI state，也不被当前页 freshness wait 阻塞。

## 生产首轮未达标后的补充实现

- 首轮 release `main-a3a331b5-20260720030257` 的 all 列表 p95 为 `539.327ms`、month 列表 p95 为 `720.336ms`，因此阶段保持 open。
- 生产 runtime 指标证明数据库 p95 约 `80.504ms`，主要余量在 Python presentation/source-version。
- 列表现在每请求只 deep-copy 一次 canonical tag dictionary，并复用 definition index 完成当前页 50 个 batch 与完整 summary categories 的标签展示；旧逐 batch/category 重复 deep-copy 路径已删除。
- 月份 freshness 删除重复 relation scope 预加载；expected-source 读取仍完整保留。
- dependency source-version probe reason 按 relation mode 分离，bank-flow API/worker 不再输出旧 no-OA precheck reason。
- canonical category snapshot SHA-256 增加同合同懒缓存，只在分类或 tag dictionary 真实变化时失效；没有 TTL、Redis、额外表、跨进程 cache 或兼容 fallback。
