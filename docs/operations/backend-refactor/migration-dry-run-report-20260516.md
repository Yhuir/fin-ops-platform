# 数据迁移 Dry-run 报告 - 20260516

本报告对应 P1-06C：app Mongo -> PostgreSQL staging -> 目标事实表转换 dry-run。当前报告只记录门禁复核和阻断项，不包含 secret、不访问 OA 源数据库、不切换生产 API、不冻结 app Mongo，也不把任何 dry-run 结果声明为正式事实源。

## 结论

| 项目 | 结论 |
| --- | --- |
| go/no-go | `NO_GO` |
| 是否完成可审计 dry-run | 否 |
| 是否允许进入正式迁移门禁 | 否 |
| 是否访问 OA 源数据库 | 否 |
| 是否写入 PostgreSQL 正式事实表 | 否 |
| 是否切换生产 API | 否 |

`NO_GO` 原因：当前工作区没有可审计的 06A manifest/NDJSON 导出产物，没有 06B staging import 执行报告，没有 staging -> facts dry-run 执行结果，也没有 count/hash/amount/month/status/file checksum 的实际对账数据。按 06C 验收规则，缺少 dry-run 对账报告时不得进入正式迁移门禁。

## 输入和证据

已复核的当前状态：

| 证据 | 状态 | 说明 |
| --- | --- | --- |
| app Mongo 备份 | 已完成 | 备份目录记录为 `/data/backups/fin_ops/2026-05-16_012900`，checksum 和恢复演练已在 runbook 中记录。 |
| app Mongo 恢复测试库 | 已完成 | 测试库记录为 `fin_ops_platform_app_restore_test_20260516`，collection count diff 为 0。 |
| PostgreSQL migration `0001`-`0007` | 已完成 | 已在 PostgreSQL 16.12 临时空库验证通过，临时库已删除。 |
| 06A 导出工具 | 已具备工具骨架 | 代码入口为 `scripts/tools/export_app_mongo.py`，本报告未运行真实导出。 |
| 06B staging 导入工具 | 已具备工具骨架 | 代码入口为 `scripts/tools/import_app_mongo_staging.py`，本报告未写 PostgreSQL。 |
| staging -> facts 转换设计 | 已有草案 | 见 `staging-to-facts-conversion-design.md`，尚无执行产物。 |

本地复核结果：

| 检查 | 结果 |
| --- | --- |
| 本地 `manifest.json` | 未发现 |
| 本地 staging validation report | 未发现 |
| 本地既有 06C dry-run report | 未发现 |
| `FIN_OPS_*` 数据迁移连接环境变量名 | 未发现 |
| `psql` | 可用 |
| `cargo` | 未发现 |

## Dry-run 步骤状态

| 步骤 | 目标 | 当前状态 | 阻断 |
| --- | --- | --- | --- |
| 1. 环境确认 | 使用 app Mongo 备份/恢复测试库或只读 app Mongo，目标为 PostgreSQL staging/临时 dry-run 库 | 未完成。缺少本次 dry-run 的 app Mongo 导出目录和 PostgreSQL staging 目标证据 | 是 |
| 2. 分区准备 | 按月份范围准备 `bank_transactions`、`invoices`、`oa_applications`、`workbench_rows`、`search_index_rows` 分区 | 未执行。当前没有 manifest 月份范围，不能确定需要创建的历史分区 | 是 |
| 3. app Mongo 导出 | 生成 manifest、对象 count 和 GridFS 文件数量/字节数 | 未执行。未发现本次 dry-run 的 manifest/NDJSON | 是 |
| 4. PostgreSQL staging 导入 | 使用 `migration_run_id` 或 `manifest_id` 隔离写入 staging，失败记录保留 | 未执行。未发现 staging import report，也未写 PostgreSQL | 是 |
| 5. staging -> 事实表转换 dry-run | 在隔离环境转换 app/read_model/job/audit 草案并生成 legacy id map | 未执行。只有转换设计草案，无执行结果 | 是 |
| 6. 对账报告 | 生成 count/hash/amount/month/status/file checksum 报告 | 未执行。缺少 source 和 target 实际指标 | 是 |

## 差异清单

当前没有可比对的 source/target 数据，因此差异清单记录为阻断型缺失差异。所有条目必须在下一次 dry-run 中用实际报告替换。

