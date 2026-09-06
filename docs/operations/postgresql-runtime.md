# PostgreSQL 运行边界

日期：2026-08-15

## Schema ownership

- `app`：canonical business facts、settings、active relations、domain scopes。
- `job`：background jobs、outbox、attempt、heartbeat。
- `audit`：durable operation/external evidence。
- `cash`：现金模块独立事实/配置（migration0166）；普通业务、audit/job、reset与页面查询不读写。现金只读OA项目资料，不读取普通财务事实。生产是否开通以[现金实施记录](../dev/cash-module-implementation-plan.md)为准。
- `public`/migration metadata：schema version 与扩展。

旧 projection schema 已由 migration 0149 删除，不属于当前 runtime。

## 连接角色

| Role | 权限 |
| --- | --- |
| API runtime | 业务 service/repository 所需最小读写 |
| Worker runtime | 明确 job/domain handler 所需最小读写 |
| Migrator | migration DDL；不作为 API/worker 凭据 |
| Audit/smoke | 只读，或仅允许固定可逆探针 |
| Cash API runtime | 同数据库cash专属十表DML；无DDL、角色继承、普通财务读取或全局审计写入 |

API/worker 通过同一受控 common/secrets env 取得 DSN，但角色可分离。不得把 migrator DSN 打印、提交或交给
浏览器。连接池必须有 acquire timeout、max waiting、idle/lifetime 与指标。

现金凭据为例外：只由API加载root0600的`/etc/fin-ops/fin-ops.cash.env`，不进入共用worker secrets；独立pool最大2/等待8、statement timeout5秒。缺配置明确503，禁止用普通DSN替代。角色创建/双向权限实际验证见[现金首次授权](cash-module-deployment.md)。这仍是同一个主数据库，不是第二数据库。

## Query contract

- 页面组合读使用短 `REPEATABLE READ READ ONLY` snapshot。
- SQL set-based、分页有界、batch hydration、明确 statement timeout。
- 生产 API 不加载 full snapshot，不读 local pickle/state JSON/App Mongo fallback。
- 普通 GET 不写 queue；普通 mutation 只写 canonical facts/audit/idempotency 与明确 domain job。

## Queue retention

通用 outbox/history retention 只清理稳定完成态，并保留每 event type 的近期证据。pending、processing、failed、
dead-lettered 和 active lease 不得清理。普通 VACUUM 只使空间可复用；需要重写/归还文件系统空间的操作必须在
独立维护窗口评估锁、额外磁盘和回滚。

## Backup 与恢复

- 主数据库 backup/restore 由既有 PostgreSQL 运维策略管理，不由应用部署脚本临时删除或替换。
- Migration 0149 是 forward-only；执行后禁止回滚到依赖旧 schema 的 release。
- 本次退役不创建 task-specific DB backup。若独立 repair 创建 recovery artifact，验证后按工具合同删除 artifact；
  禁止删除主数据库。

## 验证

- migration checksum/schema tests；
- `/health/ready`、pool/connection/query metrics；
- canonical page/system audit；
- authenticated HTTP p95/p99；
- worker/PostgreSQL outbox closure；
- 退役事件和 schema 的负向审计。
