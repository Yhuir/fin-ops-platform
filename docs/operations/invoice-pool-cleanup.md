# 统一发票池清理与重导

本文档记录统一发票池污染清理的运维边界。该流程用于把 `app.invoices` 收敛为唯一、去重的正式进销项发票池；ETC ZIP/PDF/XML 和 OA 附件识别不得把 `app.etc_invoices` 或 OA 解析缓存当作第二发票池。

## 当前事实

- 已备份 invoice 相关表到 `.runtime/backups/invoice-pool-audit/20260621031938`。
- 清理 dry-run 产物位于 `.runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run`。
- 最终审阅版执行包位于 `.runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run/final_cleanup_runbook.md` 和 `.runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run/final_cleanup_execution_review.sql`；当前均为只读审阅材料，不是可直接执行脚本。
- dry-run 口径：正式发票 identity 优先使用 `digital_invoice_no`、20 位 `invoice_no`、`invoice_code + invoice_no`，最后才是税号/日期/金额 fallback。
- 当前 dry-run 结论：两份正式 Excel 共 391 个 identity；`app.invoices` 当前 638 行、614 个正式 identity；非 Excel 污染 225 行，Excel 内重复 22 行，targeted cleanup 后可到 391 行。
- 推荐清理方式是先完整 reset canonical invoice pool，再从两份正式 Excel 重导，最后重建 read model 和 Workbench active generation。

## 工具

清理前必须先运行默认只读 preflight：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621031938 \
  --json
```

该工具只读取备份、dry-run 摘要、soft reference inventory 和可选 PostgreSQL live counts。没有 `FIN_OPS_POSTGRES_DATABASE_URL` 时也能离线检查备份产物；配置了数据库时会额外核对 `app.invoices` 行数是否仍等于 dry-run 时的 638 行。

执行当天新生成的 scoped 备份目录可以和既有 dry-run 审阅包分离。此时显式传入两条路径：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621050130 \
  --dry-run-dir .runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run \
  --oa-reverse-batch-strategy archive_legacy_polluted_history \
  --workbench-relation-strategy rebuild_after_reimport \
  --json
```

如果不传 `--dry-run-dir`，工具会优先使用 `backup-dir/cleanup_dry_run`；当最新备份是 scoped-only 且没有同目录 dry-run 时，会选择 `.runtime/backups/invoice-pool-audit/` 下最近的 `cleanup_dry_run`。正式执行前仍建议显式传入两条路径，避免误读旧审阅包。

`--execute` 是强 guard 模式。执行前必须同时满足：

- `FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE=1`
- `FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED=1`
- `--confirm-token DELETE_APP_INVOICES_AND_REIMPORT`
- preflight 无 soft reference blocker
- `--execution-sql-file` 指向可执行 SQL 变体
- `--execution-sql-sha256` 精确匹配该 SQL 文件内容

如果 dry-run 发现软引用，必须显式给出策略后才允许 preflight 进入 `PASS_READY_TO_EXECUTE`：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621031938 \
  --oa-reverse-batch-strategy archive_legacy_polluted_history \
  --workbench-relation-strategy rebuild_after_reimport \
  --json
```

本地 runtime 若使用 `.runtime/fin_ops_platform/local-postgres.env` 保存 PostgreSQL DSN，live preflight 必须在同一个 shell 中先加载该文件。不要把 DSN 打印到终端或写入文档：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621031938 \
  --oa-reverse-batch-strategy archive_legacy_polluted_history \
  --workbench-relation-strategy rebuild_after_reimport \
  --json
```

进入正式执行前，`gate_recommendation` 必须为 `PASS_READY_TO_EXECUTE`，且 live count guard 必须同时确认：

- `app.invoices = 638`
- `app.etc_invoices = 259`

审阅包中的 `final_cleanup_execution_review.sql` 仍不是可执行脚本。工具会拒绝包含 `REVIEW ONLY`、`DO NOT RUN AS A PRODUCTION CLEANUP SCRIPT` 或 `rollback;` 的 SQL 文件。正式执行前必须在用户当前明确批准后，基于审阅包生成新的 executable variant，并在文件中加入以下 marker：

```sql
-- FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTABLE_SQL
```

然后计算并传入精确 SHA-256：

```bash
shasum -a 256 path/to/executable_cleanup.sql

FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE=1 \
FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED=1 \
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621050130 \
  --dry-run-dir .runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run \
  --oa-reverse-batch-strategy archive_legacy_polluted_history \
  --workbench-relation-strategy rebuild_after_reimport \
  --execute \
  --confirm-token DELETE_APP_INVOICES_AND_REIMPORT \
  --execution-sql-file path/to/executable_cleanup.sql \
  --execution-sql-sha256 "<上一步输出的 sha256>" \
  --json
```

不要复用审阅版 SQL 作为 `--execution-sql-file`；该文件以 `rollback;` 结尾，工具会按设计拒绝。

策略含义：

