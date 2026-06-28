# 税金抵扣 Spec-first E2E Spec

本文件定义 `/tax-offset` 页面的浏览器级验收合同。Spec 以真实业务流程为准，代码只用于定位 route、API、selector 和 mock。

## 模块目标

税金抵扣页必须让用户基于 direct tax offset API 查看销项税额、进项认证计划、已认证结果，完成试算、保存计划和已认证发票导入。关系事实、发票导入、ETC、OA 附件等上游变化必须通过后端 read boundary 进入页面，不能由页面本地推断。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `TAX-E2E-001` | 首屏读取 direct tax offset payload | P0 | 进入 `/tax-offset` 后显示当前月份销项票、进项计划、统计卡和结果面板；页面 payload 不包含 `read_model_status` / scope key freshness 字段，计划保存只使用 direct source versions（存在时）和幂等 key 做页面侧并发保护。 |
| `TAX-E2E-002` | 用户取消/恢复进项计划并重新试算 | P0 | 勾选变化后调用 calculate API，统计卡和结果面板按后端返回更新，页面不自行重算业务规则。 |
| `TAX-E2E-003` | 保存税金抵扣计划 | P0 | 保存时提交 selected ids、direct source versions（存在时）和 idempotency key；成功后直接刷新当前月份页面且不请求 operation barrier；stale/conflict 不能伪成功。 |
| `TAX-E2E-004` | 已认证发票导入 preview/confirm | P0 | 选择 XLSX 后可预览识别结果；确认导入后直接刷新税金页和已认证结果 drawer 且不请求 operation barrier，显示新增已认证记录。 |
| `TAX-E2E-005` | direct empty payload | P0 | 页面级刷新诊断、自动重试或保存禁用不由 read model 字段驱动；空 direct payload 显示真实空态。 |
| `TAX-E2E-006` | Workbench relation fan-out 到税金抵扣 | P1 | Workbench confirm 后，税金抵扣页重新请求 `/api/tax-offset`，展示 relation 影响后的进项计划行，且不误报同步错误。 |
| `TAX-E2E-007` | 权限矩阵 | P1 | read-only 用户可读不可保存/导入；无权限或 session expired 不应调用受保护业务 API；写 API 仍由后端拒绝。 |
| `TAX-E2E-008` | 大数据、筛选、排序、横向滚动和视觉遮挡 | P2 | 大表格搜索/筛选/排序/滚动保持可用，按钮和弹窗不遮挡关键内容。 |

## 本地 deterministic E2E 之外的风险

- 真实税局认证 XLSX 大样本。
- 真实 OA 附件、ETC 和历史发票生命周期数据。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd 后台任务和 tax offset direct API 收敛。
- 生产大数据 SQL p95/p99 和浏览器视觉性能。

这些风险必须由 staging/runtime smoke、后端 derived data/worker 测试和生产只读审计承接。
