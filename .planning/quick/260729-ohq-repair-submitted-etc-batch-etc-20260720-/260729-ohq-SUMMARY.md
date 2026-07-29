---
quick_id: 260729-ohq
status: completed
completed_at: 2026-07-29
runtime_commits:
  - e39a2eb92
  - 6fe1f537d
  - 2c6ecf6c9
  - 0dab8487d
  - 0bbeb2d4b
production_release: main-0bbeb2d4-20260729194337
---

# Quick Task 260729-ohq Summary

## 结果

- submitted ETC business batch `etc_business_batch_241132` / `etc_batch_0045` / `etc_20260720_001` 已从 64 张、3686.36 元修复为 68 张、3740.82 元。
- 仅补入经确认的四张 canonical ETC 发票：`26537911970600073086`、`26537911970600093773`、`26537911620600159674`、`26537911810600133419`，合计 54.46 元。
- 四张原始 canonical 发票没有 PDF/XML；修复保持 `has_pdf=false`、`has_xml=false`，没有伪造附件。
- OA 草稿 `6a5d77999bb648143aa7c2c6` 和已关闭对账任务 `ETC-RECON-241132` 未写入；执行前后 fingerprint/hash 一致。
- business batch version 收敛到 13，submission version 收敛到 2；重复执行返回幂等结果，不重复新增成员或审计事件。

## 架构闭环

- 修复入口绑定 business/submission/external 三重 owner、目标发票号、目标金额、目标结果、expected version 和 dry-run fingerprint；执行需要 operator/reason，并在单一 PostgreSQL 事务内完成。
- 复用现有 ETC invoice normalization、batch link、canonical overlap、审计和 historical ETC lifecycle；没有直接修改 OA、正式 relation、Workbench active generation、Redis 或页面 DTO。
- Workbench schema 升级到 v11，折叠汇总以已提交 business batch 的完整成员为事实源；部分 strict link 不再截断同批其它成员。
- historical ETC repair runtime port 通过正式 `ReadModelRefreshGateway` 投递精确月份；Search 投影继续走 durable queue。
- Search 后台 canonical scan 使用 90 秒 worker statement budget；页面 Workbench 查询继续保持既有 2 秒 fail-fast，不扩大交互请求预算。

## 生产结果

- 正式 release：`main-0bbeb2d4-20260729194337`。
- ETC detail API：68 张 / 3740.82 元，四张补录发票均存在。
- Workbench：折叠摘要 68 张 / 3740.82 元，`collapsed_rows.invoice` 为 68 行、合计 3740.82 元，四张补录发票均存在。
- Search `2026-06`：`done/fresh`，`stale_count=0`；新 refresh 一次成功，handler 8151.571ms。
- durable queue：`pending=0`、`publishing=0`、`failed=0`、`publish_failed=0`；三个已被新鲜版本覆盖的旧 Search dead letter 已按 dry-run proof 安全归档。
- `etc-tickets` 与 `reconciliation-workbench` Page Audit 均为 `pass/fresh/drained`、零 issue。
- System Audit 仍有一个与本任务无关的既有 `bank-flow-rule-batches` integrity failure；当前 freshness 和 queue 均正常。

## 性能

生产 HTTPS、gzip、1 次 warmup + 8 次 measured：

| Endpoint | p50 | p95 | max | 结果 |
| --- | ---: | ---: | ---: | --- |
| ETC business batch detail | 116.738ms | 176.876ms | 201.647ms | 通过 1s |
| Workbench 精确搜索 | 114.343ms | 129.225ms | 129.264ms | 通过 1s |
| Workbench group detail | 100.556ms | 161.452ms | 188.212ms | 通过 1s |

## 复用与删除

- 没有新增表、常驻 worker、read model、Redis 缓存、页面分支或 OA fallback。
- 删除了 Workbench 在“已有任一 strict link”时跳过整批 business members 的旧截断条件。
- 修复工具保留为 owner-scoped、dry-run-first、可审计且可幂等复用的历史维护能力；没有保留目标批次临时输入文件。