- `--oa-reverse-batch-strategy archive_legacy_polluted_history`：`app.input_invoice_usage_oa_reverse_batches` 保存的是当时选择的发票 ID、展示行、OA 草稿/提交状态等历史业务记录。若其中引用了清理前污染发票 ID，不能把这些旧 ID 迁移进新发票池；必须依赖本次备份保留审计证据，并把旧污染批次作为历史归档处理。
- `--workbench-relation-strategy rebuild_after_reimport`：`read_model.workbench_relation_groups` 是 Workbench active generation read model。发票池重导后必须通过 read model 刷新/重建流程恢复，不手工迁移旧 generation 内的发票 ID。

## 阻塞 Gate

破坏性清理前必须先解决两个数据策略：

- `app.input_invoice_usage_oa_reverse_batches.invoice_ids` 当前引用旧 `oa-att-inv-*` 发票 id。清理时必须选择归档这些历史污染批次；不能留下失效 invoice id，也不能把污染 id 继续带入统一发票池。
- `read_model.workbench_relation_groups` 当前保存旧 invoice id 数组。Workbench 使用 active generation 发布模型，清理后必须通过正式重建/刷新流程恢复，不能只删除普通 read model 行。

`app.etc_invoices` 不在第一阶段删除范围。它应作为 ETC ZIP/PDF/XML metadata/附件关系迁移或退役对象处理，不得再写入 `app.invoices` 创建 canonical invoice。

历史版本可能已经在 `app.invoices` 中留下 ETC-created canonical 污染。执行清理时只能把 `invoice_source='ETC导入'`、`invoice_kind='ETC发票'` 且没有非 ETC source link 的行视为 legacy 污染候选；通过正式 Excel 导入或 OA 附件受控创建的 canonical invoice 必须保留，最多移除旧 ETC source link / batch id。

## 执行当天备份

即使已经存在 `.runtime/backups/invoice-pool-audit/20260621031938`，正式 destructive reset 前仍必须生成执行当天新备份。推荐目录：

```bash
BACKUP_RUN_ID="$(date +%Y%m%d%H%M%S)"
BACKUP_DIR=".runtime/backups/invoice-pool-audit/${BACKUP_RUN_ID}"
mkdir -p "${BACKUP_DIR}"
```

备份命令模板。推荐备份事实表和必要上下文，不备份可重建的超大 read model 行数据；read model schema 仍保留，正式 reset/reimport 后通过刷新链路重建：

```bash
pg_dump "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL}}" \
  --format=custom \
  --file="${BACKUP_DIR}/invoice_fact_tables.dump" \
  --table=app.invoices \
  --table=app.etc_invoices \
  --table=app.import_batches \
  --table=app.import_batch_rows \
  --table=app.oa_attachments \
  --table=app.oa_attachment_invoice_cache \
  --table=app.input_invoice_usage_oa_reverse_batches \
  --table=read_model.workbench_generations \
  --table=read_model.workbench_snapshots \
  --table=read_model.workbench_summary \
  --table=read_model.workbench_relation_groups \
  --table=job.import_jobs

pg_dump "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL}}" \
  --schema-only \
  --file="${BACKUP_DIR}/invoice_related_schema.sql" \
  --table=app.invoices \
  --table=app.etc_invoices \
  --table=app.input_invoice_usage_oa_reverse_batches \
  --table=read_model.invoice_lifecycle_rows \
  --table=read_model.input_invoice_usage_rows \
  --table=read_model.output_invoice_collection_rows \
  --table=read_model.pending_invoice_rows \
  --table=read_model.workbench_generations \
  --table=read_model.workbench_rows \
  --table=read_model.workbench_groups \
  --table=read_model.workbench_group_rows \
  --table=read_model.workbench_relation_scopes \
  --table=read_model.workbench_relation_groups \
  --table=read_model.workbench_relation_rows

python3 - "${BACKUP_DIR}" <<'PY' > "${BACKUP_DIR}/backup_summary.json"
import json
from pathlib import Path
import sys

print(json.dumps({
    "backup_dir": str(Path(sys.argv[1]).resolve()),
    "backup_kind": "invoice_fact_tables",
    "notes": [
        "facts and invoice/OA relation tables are backed up as custom dump",
        "large rebuildable read model row data is intentionally excluded from data dump",
        "read model schema is retained for recovery inspection",
    ],
}, ensure_ascii=False, indent=2))
PY

shasum -a 256 "${BACKUP_DIR}/invoice_fact_tables.dump" "${BACKUP_DIR}/invoice_related_schema.sql" "${BACKUP_DIR}/backup_summary.json" \
  > "${BACKUP_DIR}/checksums.tsv"
```

清理工具接受推荐的 scoped 备份产物：`invoice_fact_tables.dump`、`invoice_related_schema.sql`、`backup_summary.json`、`checksums.tsv`。历史审阅包中的 `invoice_related_tables.dump` / `audit_summary.json` 也仍可被识别，但正式执行当天应优先生成 scoped 备份，避免把 `read_model.workbench_rows` 这类可重建大表作为必需恢复物。

