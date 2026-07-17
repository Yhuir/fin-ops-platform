---
phase: 08-oa-pending-payments-improvements
status: local_verified_pending_production_verification
created: 2026-07-17
---

# 08：进行中 OA 准入源与刷新隔离计划

## 结论与冻结决策

三点理解成立：

1. `in-progress` 当前不执行附件证据解析、发票识别或 OCR；只保留原始附件文件元数据。未来 OCR 是独立需求，必须另行定义版本、队列、回填与 Audit。
2. OA 待付款私有事实变化只能刷新 `oa_pending_payment`；不得让其它页面出现功能、性能或 Audit 回归。
3. completed OA 等共享 canonical 事实真实变化时，现有合法 consumers 随 owner fan-out 更新是正确行为，不属于串扰。

Grill-me 复核补充四个不可省略的闭环条件：外部读取必须整批 fail-closed；失败 run 必须可审计；`all` 同步必须识别旧 watermark 中“最后一条 completed 被删除”的月份；变化原因必须拆分后再决定 fan-out，不能从混合 `affected scopes` 猜测。

## 边界与 I/O

唯一外部入口是 `MongoOAAdapter.load_sync_application_batch(scope_key, retention_cutoff_month=...)`：每个启用 form/scope 只读一次；`all` 在任何字段校验或附件解析前排除 retention cutoff 以前的文档，再输出两个不可变视图：

- `projection_records`：遵守通用 OA 导入的 form/status 配置，供共享 completed projection 使用。
- `admission_records`：固定接纳 `completed + in_progress`，供 OA 待付款 admission/payment-status/watermark 使用，不受通用 status filter 污染。

任一 form 查询失败、Mongo 进入 backoff，或目标文档缺少可稳定识别的 status/identity 时，整轮失败且不提交 PostgreSQL。同步 service 记录 failed run，不把部分集合解释为删除。合法 in-progress 草稿允许 amount/applicant/reason 等尚未填写的业务字段为空：仍以稳定 OA identity 进入 admission，金额落为 PostgreSQL `NULL`，不进入 completed projection；completed 文档缺少既有必填业务字段仍 fail-closed。

snapshot repository 只负责同一事务内持久化 canonical facts、watermark 和 OA 私有 refresh，输出两个明确变化集合：

- `oa_pending_payment_changed_scopes`：admission、payment-status 或 completed 页面输入真实变化，只刷新 OA 待付款。
- `completed_projection_changed_scopes`：共享 completed projection 真实新增、修改或删除，由 `OAProjectionSyncService` 交给既有共享 owner fan-out。

repository 禁止直接 enqueue Workbench/shared consumers；sync service 禁止重新合并两个变化集合。

## 实施任务

1. 增加 dual-view source batch；completed 保持现有附件处理，in-progress 绕过附件解析/OCR。
2. 删除 sync service 的 `list_available_months` / `list_application_records` / `list_all_application_records` 旧读取编排，以及无生产调用方的 fingerprint polling 链。
3. 原子 snapshot writer 分别接收 projection/admission records，拆分私有与共享 change causes；覆盖旧 watermark 删除态。
4. 失败运行显式写 `app.oa_sync_runs(status='failed')`；不掩盖原始异常。
5. 增加 adapter、service、repository、真实 PostgreSQL、worker/read-model、API、架构 guard 和跨页面回归证据，并同步长期边界文档。

## 验收门

- 通用 status filter 仅含 completed 时，admission batch 仍包含 in-progress。
- in-progress 合法草稿业务字段未填写时仍进入 admission，空金额原子落为 `NULL`；保留期内 completed 缺必填业务字段仍整轮失败，保留期外历史文档不进入校验、解析或 snapshot。
- in-progress 路径不调用附件 parser/OCR；completed 路径保持调用。
- 部分外部读取失败：零 projection/snapshot/watermark/outbox commit，failed run 可见。
- identical batch：零业务时间戳漂移、零 admission replace、零页面 fan-out。
- admission/status-only 变化：仅 OA pending 精确月份 dirty/outbox；Workbench、成本统计和其它 shared consumers 均无新事件/version 变化。
- completed canonical 真实变化或删除：OA 私有刷新与合法 shared owner fan-out 均存在，月份精确。
- 本地全量测试、真实 PostgreSQL、lint/docs/build/architecture guard 通过后才允许提交部署。
- 生产部署后运行 `oa.sync:all` 与 OA shard drain；验证三页面 Audit、操作后 Audit、OA 进行中数据、性能门槛和 simultaneous 隔离。失败则回滚 release，不恢复旧读取/fallback。
