# 流水规则批次页面直读迁移

## Goal

将 `bank-flow-rule-batches` 的列表与详情读取切换到 PostgreSQL canonical facts，移除页面 read model freshness、refresh enqueue 和前端 polling 语义，同时保持现有写侧 relation command、权限、CAS、审计与幂等合同。

## I/O

- 输入：`month`、`type`、`status`、`bucket`、`account_key`、`page`、`page_size`、`batch_id`。
- 事实源：`app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`app.bank_transactions`、有效分类/确认、`app.app_settings`、`app.workbench_pair_relations(status='active')`。
- 输出：`summary`、`categories`、`batches`、`pagination`、`detail`；不输出 read-model status/version/source-version/refresh 字段。
- 写侧：继续通过既有 application service、relation command 和 changed-batch delta writer 原子提交/撤回/重置；页面在写成功后单次重新 GET。

## Tasks

- [x] 新增页面专属 PostgreSQL canonical query repository，在显式 `REPEATABLE READ READ ONLY` snapshot 中完成服务端筛选、排序、分页、summary/facets 与详情读取；只读 active pair relations。
- [x] 将 `BankFlowRuleBatchApplicationService` 和 route 切换到 query repository，删除页面专属 read-model 状态、refresh producer 调用、runtime fallback 与 projection relation detail 读取。
- [x] 删除前端 read-model 类型、状态、轮询与本地 optimistic refresh；所有写操作成功后单次 GET。
- [x] 更新页面模块、API 与 app architecture 文档；共享 manifest/worker/deploy 删除只记录 HANDOFF。
- [x] 增补 repository/service/API/frontend 测试，运行 lint、相关 backend/frontend tests、typecheck/build 与查询次数/性能验证。

## Acceptance

- 页面热路径不引用 `read_model.bank_flow_rule_batch_rows`、no-OA legacy 或 Workbench relation projection。
- 列表、summary、facets/counts 处于同一 snapshot，查询次数固定且分页在 SQL。
- 详情关系只来自 `app.workbench_pair_relations where status='active'`，提交/撤回历史与冻结 requirement/tag metadata 保持。
- 响应与前端不再出现旧 read-model status、refresh enqueue 或 polling。
- no-OA、关联台、成本/外部往来款行为不变。

## Status

页面分支实现完成。共享 worker/registry/deploy 清理、canonical draft writer 归属、BRB-E2E-003 的共享 Workbench fixture 和生产验证交主控处理。
