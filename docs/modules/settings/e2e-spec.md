# 设置 Spec-first E2E Spec

本文件定义 `/settings` 页面在真实浏览器中的业务验收合同。测试必须保护平台配置、权限、数据重置、OA 凭据、项目状态边界、read model/worker 边界和下游页面一致性，而不是保护当前 React 组件实现细节。

## 模块目标

设置页面维护平台级配置事实。普通 settings 写入 `ApplicationStateStore`，OA 申请人凭据使用独立 secret repository，数据重置通过受保护后台 job 执行。任何设置变更都不能让旧 read model/cache 被当作 fresh，也不能绕过权限、审计、dirty scope 或 worker/freshness 边界。

## 用户角色

- `admin`：可读取和维护所有设置、OA 凭据、项目状态、访问控制和数据重置。
- `full_access`：可读取和维护普通业务设置，但不能执行 admin-only 高风险动作。
- `read_export_only`：可读取允许的配置视图，不得触发 settings mutation、OA 凭据维护、数据重置或 OA manual import mutation。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `SETTINGS-E2E-001` | 页面 ready 和配置边界 | P0 | 进入 `/settings` 后显示设置标题、分类树和可访问 section；普通 settings payload 不包含 OA 密码、token、密文或银行自动标签写字段。 |
| `SETTINGS-E2E-002` | 项目状态与历史成本隔离 | P0 | 用户把项目标记完成并保存后，请求必须包含 `completed_project_ids` 且零页面 fan-out；项目状态只影响设置/项目管理，不得删除已发生并满足 OA 完成条件的历史成本。成本统计请求不再携带 `project_scope`，页面也不暴露项目范围切换 UI。 |
| `SETTINGS-E2E-003` | 数据重置双确认和 job polling | P0 | admin 选择数据重置目标后必须先确认影响，再输入 OA 密码；POST job 返回 202 后页面显示进度、轮询 job、重新读取 settings 并显示成功反馈；不得出现隐藏浏览器错误或未预期 dialog。 |
| `SETTINGS-E2E-004` | 数据重置安全边界 | P0 | data reset 必须 admin/password gate、protected targets、active job reentry、并发 409、失败不清数据、不泄露密码；重置后旧 read model/cache 不得伪装 fresh。 |
| `SETTINGS-E2E-005` | OA 申请人凭据独立事实源 | P0 | admin 可维护 OA 申请人凭据；settings GET/POST 和凭据列表不得回显密码、token 或密文；目标 OA token provider 只通过 credential service 取密。 |
| `SETTINGS-E2E-006` | 业务规则保存和银行标签写边界 | P0 | 待找发票规则保存必须递增版本并触发 downstream lifecycle；`/api/workbench/settings` 携带 `bank_transaction_tags` 必须失败，银行自动标签写入只能走银行明细 API。 |
| `SETTINGS-E2E-007` | 权限矩阵和零 durable mutation | P0 | `read_export_only` 不显示或禁用 settings 高风险写入口，直接调用 mutation API 返回拒绝且不触发下游写服务；保留 OA roles/`finops:app:view` 的 `YNSYLP006` 仍在 direct `/fin-ops/` 与 protected API 边界 denied；forbidden/expired session 零 protected API 成功。 |
| `SETTINGS-E2E-008` | OA manual import mutation 权限 | P0 | OA manual import refresh/create/delete 必须使用 session actor 和 mutation gate；body actor 伪造不能绕过只读权限。 |
| `SETTINGS-E2E-009` | App Status/read model/worker 可见性 | P1 | settings 变更和 data reset 引起的 dirty/readiness/job 状态必须能被 App Status/App Health 或下游页面诊断；页面不能只靠本地事件宣称 fresh。 |
| `SETTINGS-E2E-010` | 真实基础设施 data reset 和 worker drain | P1 | 真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储环境下，data reset、项目范围变更、规则保存和 OA 凭据使用后，相关 read model、worker、cache 和页面最终收敛；该项必须在 staging/runtime smoke 验证。 |
| `SETTINGS-E2E-011` | canonical ACL 四层级与恢复 | P0 | 当前 17-route registry 在 admin/full/read/denied 下保持精确可达性；AppHealth、OA credentials、data reset 仅 admin。管理员使用专用 versioned PUT 增加账号、切换 session 验证 tier，finally 恢复空 accounts 后同一身份立即 denied。 |
| `SETTINGS-E2E-012` | ACL 失败状态与 I/O 预算 | P0 | stale version 保留 draft；OA target、PG persistence、compensation/inconsistent 分别显示 409/502/503 且不伪报成功；generic save 零 OA、no-op 零 PG/audit/OA、evaluator 每次最多一次 snapshot，且无 cache/outbox/dirty/read-model/worker 新路径。 |

## T0 ACL Browser/API contract

- full-access 页面不显示管理控件，同时直接 `POST /api/workbench/settings` 注入任一 ACL key 必须 400，直接 `PUT /api/workbench/settings/access-control` 必须 403。
- admin 独立加载/保存 access-control，`YNSYLP005` 行只读；保存后用新 session GET `/api/session/me` 验证目标 tier。
- 普通 settings save、Workbench 列布局和 pending rules 请求体不允许出现 ACL family。
- 13-11 deterministic Browser matrix 必须覆盖 direct URL/API、精确 17-route、admin-only control plane 和 ACL restore；唯一后端 inventory owner负责机械 I/O/topology 预算，不在 E2E 新建 scanner。
- 生产 post-deploy 使用专用初始 denied bearer，按 full→read→denied 验证并 finally 恢复；fresh OA router/menu 只由 13-05 production checkpoint 证明，token、用户名明文不进入 artifact。本地 mock 不能替代该结论。

## 不属于本地 deterministic E2E 的风险

- 真实生产数据重置的备份、PITR/恢复、worker pause/drain、Redis/cache 清理和 reset 后全页面 smoke。
- 真实 OA 登录、RSA/token、OA 草稿、OA iframe/session 和目标申请人权限。
- 真实 PostgreSQL pgcrypto key、历史 settings payload、半迁移数据和大规模 state store。
- 真实 RabbitMQ/Redis/systemd worker drain、长队列重试、Nginx/对象存储和生产网络抖动。
- 所有下游页面在 settings fan-out 后的最终 UI 刷新由下游页面 Spec-first E2E 和 staging smoke 共同证明。
