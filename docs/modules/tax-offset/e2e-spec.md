# 税金抵扣 Spec-first E2E Spec

本文件定义 `/tax-offset` 页面的浏览器级验收合同。Spec 以真实业务流程为准，代码只用于定位 route、API、selector 和 mock。

## 模块目标

税金抵扣页必须让用户基于 fresh `tax_offset` read model 查看销项税额、进项认证计划、已认证结果，完成试算、保存计划和已认证发票导入。发票导入、ETC/OA 附件 canonical promotion 与税务认证等实际 source 变化必须通过 read model/worker 边界进入页面；Workbench relation 不属于税金 projection source，不能触发税金造数或 queue fan-out。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `TAX-E2E-001` | 首屏读取 fresh tax offset read model | P0 | 进入 `/tax-offset` 后显示当前月份销项票、进项计划、统计卡和结果面板；API payload 的 `read_model_status=fresh`、`read_model_scope_key` 和 `source_versions` 被消费。 |
| `TAX-E2E-002` | 用户取消/恢复进项计划并重新试算 | P0 | 勾选变化后调用 calculate API，统计卡和结果面板按后端返回更新，页面不自行重算业务规则。 |
| `TAX-E2E-003` | 保存税金抵扣计划 | P0 | 保存时提交 selected ids、expected read model scope/source versions 和 idempotency key；成功后命令立即结束并重跑当前月份 normal GET，由 tax fresh gate 按需收敛；stale/conflict 不能伪成功。 |
| `TAX-E2E-004` | 已认证发票导入 preview/confirm | P0 | 选择 XLSX 后可预览识别结果；确认导入 job 只证明事实已提交，不等待页面重建；进入/刷新税金页和已认证结果 Drawer 时由当前月份 fresh gate 收敛并显示新增记录。 |
| `TAX-E2E-005` | read model non-fresh/failed | P0 | refreshing/stale/failed/missing 时显示诊断或禁用不安全写入，不把空 payload 当最终空结果。 |
| `TAX-E2E-006` | Workbench relation 与税金事实隔离 | P1 | Workbench confirm/withdraw 不得新增、删除或改变税金抵扣发票 item，也不得为 `tax_offset` 写 dirty/outbox；税金页面只随 canonical 发票或税务认证事实变化。 |
| `TAX-E2E-007` | 权限矩阵 | P1 | read-only 用户可读不可保存/导入；无权限或 session expired 不应调用受保护业务 API；写 API 仍由后端拒绝。 |
| `TAX-E2E-008` | 大数据、筛选、排序、横向滚动和视觉遮挡 | P2 | 大表格搜索/筛选/排序/滚动保持可用，按钮和弹窗不遮挡关键内容。 |

## 本地 deterministic E2E 之外的风险

- 真实税局认证 XLSX 大样本。
- 真实 OA 附件、ETC 和历史发票生命周期数据。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd `tax-offset` worker drain。
- 生产大数据 SQL p95/p99 和浏览器视觉性能。

这些风险必须由 staging/runtime smoke、后端 read model/worker 测试和生产只读审计承接。
