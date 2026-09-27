# 进项发票使用情况 Spec-first E2E Spec

本文件定义 `/input-invoice-usage` 页面在真实浏览器中的业务验收合同。测试必须证明进项发票使用、OA 反提、active relation 证据和 canonical direct-read 状态符合业务规格，而不是保护当前组件实现细节。

## 模块目标

进项发票使用情况页面用于查看进项发票、OA、支出流水、支付状态、关系详情和以发票反提 OA 工作流。页面读事实来自 canonical PostgreSQL query API，正式关系只来自 `app.workbench_pair_relations status='active'`；页面不能读取关联台候选表、页面 read model 或 Workbench projection。

## 用户角色

- `admin`：可读写，并可在设置页维护目标 OA 申请人凭据。
- `page_authorized`：可读取页面、创建 OA 草稿、确认 OA 已提交、维护支付规则和导出。
- 未获本页授权：不能进入页面或调用其读取、导出、OA 草稿和规则 API。
- forbidden/expired session：不能进入页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `IN-USAGE-E2E-001` | canonical rows/filter/table baseline | P0 | 页面一次加载 rows/summary/facets，展示发票、支付状态、OA、支出流水；首屏 page size 有界，筛选/排序不从当前页伪造全局选项。 |
| `IN-USAGE-E2E-002` | Workbench relation evidence access convergence | P0 | 未正式化自动匹配不能驱动已支付；Workbench confirm 或自动正式化写时零页面 fan-out，进入/刷新进项页后 linked OA/流水证据驱动已支付状态。 |
| `IN-USAGE-E2E-003` | OA reverse 无 OA 候选 | P0 | 候选仅含未关联 OA 的进项发票，按单张发票分页并按流水关联筛选；已占用候选计入总数但禁选；显式选择任一已关联 OA 项必须拒绝提交。 |
| `IN-USAGE-E2E-004` | OA reverse draft -> staged -> submitted history | P0 | 用户可从当前候选子集重新 preview、创建 OA 草稿；关闭确认弹窗后批次进入 `暂存` 且不展示 OA 草稿链接；用户确认 `我已在OA系统提交该草稿 / OA正在进行中` 后，历史只展示业务字段，不暴露 batch/draft/preview/internal status；创建草稿后刷新候选占用，状态确认后重跑当前页 normal GET。 |
| `IN-USAGE-E2E-005` | direct-read error/detail recovery | P0 | rows 或 relation detail 暂时失败时展示错误、不伪装空态、不自动 polling；用户刷新后恢复 canonical rows/detail。 |
| `IN-USAGE-E2E-006` | 多关系 `+N` 详情 | P1 | 同一 active relation component 下多 OA、流水或发票聚合为一行，`+N` 详情从 canonical detail API 展开。 |
| `IN-USAGE-E2E-007` | 页面权限矩阵 | P1 | 未获本页授权时不能渲染或调用页面 API；API 403 不被 UI 当作成功；005-only 凭据入口不泄漏给普通用户。 |
| `IN-USAGE-E2E-008` | 导出/download | P1 | 浏览器 download event 成功，字段、筛选、权限和 row-limit 反馈与 canonical contract 一致。 |
| `IN-USAGE-E2E-009` | 下游 tax/cost/OA pending/search 访问收敛 | P1 | relation、支付规则、OA reverse 或认证状态变化时本页写后重跑 canonical GET；其它 consumer 按自己的事实边界收敛。 |

| `IN-USAGE-E2E-010` | 关联统计与发票级候选 | P0 | 四类原生 Tabs 使用发票张数；反提 pool 与未关联 OA 同范围时身份集合相同；服务端分页与当前页选择不漏票。 |
| `IN-USAGE-E2E-011` | 规则 CRUD | P0 | 原生组件完成新增、删除、申请人修改；保存后回读且旧默认项不复活，失败/冲突显示错误，三个冲规则仅形成一个分类。 |

## 不属于本地 deterministic E2E 的风险

- 真实 OA 登录、公钥 RSA、OA 草稿页面打开和人工提交。
- 真实 PostgreSQL 大数据、历史半迁移、EXPLAIN 和锁等待。
- 下游仍使用 read model 的 consumer，其真实 RabbitMQ/Redis/systemd worker drain。
- 真实浏览器下载保存、大文件导出、iframe/cookie 和多账号 OA profile。
