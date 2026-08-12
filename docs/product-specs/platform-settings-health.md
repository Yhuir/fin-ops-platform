# 平台设置、权限与健康状态

本文维护设置页、账户权限、项目状态、数据重置入口、App Health 和后台任务可见性的当前业务口径。

## 设置与权限

- 设置页维护其他账户的访问级别、项目状态、业务规则和运行配置。唯一管理员 `YNSYLP005` 不属于可编辑业务数据，也不能通过 APP 轮换。
- 权限影响页面可见性、按钮可用性、API 写入、数据重置和运维修复动作。
- 权限和审计属于 command/service 边界，不做 read model 分发。
- `/settings` 的“访问账户权限”是唯一人工 ACL 输入，使用独立的 admin-only ACL API；普通设置保存与 ACL 加载/保存完全分离。管理员只能把其他 OA 账号设为 `full_access`、`read_export_only`，或从列表删除表示 `denied`。
- 除 `YNSYLP005` 外，canonical Settings ACL `accounts` 是 APP 访问级别的唯一业务事实源；缺席即 denied。OA 只认证用户名，它的 permission/role（包括 `finops:app:view`）以及退役的 APP admission env 都不能 grant APP 访问。
- 用户名以 casefold key 比较并保留 OA `sys_user.user_name` canonical spelling；等值碰撞在写入和 OA I/O 前 fail closed。ACL 删除在下一次 APP session/API 判断立即生效，不等待 OA identity cache。
- ACL semantic no-op 不写 PostgreSQL、不写 audit、不调用 OA；真实变化使用版本冲突保护并同步 OA 三类角色，失败按补偿合同返回明确错误。
- `finops:app:view` 只定位 OA 菜单；OA 仅接收 canonical ACL 到 `finops_read_export` / `finops_full_access` / `finops_admin` 三类专用角色的严格投影。历史非专用菜单绑定由部署做 exact-target 清理/回滚，不属于页面写入。
- 该 ACL 链路不新增 read model、worker、dirty scope、Redis 或第二缓存；自动化证据锁定每次非管理员判断最多一次 snapshot 读取、普通设置保存零 OA I/O 和 ACL no-op 零外部 I/O；生产延迟只记录实测，不在本文预告通过。
- 规则配置变化如果影响业务判定，必须触发对应 dirty scope。

## 数据重置入口

数据重置是高风险操作：

- 需要权限、确认、审计、影响范围和回滚说明。
- 必须考虑 PostgreSQL 数据、对象存储、read model、Redis 缓存和后台任务。
- 重置后不能让页面展示旧缓存或旧 read model 为 fresh。

## App Health

App Health 用于展示运行状态和后台任务：

- read model freshness/stale/refreshing。
- durable queue、worker heartbeat、job failure。
- cache 状态、SSE/轮询状态和必要的重试入口。
- 关联台 generation 统计和关键页面可用性。

## Global Runtime Status Plane

左上角 App Status Icon 使用全局运行状态平面，不读取当前页面组件状态，也不随路由切换变化。全局状态只由后端 runtime facts 变化驱动：后台任务、read model freshness、dirty scope、outbox、worker heartbeat、依赖状态、会话和权限。

颜色语义：

- 绿色：所有页面数据域 ready/loaded/synced；登记的 read model 由 `read_model.app_status_readiness` 证明为 `fresh`，direct canonical 页面由 normal GET/Audit 与依赖状态证明可读；同时无 queued/running/attention 后台任务且关键依赖正常。
- 黄色：任一页面数据域 loading/refreshing/stale，任一后台任务 queued/running/failed/partial_success 未确认，或存在非阻断运行告警。
- 红色：会话失效、权限不可用、App Health/API 不可达、关键依赖失败，或关键 read model failed/unavailable。

hover 面板是只读全局状态面板，展示后台任务进度、所有页面数据域状态、最后更新时间和跳转入口。它不执行重试、确认、取消或修复动作；这些动作仍在后台任务详情或 App Health 运维页完成。

read model 空业务结果可以是绿色，但必须有 readiness scope 记录证明该 scope 已加载并 fresh；不能因为 projection 表为空、dirty scope 为空或 worker 没有报错就推断为 ready。schema/source version mismatch、首次缺失 readiness、readiness reader unavailable 都必须显式进入黄色或红色。

## 后台任务

后台任务必须可观测、可重试、可定位失败原因。页面只展示任务状态和用户可执行动作，不能替代 worker/queue 的事实源。

## 相关文档

- Runtime：`../app-architecture/runtime-and-ownership.md`
- 运维治理：`../operations/runtime-worker-governance.md`
- 数据安全：`../operations/data-safety.md`
