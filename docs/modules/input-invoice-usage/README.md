# 进项发票使用情况 模块维护入口


- Module key: `input-invoice-usage`
- 类型: 页面模块
- Route: `/input-invoice-usage`
- Page key: `input-invoice-usage`

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/InputInvoiceUsagePage.tsx`
- `web/src/components/inputInvoiceUsage/*`
- `web/src/features/inputInvoiceUsage/api.ts`
- `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`

## 当前边界

关注进项发票使用状态、筛选、导出、OA 反查、以发票反提 OA 和 invoice usage read model。

`以发票反提 OA` 的当前目标是：操作人在 FinOps 中选择目标 OA 申请人与发票，FinOps 后端使用目标 OA 申请人的已配置凭据创建 OA 暂存草稿；OA 提交流程由用户在 OA 系统中手动完成。草稿创建成功后本地 batch 立即进入 `暂存`，用户可以稍后选择 `我已在OA系统提交该草稿 / OA正在进行中` 或 `OA提交内容需修改 / 删除本次提交内容`；FinOps 只记录本地确认后的已提交历史。

OA reverse batch 只记录本地流程状态；OA/发票 relation 事实必须通过 `WorkbenchRelationCommandService` 写入 `input_invoice_oa_reverse` 并由 `workbench_relation` read model 分发给相关页面。

进项发票使用情况的列表和关系详情是读路径：关系证据来自 `WorkbenchRelationReadFacade` / `DistributedInvoiceRelationContext`，不直接调用 `WorkbenchRelationCommandService`。关联台未配对区 open/proposed 候选也必须通过同一个 facade 进入本页展示，不能由本页直接读取关联台候选表或自行拼候选。

如果正式进项发票由 OA 附件发票提升或合并而来，列表关系查询必须同时使用发票自身 id 和 `source_links[].source_workbench_row_id` 中的 OA 附件发票 row id 查询统一 relation distribution。这样截图类“正式发票 id 与 OA 附件 row id 不同”的行仍能显示 OA/流水证据，但证据仍来自 `WorkbenchRelationReadFacade`，不能改为本页私有匹配。

关联台页面上的当前选中行、同屏排列或候选高亮不是关系事实。进项发票使用情况只能消费 `workbench_relation` distribution 中已持久化的 `linked` / `candidate` relation；如果某张正式发票在 distribution 中是 `unlinked`，本页必须继续显示未关联，不能用金额相同、销方相似、筛选选中态或关联台视觉行位置推断 OA/流水关系。

`以发票反提 OA` drawer 必须区分 OA 关系三态：`linked` 展示 `已关联oa`、不可勾选；`candidate` 展示 `候选oa`、不可勾选，提示用户先回关联台确认或处理候选；`unlinked` 展示 `未关联oa` 并允许进入创建 OA 草稿 payload。

同一 linked 或 candidate relation 中存在多条 OA、银行流水或进项发票时，rows DTO 必须聚合为一条使用情况行，金额展示各自合计，并用 `relationCount`、`detailMode=list`、`summaries` 和 `invoiceRelations` 支持前端显示 `+N` 后打开关系明细。`relationStatus='candidate'` 只能作为候选证据展示；支付状态、已支付判断和已确认关系判断只能使用 `relationStatus='linked'` 的关系。

`/api/input-invoice-usage/rows/{row_id}/relation-details` 在 SQL read model 可用时必须按 `row_id` 读取单行 payload 并展开已有 summaries，不能为了打开 `+N` 详情触发全量 live rebuild；read model missing/stale/source mismatch 时返回 refreshing 状态并入队刷新。

生产 PostgreSQL runtime 下，`/api/input-invoice-usage/rows` 和 filter/export 相关 all-rows helper 必须依赖 SQL read model repository。repository 缺失、SQL view miss、schema/source version mismatch 或 refresh_status 非 fresh 时都返回 `202`/`read_model_status=refreshing` 并 enqueue `input_invoice_usage` 对应 month/all scope；不得回退 `InputInvoiceUsageQueryService.list_rows(...)` 进行 live scan 或返回 `live_query`。legacy/local 模式保留 query service 作为开发兼容路径。

`input_invoice_usage:all` 在 refresh 链路中是 fan-out 到月份 shard 的控制 scope；页面默认 all 查询的 freshness 证明来自实际 rows/month scopes 和 active dirty/outbox 状态。month scope 必须继续严格比对对应月份 `workbench_relation` source versions；all 查询不能直接使用全局 `workbench_relation:all` source versions 作为 expected contract，否则会把已 fresh 的月份 shard 误判为 stale 并反复显示“正在刷新”。

`input_invoice_usage:all` fan-out 发现当前月份 shard 后，必须清理不再属于当前进项发票事实集的旧月份 rows/scopes。否则旧 month scope 的基础 source versions 会继续参与 all 查询 freshness 聚合，导致 `oa_projection_sync_version_missing` 等 stale reason 反复出现，页面长期显示“正在刷新”。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `oa-reverse-design.md`：维护以发票反提 OA 的目标流程、权限、凭据、安全边界和 API/服务设计。
- `oa-reverse-implementation-plan.md`：维护以发票反提 OA 闭环的分阶段实现计划和阶段 prompt。
- `payment-status-rules-ui-spec.md`：维护“发票与支付状态规则设置”右侧抽屉的小范围 UI 合同。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 Spec-first Browser e2e 业务验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