| Code | Object Type | Month | Status | Legacy ID | Dimension | Expected | Actual | 阻断说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DRY_RUN_INPUT_MISSING` | all | n/a | n/a | n/a | source_manifest | 06A manifest/NDJSON | 未发现 | 无法建立 source baseline。 |
| `STAGING_REPORT_MISSING` | all | n/a | n/a | n/a | staging_import | 06B validation report | 未发现 | 无法证明 staging 导入成功且失败记录已保留。 |
| `PARTITION_PLAN_MISSING` | partitioned_facts | n/a | n/a | n/a | partition_range | manifest 月份范围和分区准备记录 | 未发现 | 无法验证历史分区已按数据范围准备。 |
| `FACTS_DRY_RUN_MISSING` | app/read_model/job/audit | n/a | n/a | n/a | target_conversion | staging -> facts dry-run result | 未发现 | 无法验证转换映射、枚举、金额和审计/outbox 草案。 |
| `LEGACY_ID_MAP_MISSING` | all_migrated_objects | n/a | n/a | n/a | legacy_id_coverage | 100% 或有解释的豁免 | 未发现 | 无法定位 migrated target 与 legacy source 的覆盖关系。 |
| `FILE_CHECKSUM_REPORT_MISSING` | files | n/a | n/a | n/a | file_checksum | manifest checksum 和 GridFS/对象存储抽样 | 未发现 | 文件内容 checksum 属于 06D；06C 不能伪装为已通过。 |
| `AMOUNT_REPORT_MISSING` | bank_transactions/invoices | n/a | n/a | n/a | amount_totals | source/target 金额汇总一致 | 未发现 | 金额差异规则无法执行，必须阻断。 |
| `COUNT_REPORT_MISSING` | all | n/a | n/a | n/a | record_counts | source/target 数量一致或有解释 | 未发现 | 数量差异规则无法执行，必须阻断。 |
| `MONTH_STATUS_REPORT_MISSING` | finance/workbench/job | n/a | n/a | n/a | month_status_distribution | source/target 分布一致或有解释 | 未发现 | 月份和状态差异规则无法执行，必须阻断。 |

## 对账维度结果

| 维度 | 结果 | 阻断规则 |
| --- | --- | --- |
| collection/document count | 未执行 | 任一 count 差异或缺少 count 报告均阻断。 |
| NDJSON hash | 未执行 | manifest checksum 与文件内容不一致或缺失均阻断。 |
| 金额合计 | 未执行 | 任一金额差异或缺少金额报告均阻断。 |
| 月份分布 | 未执行 | 任一月份分布差异或缺少报告均阻断。 |
| 状态分布 | 未执行 | 未识别状态或缺少状态分布报告均阻断。 |
| legacy id 覆盖率 | 未执行 | 需要迁移对象缺少映射或缺少覆盖率报告均阻断。 |
| 文件数量、字节数、checksum 抽样 | 未执行 | 文件数量/字节数差异或 checksum 抽样失败均阻断；文件内容 checksum 不得在 06C 伪造通过。 |

## 下一步修复任务

1. 在受控迁移环境中选择 app Mongo 恢复测试库或只读 app Mongo 作为 source；不得访问 OA 源数据库。
2. 运行 06A 导出工具，生成本次 dry-run 专用 export 目录、`manifest.json`、NDJSON 和 GridFS metadata manifest。
3. 从 manifest 提取月份范围，使用既有 migration 分区函数为历史月份创建可重复执行的分区准备记录。
4. 运行 06B staging 导入工具，使用唯一 `migration_run_id` 写入 `staging.mongo_export_manifest` 和 `staging.mongo_import_rows`，生成 validation report；任何失败记录必须保留。
5. 在隔离 dry-run 库或同一 `migration_run_id` 隔离范围内执行 staging -> facts 转换演练，生成 `staging.legacy_id_map` 和 app/read_model/job/audit 转换结果。
6. 生成实际 count/hash/amount/month/status/file checksum 对账报告；报告必须能定位对象类型、月份、状态和 legacy id。
7. 若任一差异存在，保持 `NO_GO`，修复 mapping/import/partition/checksum 问题后重跑完整 dry-run。
8. 只有报告无未解释差异时，才允许进入正式迁移门禁评审；仍不得自动生产切流。

## 禁止事项确认

- 未访问 OA 源数据库。
- 未重新备份、覆盖或恢复 app Mongo 生产备份。
- 未冻结 app Mongo。
- 未写入 PostgreSQL 正式事实表。
- 未切换生产 API。
- 未写入 secret、URI、密码或 token。
