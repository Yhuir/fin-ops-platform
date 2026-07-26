# 进项发票使用情况 Spec-first E2E Spec

本文件定义 `/input-invoice-usage` 页面在真实浏览器中的业务验收合同。测试必须证明进项发票使用、OA 反提、active relation 证据和 canonical direct-read 状态符合业务规格，而不是保护当前组件实现细节。

## 模块目标

进项发票使用情况页面用于查看进项发票、OA、支出流水、支付状态、关系详情和以发票反提 OA 工作流。页面读事实来自 canonical PostgreSQL query API，正式关系只来自 `app.workbench_pair_relations status='active'`；页面不能读取关联台候选表、页面 read model 或 Workbench projection。

## 用户角色

- `admin`：可读写，并可在设置页维护目标 OA 申请人凭据。
- `full_access`：可读取页面、创建 OA 草稿、确认 OA 已提交、维护支付规则和导出。
- `read_export_only`：可查看/导出，不能创建 OA 草稿或保存规则。
- forbidden/expired session：不能进入页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `IN-USAGE-E2E-001` | canonical rows/filter/table baseline | P0 | 页面一次加载 rows/summary/facets，展示发票、支付状态、OA、支出流水；首屏 page size 有界，筛选/排序不从当前页伪造全局选项。 |
| `IN-USAGE-E2E-002` | Workbench relation evidence access convergence | P0 | 未正式化自动匹配不能驱动已支付；Workbench confirm 或自动正式化写时零页面 fan-out，进入/刷新进项页后 linked OA/流水证据驱动已支付状态。 |
| `IN-USAGE-E2E-003` | OA reverse preview 二态 | P0 | 反提 OA 预览中 `unlinked` 发票可勾选；`linked` 显示 `已关联oa` 且不可勾选；历史 `candidate` 兼容值归入 `未关联oa`，不展示独立候选 OA 筛选。 |
| `IN-USAGE-E2E-004` | OA reverse draft -> staged -> submitted history | P0 | 用户可从当前候选子集重新 preview、创建 OA 草稿；关闭确认弹窗后批次进入 `暂存` 且不展示 OA 草稿链接；用户确认 `我已在OA系统提交该草稿 / OA正在进行中` 后，历史只展示业务字段，不暴露 batch/draft/preview/internal status；这些本地状态动作不刷新 rows，真正 relation 写后也只重跑当前页 normal GET。 |
| `IN-USAGE-E2E-005` | direct-read error/detail recovery | P0 | rows 或 relation detail 暂时失败时展示错误、不伪装空态、不自动 polling；用户刷新后恢复 canonical rows/detail。 |
| `IN-USAGE-E2E-006` | 多关系 `+N` 详情 | P1 | 同一 active relation component 下多 OA、流水或发票聚合为一行，`+N` 详情从 canonical detail API 展开。 |
| `IN-USAGE-E2E-007` | 权限矩阵 | P1 | `read_export_only` 看不到或不能触发写入口；API 403 不被 UI 当作成功；admin-only 凭据入口不泄漏给普通用户。 |
| `IN-USAGE-E2E-008` | 导出/download | P1 | 浏览器 download event 成功，字段、筛选、权限和 row-limit 反馈与 canonical contract 一致。 |
| `IN-USAGE-E2E-009` | 下游 tax/cost/OA pending/search 访问收敛 | P1 | relation、支付规则、OA reverse 或认证状态变化时本页写后重跑 canonical GET；其它 consumer 按自己的事实边界收敛。 |

## 不属于本地 deterministic E2E 的风险

- 真实 OA 登录、公钥 RSA、OA 草稿页面打开和人工提交。
- 真实 PostgreSQL 大数据、历史半迁移、EXPLAIN 和锁等待。
- 下游仍使用 read model 的 consumer，其真实 RabbitMQ/Redis/systemd worker drain。
- 真实浏览器下载保存、大文件导出、iframe/cookie 和多账号 OA profile。
