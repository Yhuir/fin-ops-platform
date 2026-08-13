# 银行流水导入 Spec-first E2E Spec

本文件定义 `/imports/bank-transactions` 的 Browser E2E 合同。测试应基于本页业务流程、API 契约和 worker/read model 边界设计，不以当前实现细节作为需求真相。

| Spec ID | 业务流程 | Browser 验收 |
| --- | --- | --- |
| `IMPORT-BANK-E2E-001` | 页面入口和配置 | 进入 `/imports/bank-transactions` 后显示“银行流水导入”；未选择文件时不创建 session；每个文件必须选择银行账户后才允许预览。 |
| `IMPORT-BANK-E2E-002` | 预览和 audit | 上传 XLS/XLSX 后调用 `/imports/files/preview`，带 `bank_transaction` 与每文件账户 mapping override；页面展示 audit counts、可导入数、重复数和 preview grid；慢预览期间预览按钮必须显示进行中状态，预览/清空/确认动作全部禁用，不能重复提交或中断成半状态。 |
| `IMPORT-BANK-E2E-003` | 重复/未导入明细 | 文件内重复、跨文件重复、已存在、损坏文件、异常或需复核行必须进入明细表；页面不能把 skipped/duplicate/error 行展示成可确认导入；损坏文件 + 正常文件混合上传时，确认只能提交正常文件 ID。 |
| `IMPORT-BANK-E2E-004` | 银行账户冲突 | 文件识别账号与所选账号不一致时必须阻止确认；用户清空预览并选择识别到的正确账户后才能重新预览和导入，前后端都不得保留强制继续入口。 |
| `IMPORT-BANK-E2E-005` | preview stale | 预览后底层事实变化时，confirm 返回 `preview_stale`；页面必须提示重新预览，不创建 import job，也不调用 operation barrier 或 Workbench 页面 API。 |
| `IMPORT-BANK-E2E-006` | confirm 失败 | confirm API/worker 入队失败时，页面必须显示错误，不展示“已确认导入”，不调用 operation barrier 或 Workbench 页面 API，也不把下游 read model 伪装成 fresh。 |
| `IMPORT-BANK-E2E-007` | confirm 成功和下游访问收敛 | 可确认文件提交后显示事实提交反馈；普通 import job result 的 `operation_barrier_targets` 必须为空，导入页不得读取或等待任何业务页面；进入银行明细、成本统计等消费者时，各页通过自己的 fresh gate 展示导入事实。返回 `job` 时只能展示“已开始后台导入”，不能宣称下游 fresh。 |
| `IMPORT-BANK-E2E-008` | 权限和系统保护 | `read_export_only` 不能上传、预览或确认；系统 write-safety blocked 时不能执行确认。 |
| `IMPORT-BANK-E2E-009` | 真实基础设施 worker drain | PostgreSQL/RabbitMQ/Redis/systemd import worker、Workbench matching、bank detail/account balance/read model freshness 必须在 staging 或生产只读 smoke 验证。 |

## 非目标

- 不在 deterministic Browser E2E 中连接真实 OA、真实银行文件或生产数据库。
- 不把 mocked confirm 成功等同于真实 worker drain 完成。
- 不使用真实业务 Excel 作为本地 fixture；需要真实样本时走 staging/manual smoke。
