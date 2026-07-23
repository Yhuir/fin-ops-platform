# 发票导入 Spec-first E2E Spec

本文件定义 `/imports/invoices` 的 Browser E2E 合同。测试应基于发票导入业务流程、API 契约、derived lifecycle 和 worker/read model 边界设计，不以当前代码行为作为需求事实源。

| Spec ID | 业务流程 | Browser 验收 |
| --- | --- | --- |
| `IMPORT-INVOICE-E2E-001` | 页面入口和每文件方向 | 进入 `/imports/invoices` 后显示“发票导入”；未选择文件时不创建 session；每个文件必须选择 `input_invoice` 或 `output_invoice` 后才允许预览。 |
| `IMPORT-INVOICE-E2E-002` | 预览和 audit | 上传 XLS/XLSX 后调用 `/imports/files/preview`，带 `invoice_export` 与每文件 `batch_type` override；页面展示 audit counts、可导入数、异常数、需复核文案和 preview grid；慢预览期间预览、清空、确认都必须锁定，且只能提交一次 preview 请求。 |
| `IMPORT-INVOICE-E2E-003` | 重复/未导入明细 | 文件内重复、跨文件重复、已存在、异常或需复核行必须进入明细表；损坏发票文件必须作为 file-level error 展示，不能让整个 preview 崩溃；页面不能把 skipped/duplicate/error 行展示成可确认导入，confirm 只能提交有效文件 id。 |
| `IMPORT-INVOICE-E2E-004` | preview stale | 预览后底层发票事实变化时，confirm 返回 `preview_stale`；页面必须提示重新预览，不创建 import job，也不调用 operation barrier 或 Workbench 页面 API。 |
| `IMPORT-INVOICE-E2E-005` | confirm 失败 | confirm API/worker 入队失败时，页面必须显示错误，不展示“已确认导入”，不调用 operation barrier 或 Workbench 页面 API，也不把下游 read model 伪装成 fresh。 |
| `IMPORT-INVOICE-E2E-006` | confirm 排队和下游访问收敛 | 可确认文件提交后必须返回 durable import job；queue 不可用时显示失败且保持 preview。已完成普通 import result 的 `operation_barrier_targets` 必须为空，不得读取或等待 Workbench/其它业务页面；返回进行中 `job` 时只能展示“已开始后台导入”，不能宣称下游页面 fresh。 |
| `IMPORT-INVOICE-E2E-007` | 权限和系统保护 | `read_export_only` 不能上传、预览或确认；系统 write-safety blocked 时不能执行确认。 |
| `IMPORT-INVOICE-E2E-008` | downstream access convergence | `invoice_import_confirmed` 只提交 canonical invoice facts/version/audit，产生零页面 dirty/outbox；Workbench、invoice lifecycle、tax、cost、pending、input/output、OA pending 和 search 分别在访问时通过 freshness/status exact-scope 收敛。 |
| `IMPORT-INVOICE-E2E-009` | 真实基础设施 worker drain | PostgreSQL/RabbitMQ/Redis/systemd import worker、derived lifecycle worker、下游 read model freshness 和 App Status/import progress 必须在 staging 或生产只读 smoke 验证。 |

## 非目标

- 不在 deterministic Browser E2E 中连接真实 OA、真实发票文件或生产数据库。
- 不把 mocked confirm 成功等同于真实 worker drain 完成。
- 不使用真实业务 Excel 作为本地 fixture；需要真实样本时走 staging/manual smoke。
