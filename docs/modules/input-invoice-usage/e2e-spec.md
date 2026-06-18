# 进项发票使用情况 Spec-first E2E Spec

本文件定义 `/input-invoice-usage` 页面在真实浏览器中的业务验收合同。测试必须证明进项发票使用、OA 反提、关系证据和 read model 状态符合业务规格，而不是保护当前组件实现细节。

## 模块目标

进项发票使用情况页面用于查看进项发票、OA、支出流水、支付状态、关系详情和以发票反提 OA 工作流。页面读事实来自 `input_invoice_usage` SQL read model，OA/流水/发票关系证据来自 `WorkbenchRelationReadFacade` 分发的 `workbench_relation`；页面不能直接读取关联台候选表，也不能把 stale/missing read model 伪装成 fresh。

## 用户角色

- `admin`：可读写，并可在设置页维护目标 OA 申请人凭据。
- `full_access`：可读取页面、创建 OA 草稿、确认 OA 已提交、维护支付规则和导出。
- `read_export_only`：可查看/导出，不能创建 OA 草稿或保存规则。
- forbidden/expired session：不能进入页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `IN-USAGE-E2E-001` | fresh rows/filter/table baseline | P0 | 页面加载 fresh rows，展示发票、支付状态、OA、支出流水；首屏 page size 有界，筛选/排序不从当前页伪造全局选项。 |
| `IN-USAGE-E2E-002` | Workbench relation evidence fan-out | P0 | 关联台 candidate relation 只显示 OA/流水候选证据，支付状态保持待处理；Workbench confirm 后页面重新读取 rows，linked OA/流水证据驱动已支付状态。 |
| `IN-USAGE-E2E-003` | OA reverse preview 三态 | P0 | 反提 OA 预览中 `unlinked` 发票可勾选；`linked` 显示 `已关联oa` 且不可勾选；`candidate` 显示 `候选oa` 且不可勾选，两者都不能进入创建草稿 payload。 |
| `IN-USAGE-E2E-004` | OA reverse draft -> staged -> submitted history | P0 | 用户可从当前候选子集重新 preview、创建 OA 草稿；关闭确认弹窗后批次进入 `暂存` 且不展示 OA 草稿链接；用户确认 `我已在OA系统提交该草稿 / OA正在进行中` 后，历史只展示业务字段，不暴露 batch/draft/preview/internal status。 |
| `IN-USAGE-E2E-005` | read model refreshing/stale/detail | P0 | rows 和 `/rows/{row_id}/relation-details` 在 missing/stale/source mismatch 时展示刷新/诊断，不触发全量 live rebuild 或假空态。 |
| `IN-USAGE-E2E-006` | 多关系 `+N` 详情 | P1 | 同一 linked/candidate relation 下多 OA、流水或发票聚合为一行，`+N` 详情从单行 read model payload 展开。 |
| `IN-USAGE-E2E-007` | 权限矩阵 | P1 | `read_export_only` 看不到或不能触发写入口；API 403 不被 UI 当作成功；admin-only 凭据入口不泄漏给普通用户。 |
| `IN-USAGE-E2E-008` | 导出/download | P1 | 浏览器 download event 成功，字段、筛选、权限、row-limit 和 refreshing 反馈与后端 contract 一致。 |
| `IN-USAGE-E2E-009` | 下游 tax/cost/OA pending/search fan-out | P1 | relation、支付规则、OA reverse 或认证状态变化后，下游页面通过各自 read model 展示一致结果。 |

## 不属于本地 deterministic E2E 的风险

- 真实 OA 登录、公钥 RSA、OA 草稿页面打开和人工提交。
- 真实 PostgreSQL 大数据、历史半迁移、EXPLAIN 和锁等待。
- 真实 RabbitMQ/Redis/systemd worker drain。
- 真实浏览器下载保存、大文件导出、iframe/cookie 和多账号 OA profile。
