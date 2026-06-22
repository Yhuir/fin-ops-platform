---
phase: 18-canonical-invoice-etc-link-closure
status: phase_c_implementation_complete_apply_gated
created: 2026-06-23
---

# 18-PLAN：Phase A-C 生产修复与架构演进计划

## 目标

修复关联台出现同一真实发票两行的问题，并把系统演进到明确事实源边界：

- `app.invoices`：canonical invoice pool，一张真实发票一个 active row。
- `app.etc_batch_invoice_links`：ETC business batch 与 canonical invoice 的关系事实。
- `app.etc_invoices`：迁移期保留为 ETC 源数据/导入审计，不再作为关联台发票事实源。

## Phase A：生产稳定化

### A1 重新做只读审计

输入：

- 当前 PostgreSQL 生产/本地镜像。
- 用户提供的 Excel 全量镜像：`/Users/yu/Desktop/sy/财务运营平台/发票/进项全量发票查询导出结果1-6.22(1).xlsx`。

必须输出：

- `app.invoices` active 总数、input/output 数、visible/hidden 数。
- Excel `发票基础信息` 有效身份数、重复身份数、缺失身份数。
- Excel `信息汇总表` 明细行数，以及按发票身份聚合后的差异说明。
- DB 多于 Excel 的发票清单分类。
- `app.invoices` 与 submitted/manual-submitted ETC batch 的 overlap 清单。
- 可自动修复、安全待人工判定、禁止自动处理三类 row set。

### A2 先写失败测试

需要覆盖：

- 正式发票导入发生在历史 ETC 批次之后时，导入服务会识别并链接/隐藏重叠发票，不产生关联台待关联重复行。
- 关联台 open invoice rows 排除已绑定 submitted ETC 批次的 canonical invoice，但仍渲染正确 ETC summary。
- Excel `信息汇总表` 明细行不会覆盖 `发票基础信息` 的发票级金额。
- 清空发票池或重建发票池后，历史 ETC 批次链接不会制造第二个关联台发票事实。

### A3 最小代码修复

优先保持 Phase A 改动窄：

- 在正式发票 import/upsert 成功后，反向查询 existing submitted/manual-submitted ETC invoice identity。
- 对严格匹配的重叠发票写入 canonical link/隐藏状态或等价 metadata，使它不再作为 open invoice row 出现。
- 在 `WorkbenchSqlProjectionBuilder` 增加防线：如果一张 visible canonical invoice 已属于 submitted ETC batch，不作为待关联发票行输出。
- 对 `信息汇总表` 导入路径增加保护，避免行项目金额覆盖发票基础信息总额。

### A4 生产修复工具

提供 dry-run-first 工具或脚本：

- `--dry-run` 默认输出 JSON。
- `--apply` 需要显式参数、reason 和操作者上下文。
- 每条修复记录包含 invoice identity、invoice id、ETC batch id、判定依据、原始状态、新状态、回滚信息。
- apply 后 enqueue 受影响月份/全量关联台 read model scope。

### A5 Phase A 完成门槛

- 只读审计已保存到 `18-AUDIT-20260623.md`。
- 自动修复候选和人工判定候选已分开：真实库 dry-run 为 112 条自动修复候选、1 条人工判定候选、34 条无需处理/禁止自动处理。
- Phase A 测试已补充并通过 targeted verification。
- dry-run 结果与预期 row set 一致，状态为 `attention`，原因是存在 1 条日期不一致人工判定候选。
- 未经用户显式确认，不执行生产 `--apply`。

## Phase B：事实源边界重构

### B1 新增 link table

新增 migration：`app.etc_batch_invoice_links`。

字段建议：

- `id uuid primary key`
- `tenant_id text not null`
- `business_batch_id text not null`
- `etc_invoice_id text`
- `invoice_id uuid not null references app.invoices(id)`
- canonical identity fields：`invoice_no`、`invoice_code`、`digital_invoice_no`、`invoice_date`
- `link_status text not null`，例如 `active` / `removed`
- `link_source text not null`，例如 `etc_import` / `historical_backfill` / `manual_repair`
- `confidence text not null`，例如 `strict` / `manual_review`
- `raw_payload jsonb not null default '{}'::jsonb`
- `created_at`、`updated_at`

约束：

- 同一 tenant、business batch、invoice identity 只能有一个 active link。
- 同一 tenant、business batch、invoice_id 只能有一个 active link。
- 为 `business_batch_id`、`invoice_id`、identity 查询建立索引。

### B2 增加 repository/service 边界

- 新增 repository 负责 link table SQL。
- service 只接收明确依赖，不接收整个 `Application`。
- 写入要幂等，重复导入/重复提交/重复修复不会产生重复 active link。
- 失败时保留审计上下文，不能半写 `app.invoices` 与 link table。