备份完成后，在同一个 live DB 环境再次运行 preflight，并显式指定执行当天 `--backup-dir` 与已审阅 `--dry-run-dir`。只有备份存在、live count guard 通过、软引用策略已显式选择，并且用户再次批准后，才允许把审阅版 SQL 转换为 executable variant。

## 重导输入文件校验

正式 reset 前还必须确认两份 Excel 输入文件仍可被当前导入 parser 正确读取。该校验不写数据库，必须返回 `PASS_INPUT_FILES`：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --verify-input-files \
  --input-invoice-xlsx "/Users/yu/Desktop/sy/财务运营平台/发票/进项发票20260101-20260618_合并.xlsx" \
  --output-invoice-xlsx "/Users/yu/Desktop/sy/财务运营平台/发票/销项发票20260101-20260618(2).xlsx" \
  --expected-input-rows 371 \
  --expected-output-rows 20 \
  --json
```

当前已验证结果：

- `进项发票20260101-20260618_合并.xlsx`：371 行，全部有强 identity；月份分布为 2026-01:70、2026-02:46、2026-03:74、2026-04:64、2026-05:105、2026-06:12。
- `销项发票20260101-20260618(2).xlsx`：20 行，全部有强 identity；月份分布为 2026-01:1、2026-02:3、2026-03:6、2026-04:1、2026-05:8、2026-06:1。

## 重导服务链路预演

正式 reset 后的重导必须复用现有发票导入链路，不得用临时 SQL 直接写 `app.invoices`。当前已用真实两份 Excel 做过纯内存服务链路演练，执行路径为：

```text
FileImportService.preview_files(...)
FileImportService.confirm_session(...)
ImportNormalizationService.confirm_import(...)
```

演练不连接 PostgreSQL、不写数据库，仅验证 parser、file import preview、confirm、去重和 canonical invoice 构建合同。结果：

- 首次导入进项文件：preview `row_count=371`、`success_count=371`、`duplicate_count=0`、`error_count=0`；confirm 后 371 条 input invoice。
- 首次导入销项文件：preview `row_count=20`、`success_count=20`、`duplicate_count=0`、`error_count=0`；confirm 后 20 条 output invoice。
- 首次两文件确认后：内存发票池 391 条，`source_unique_key` 唯一 391，空 key 0。
- 同样两文件再次导入：进项 duplicate 371、销项 duplicate 20；重复确认后内存发票池仍为 391 条，`source_unique_key` 唯一 391。

该预演只证明正式导入 service 合同可满足 391 和幂等目标；不替代生产 PostgreSQL reset、file import 持久化、runtime worker drain 或最终 `--verify-final`。

## 验收

清理和重导完成后必须证明：

- `app.invoices` 正好 391 行。
- 正式 identity 正好 391 个。
- 进项 371 行，销项 20 行。
- Excel 391 个 identity 全部存在，缺失 0。
- `app.invoices` 中 ETC-only canonical 污染为 0。
- 同一两份 Excel 再次导入不会新增重复发票。
- 相关 read model 和 Workbench active generation fresh，且不再引用清理前旧 invoice id。

统一发票池最终状态先用只读 final invariant gate 验证。该 gate 同时检查数量不变量和 `candidate_keep_excel_identities.csv` 中的 391 个 Excel identity 集合，避免“数量是 391 但不是那 391 张发票”的误判：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.invoice_pool_cleanup \
  --backup-dir .runtime/backups/invoice-pool-audit/20260621050130 \
  --dry-run-dir .runtime/backups/invoice-pool-audit/20260621031938/cleanup_dry_run \
  --input-invoice-xlsx "/Users/yu/Desktop/sy/财务运营平台/发票/进项发票20260101-20260618_合并.xlsx" \
  --output-invoice-xlsx "/Users/yu/Desktop/sy/财务运营平台/发票/销项发票20260101-20260618(2).xlsx" \
  --oa-reverse-batch-strategy archive_legacy_polluted_history \
  --workbench-relation-strategy rebuild_after_reimport \
  --verify-final \
  --json
```

清理前运行该命令应返回 `BLOCKED_FINAL_INVARIANTS`，因为当前库仍是污染态。清理、重导和 read model 重建完成后，该 gate 必须返回 `PASS_FINAL_INVARIANTS`。传入两份正式 Excel 时，工具直接从 Excel 解析 expected identity；未传 Excel 时才回退到 dry-run 的 `candidate_keep_excel_identities.csv`。失败时读取 `final_invariants.failures[]`，逐项确认实际值和期望值；若出现 `missing_excel_identity_count` 或 `extra_identity_count`，还要读取 `final_invariants.identity_set_check.examples` 中的 identity 示例定位缺失或多余发票。不得只凭页面显示 391 条就判定闭环。
