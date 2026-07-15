# 生产页面 Audit 完整性修复计划

## 目标

- 在 `main` 上修复当前 5 个失败页面 Audit，不放宽 proof，也不伪造外部证据。
- 修复未来导入链路，保证发票/银行文件上传后 canonical facts、import provenance 与税额抵扣 read model 能自动收敛。
- 通过受控 dry-run/execute 工具恢复已经受影响的数据，并保留 rollback manifest。

## Grill-me 结论

| 编号 | 失败 | 根因 | 分类 | 修复边界 |
| --- | --- | --- | --- | --- |
| F-01 | `imports.bank-transactions` | import row 使用进程内全局自增 ID；多进程重复 ID 被后续 upsert 改挂到其它 batch | 代码 + 数据 | `ImportNormalizationService` 生成 batch-scoped row ID；repository 禁止跨 batch re-parent；repair service 从持久化 file payload 与 canonical transaction 重建 row evidence |
| F-02 | `imports.invoices` | 税务导出的一张发票可包含多条商品/折扣行，旧逻辑把后续行当重复并只保存第一行金额 | 代码 + 数据 | parser 按单文件发票身份聚合行；Audit 对历史 component rows 按 batch/invoice 聚合；repair service 修正 9 张 canonical invoice 合计 |
| F-03 | `tax-offset` | source version 是全局 invoice facts 版本，但导入只 invalidated 受影响月份 | 代码 + 运行时 | invoice facts 变化时 invalidated/rebuild 全部现存 tax-offset scopes；部署后正式 force refresh |
| F-04 | `settings` | 持久化 settings 早于当前 normalization contract | 数据 | 使用现有 `settings-normalize` dry-run/execute，不新增旁路 |
| F-05 | `imports.etc-invoices` | 已被成功 task 覆盖的旧 preview/failed attempt 仍被页面 Audit 当作当前失败 | Audit contract | 只有精确 task 已 `imported/closed` 时降为显式 covered warning；未覆盖失败仍 fail closed |

## 模块 I/O

- `import_file_service`：输入物理 Excel 行；输出每个文件内按发票身份聚合后的 import rows，原始 component rows 保存在聚合 row payload 中；无 DB/HTTP I/O。
- `imports`：输入 normalized rows；输出 batch-scoped deterministic row IDs 与 canonical objects；无 DB/HTTP I/O。
- `postgres_repositories/core`：只负责 import rows 持久化；跨 batch ID 冲突必须 fail fast，禁止 re-parent。
- `import_audit_repair_service`：输入 repository snapshot；输出纯 repair plan、source fingerprint、rollback manifest；无 DB/HTTP I/O。
- `postgres_repositories/import_audit_repair`：只负责加载 repair snapshot 与单事务应用精确 plan。
- `tools/import_audit_repair_ops`：只负责 CLI dry-run/execute orchestration；不承载业务判断。
- `etc_import_page_audit`：只读 proof；covered 判定只消费持久化 task/session/job edges，不写数据。
- `tax_offset_runtime_service`：invoice global source version 改变时负责全部 scope invalidation/enqueue。

## 旧逻辑删除条件

- 删除 import row 进程内 `_row_counter` 及其 snapshot/persistence/source-version 依赖。
- 删除逐物理行创建 canonical invoice 的 invoice-export 路径；单文件内先聚合后进入统一 import normalization。
- 不新增 legacy fallback，不保留允许 `app.import_batch_rows` 跨 batch upsert 的写法。
- 不把 failed ETC session 无条件降级；只有已有正式 task 完成证据才视为 covered。

## 验证和发布 Gate

1. 业务单元：发票多明细/折扣/混合税率、header 冲突、deterministic row ID。
2. Service/repository：repair dry-run、fingerprint conflict、单事务写入、跨 batch row ID fail-fast、全 scope tax invalidation。
3. API/Audit：历史 component rows 聚合 proof；covered/uncovered ETC；五个页面 response contract。
4. Read model/job：发票确认后 tax-offset 全 scope invalidation 与 durable enqueue。
5. Frontend：无 response shape/UI 变化，不适用新增组件测试；复跑现有 import/audit 页面回归。
6. E2E：invoice upload -> confirm -> canonical aggregate -> tax-offset refresh；bank preview provenance 不被后续 invoice preview 覆盖。
7. Existing regression：全部 page Audit、import API、PostgreSQL repository、deploy control、docs/architecture gates。

发布顺序：测试 -> commit/push -> `deploy-oa.sh` -> repair dry-run -> 保存 manifest -> repair execute -> settings normalize dry-run/execute -> tax-offset force refresh -> queue drain -> 17 页 system Audit 两次连续通过。外部 evidence 未注册仍保持 `unknown`，不伪造为 pass。

## 执行状态

- [x] 分支/工作树鉴别：旧 `codex/workbench-cost-coherent-snapshot-v8` 无独有提交，已安全切回 `main`，无需 merge 或 cherry-pick。
- [x] 五个 Audit 失败的代码/数据根因定位。
- [x] 未来导入链路、历史 Audit proof 与受控修复工具实现。
- [x] 相关单元/仓储/Audit/read-model/deploy-control 测试补齐。
- [x] `bash scripts/verify.sh all`：后端全量、前端全量、生产构建与 177/177 Playwright 业务流通过。
- [ ] commit/push。
- [ ] 生产发布、指纹锁定的 dry-run/execute 数据恢复。
- [ ] settings normalization、read model 收敛、system Audit 两次连续通过与 520 关系回归。

### 生产 dry-run 反馈

- 首次 release `main-6ff1e40d-20260715232536` 的只读 dry-run 在写入前按设计 fail closed：`batch_import_0046` 的 file payload 保留了 preview 时两条 `created`，而 confirm 时按同一 identity 落为一条 `created` + 一条 `duplicate_skipped`。
- 修复计划不盲信 stale preview decision；对已落 canonical 的银行流水，由 `source_unique_key + canonical source_batch_id + batch 内首次出现顺序` 恢复最终 decision，仍以正式 batch counts 作 fail-closed 终局门禁。
- 首次 dry-run 未执行任何数据写入；补齐生产历史格式回归测试后需重新走 commit/push/deploy/dry-run。
