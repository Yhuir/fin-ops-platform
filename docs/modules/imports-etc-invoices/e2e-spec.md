# ETC发票导入 Spec-first E2E Spec

本文件定义 `/imports/etc-invoices` 的 Browser E2E 合同。测试应基于 ETC 对账任务、zip preview、confirm job、derived lifecycle 和 worker/read model 边界设计，不以当前代码行为作为需求事实源。

| Spec ID | 业务流程 | Browser 验收 |
| --- | --- | --- |
| `IMPORT-ETC-E2E-001` | 页面入口和 ready task | 进入 `/imports/etc-invoices` 后显示“ETC发票导入”；没有选择已确认且可导入的 ETC 对账任务时不能预览；unavailable task 必须解释 blocker。 |
| `IMPORT-ETC-E2E-002` | zip 文件约束 | 页面只接受 `.zip`；非 zip 文件必须被拒绝，且不能调用 ETC preview API 或通用 `/imports/files/*` API。 |
| `IMPORT-ETC-E2E-003` | preview 和 audit | 上传 zip 后调用 `/api/etc/import/preview`，带 `task_id`；页面展示 session、audit counts、可导入数、重复数、需复核文案和 `ETC导入预览结果` grid。 |
| `IMPORT-ETC-E2E-004` | 过滤/缺失/异常明细 | preview 必须展示 confirmed reconciliation task 过滤后的 included、duplicate、attachment_completed、failed、missing requirement 或 blocking issue；页面不能把 skipped/failed 行展示成可确认导入。 |
| `IMPORT-ETC-E2E-005` | preview stale | 底层 canonical invoice/import session 变化时，confirm 返回 `preview_stale`；页面必须提示重新预览，不展示“已开始后台导入”，不调用通用 files confirm。 |
| `IMPORT-ETC-E2E-006` | stale reconciliation task preview | task reopen、task version/hash 或 confirmed item set 变化时，confirm 返回 `stale_reconciliation_task_preview`；页面必须清空旧 preview，要求重新预览，禁用确认导入。 |
| `IMPORT-ETC-E2E-007` | confirm 失败 | confirm API/worker 入队失败时，页面必须显示错误，不展示“已开始后台导入”，不把下游 read model 伪装成 fresh。 |
| `IMPORT-ETC-E2E-008` | confirm job feedback | 可确认 session 提交后必须展示 background job feedback；job source 应指向 `imports_etc_invoices` 和 `etc_tickets`，不能走通用 `/imports/files/confirm`。 |
| `IMPORT-ETC-E2E-009` | 权限和系统保护 | `read_export_only` 不能上传、预览或确认；系统 write-safety blocked 时不能执行确认。 |
| `IMPORT-ETC-E2E-010` | explicit import scopes + access convergence | canonical metadata 真变更时，`etc_import_confirmed` 必须只按精确月份触发显式 import 合同声明的 Workbench、invoice lifecycle、tax offset 和 search；不直投 Cost，Workbench publish 也不投 `workbench_shard_published`。Cost 页面在访问时先收敛 Workbench，再收敛当前 Cost scope；historical repair 不进入热路径。 |
| `IMPORT-ETC-E2E-011` | 真实基础设施 worker drain | PostgreSQL/RabbitMQ/Redis/systemd import worker、derived lifecycle worker、对象存储、真实 OA 草稿和下游 read model freshness 必须在 staging 或生产只读 smoke 验证。 |

## 非目标

- 不在 deterministic Browser E2E 中连接真实 OA、对象存储、票根网 zip 或生产数据库。
- 不把 mocked confirm job queued 等同于真实 worker drain 完成。
- 不使用真实业务 zip 作为本地 fixture；需要真实样本时走 staging/manual smoke。