### B3 迁移写入路径

需要改造：

- ETC import confirm。
- ETC business batch submit/delete/reset。
- Existing ETC batch historical link service。
- 正式 invoice import/upsert 后的反向链接。
- Workbench relation confirm/withdraw 对 ETC summary 的恢复。

### B4 迁移读取路径

- 关联台 ETC summary 从 link table + canonical invoice 读取。
- open invoice rows 以 link table 为排除事实。
- 下游 read models 不直接把 `app.etc_invoices` 当 invoice pool。
- `app.etc_invoices` 在迁移期只承担源数据/审计/文件元数据。

### B5 Phase B 完成门槛

- Migration、repository、service 和 Workbench open invoice read model contract tests 通过；见 `18-PHASE-B-20260623.md`。
- 正式发票导入后的 submitted ETC 反向链接不再只写 metadata，同时幂等写入 link table。
- Workbench open invoice 排除优先读 active `app.etc_batch_invoice_links`，旧 `app.etc_invoices` fallback 保留到 backfill 完成。
- `app.invoices` canonical identity upsert 不再允许同一真实发票出现两个 active rows。
- 尚未完成：ETC summary 全量切到 link table、历史 backfill、reset/runbook 和生产 migration/apply。

## Phase C：历史迁移、清理和文档闭环

### C1 Backfill

- 从 `app.etc_business_batches`、`app.etc_invoices`、`app.invoices.etc_invoice_id`、`app.invoices.raw_payload`、`app.workbench_pair_relations.special_metadata.etc_batch_link` 回填 link table。
- mismatch row 进入人工审核清单。
- backfill dry-run/apply/rollback 全量可审计。

### C2 清理旧路径

- 移除或明确 deprecate 直接通过 `app.etc_invoices` 渲染关联台发票事实的路径。
- 删除重复 helper、过期 tests 或绕过新边界的逻辑。
- 保留必要兼容窗口，但必须有清晰 TODO/文档和测试保护；不允许无限期双写无事实源说明。

### C3 更新 reset 与运维

- `reset_invoices` 必须明确处理 canonical invoices、ETC batch links、ETC source metadata、workbench relations、read models 的边界。
- 提供“清空发票池后重新导入”的生产 runbook，证明不会再次出现历史 ETC 批次重复发票。

### C4 最终验收

- 重跑 Excel 镜像审计，缺失 0；extra 和 mismatch 都有解释或修复记录。
- 重跑 overlap 审计，关联台 open invoice duplicate 为 0。
- 真实或镜像 smoke：ETC 历史批次存在 -> 清空/重建发票池 -> 导入正式发票 -> 关联台只显示 ETC summary，不显示重复待关联发票。
- 文档更新覆盖模块事实源、状态机、测试矩阵和运维 runbook。

### C5 Phase C 实现状态

- 已完成：`backfill_etc_batch_invoice_links` dry-run/apply/rollback 工具、Workbench ETC summary link table 优先读取、reset/runbook/module docs 和 Phase C GSD 记录。
- 已保留：旧 `app.etc_invoices` summary fallback，用于尚未 backfill 的历史数据；删除 fallback 必须等生产 link table 覆盖证明完成。
- 未执行：生产 migration、生产 backfill `--apply`、生产 repair `--apply`、生产 Workbench active generation rebuild。
- 当前停止点：生成生产审批包前只能执行 read-only dry-run；任何真实写入必须等待用户确认 exact row set、reason、operator、rollback 和验证方式。

## 七类测试覆盖

- Business core：canonical invoice identity、ETC overlap 判定、金额明细/发票级总额规则。
- Service-layer：invoice import、ETC link service、repair/backfill service、reset service、read model invalidation。
- API contract：如果新增 repair/backfill API 或调整 import/ETC API，覆盖成功、非法状态、幂等、权限、错误响应。
- Read model/cache/worker：Workbench、invoice relation、ETC summary、导入 confirmed event fan-out。
- Frontend interaction：只有 UI 行为或 API shape 变化时新增；若 Phase A/B 纯后端，应保留现有 Workbench UI regression。
- End-to-end business flow：至少覆盖 formal invoice import after submitted ETC batch 和 reset/reimport 后 Workbench 无重复。
- Existing regression：现有 ETC submission、撤回关联、普通发票导入、普通 Workbench 匹配、税金/成本/进项使用页面不变空。

## 执行纪律

- 每个执行 prompt 都必须先声明本轮停止条件。
- 每轮结束必须输出：已完成、未完成、下一轮建议 prompt。
- 生产数据 `--apply` 前必须停下来等用户确认，不在自动循环中执行。
- 如果审计数字与本文件已知事实不一致，以最新只读审计为准，先更新计划再继续。
