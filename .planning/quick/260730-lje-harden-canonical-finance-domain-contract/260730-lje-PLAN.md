---
quick_id: 260730-lje
status: in_progress
date: 2026-07-30
must_haves:
  truths:
    - "PostgreSQL 是 app 事实源；Settings 重置不再依赖空快照模拟删除。"
    - "outbox 只有一个可写重试计数字段，兼容列只能单向镜像。"
    - "canonical facts、正式配对关系、后台任务与 read-model manifest 的数据库/运行时合同一致。"
    - "直接 API 读取页面不重新引入页面 projection、Redis 一致性层或旧 fallback。"
  artifacts:
    - "显式、事务化、可回滚的 PostgreSQL Settings reset 边界及测试"
    - "outbox envelope/attempts 与 canonical facts/relations 的渐进式数据库约束"
    - "运行时 manifest、长期文档、测试合同与当前 4 个共享 read model 一致"
  key_links:
    - "route -> service -> repository/transaction，HTTP 层不拥有业务删除逻辑"
    - "writer -> job.outbox_events -> runtime queue repository，PostgreSQL durable queue 仍是事实源"
    - "canonical facts + app.workbench_pair_relations -> direct-read consumers/workbench"
---

# Quick Task 260730-lje：领域合同与持久化边界加固

## 范围

在不建设完整 DDD、不增加 Redis/read model、不改变页面业务口径的前提下，修复已经确认的持久化合同缺口：Settings PostgreSQL 重置、outbox attempts/envelope、canonical facts/正式关系的数据库形状、runtime manifest 与长期文档漂移；只删除已证明不可达的旧逻辑。

## Task 1：修复事实源与运行时合同

**Files:** Settings reset service/repository/wiring、runtime queue repository、read-model manifest、相应 migration。

**Action:**
- Settings reset 走显式 PostgreSQL 事务删除边界，返回真实删除数，重复执行幂等，任一步失败整体回滚。
- outbox 以 `attempts` 为唯一运行时写字段；`attempt_count` 只做单向兼容镜像。
- 用 `NOT VALID` 约束保护安全可证明的 envelope、canonical facts、正式关系和后台任务 JSON/数组/月份形状；不猜测未知状态枚举。
- manifest 登记实际运行的 auxiliary instance，保持 manifest/systemd/测试双向一致。

**Verify:** disposable PostgreSQL migration/reset/queue tests；manifest parity；现有 relation command 回归。

**Done:** 所有新合同均 fail-fast、可回滚、无第二事实源或兼容 fallback。

## Task 2：移除漂移并补齐测试/文档

**Files:** 受影响模块 boundary-io、架构/运行时/运维文档、目标测试。

**Action:**
- 删除只在旧 Mongo/空快照/read-model 叙述中存活的错误合同和已证明不可达代码。
- 文档统一为 PostgreSQL、4 个共享 read model、直接 API 页面与 Workbench active generation 的当前事实。
- 覆盖业务核心、service、API 合同、queue/read model、跨模块集成和现有功能回归；本次无 UI 行为变化，不新增 UI 测试。

**Verify:** targeted backend tests、migration tests、docs gate、`bash scripts/verify.sh lint`。

**Done:** 代码、测试、manifest、文档无双写/双读或旧路径污染。

## Task 3：发布与生产验证

**Files:** GSD summary/verification；不修改生产业务数据。

**Action:**
- 在 main 上原子提交并 push `origin/main`，用 `./scripts/deploy-oa.sh` 发布。
- 部署前后执行只读数据合同审计、migration/worker/queue/manifest/system audit 和相关 API 性能检查。
- 生产不执行 Settings reset；没有登记的可逆业务 fixture 时不做 confirm/withdraw 写入验证。

**Verify:** 精确 SHA、active release、migration 0129+、required workers、durable queue、只读 API/性能和 System Audit。

**Done:** 无一致性/回滚/权限/性能阻断；任何不满足项均停止发布并明确报告。

## 明确不做

- 不新建通用 Aggregate/DomainEvent/CandidateMatch/MoneyMovement 层。
- 不新增 Redis、RabbitMQ 状态事实源或页面 read model。
- 不物理删除仍需观察窗口、备份恢复证明或生产归零证据的历史表。
- 不执行无意义的全浏览器套件，也不以跳过/放宽断言掩盖失败。
