# Deploy 模块边界与 I/O

日期：2026-08-28

## 输入

- 已提交并推送的 exact `main` commit。
- 本地验证通过的 backend/frontend/docs 与 production frontend build。
- SSH/server/env、独立 migrator、runtime secrets 和当前 release fingerprint。

## 输出

- `/opt/fin-ops/releases/<release>` immutable payload。
- 原子 active symlink、API service、四个 registry worker。
- Migration/evidence/checkpoint/health/SLO 结果。

## 边界

- `scripts/deploy-oa.sh` 负责 build/upload/activate orchestration。
- `finops-deploy-control` 负责 root 级 maintenance、migration、runtime assets、checkpoints。
- `finops-ensure-runtime-workers` 只从 registry 派生 worker；未登记实例 stop/disable。
- Preflight 的只读 closure 在本次 schema plan 证明两版 schema 完全相同且无待迁移项时加载候选代码；其余情况使用 active 代码。Domain、worker inventory 与队列健康仍归 active release，T+0/T+30 使用激活后的版本。该选择不放宽任何失败条件，不写业务数据。
- 不开放任意 shell/SQL，不修改 OA 源码，不删除主数据库，不恢复旧 projection runtime。

## Forward-only

Migration 0149/0160 退役旧 schema。执行后 previous release 若依赖旧对象则不可自动恢复；Migration 0161
会入队正式关联关系规则收敛任务，其正确消费依赖候选版本按 `relation_mode` 选择正式关系，旧 release 不得消费该任务。
Migration 0165 会删除旧账户权限 JSON 字段并切换 OA 角色，旧 release 无法继续读取或写入权限合同。
因此以上 migration 均为 forward-only：候选失败保持 maintenance 并 forward repair。前端-only release 仍可按
immutable fingerprint 回滚。

## 候选事件升级互锁

- Preflight 默认继续要求 durable queue 清零。唯一例外是：pending 行全部属于 exact candidate 新增、当前
  release 未登记的 event type，且按 `event_type + status` 全量聚合后的数量与 queue pending 总数完全一致。
- 该例外只允许 `pending`；混入 current-release 事件、`processing`、`failed`、`dead_lettered` 或无法全量对账
  都必须阻断。T+0/T+30 与 stability gate 不继承例外，候选 worker 启动后必须真正清空队列。
- 该边界用于打破“迁移先入队、旧 worker 不认识新事件”的升级互锁，不允许删除 queue 行或通用跳过预检。

## 验证

现金前后端发布已获用户2026-09-07最新明确授权，分支`codex/cash-ledger`，不合并main。前端实现并本地验证后发布。使用同库、同一App登录账号，不安装cash专用env或创建账号；追加0167为已存在的`fin_ops_app_runtime`授予cash十表必要DML，保留0166及旧迁移不变。步骤见[现金部署](../../operations/cash-module-deployment.md)。生产不插入试验现金、不创建受限角色、不改OA状态；既有正式发布验证保留。

Nginx示例采用归一化`$uri`条件access_log，精确排除三种cash API前缀；普通/近似cash-back路径日志不变。正式配置只改这项map和站点日志条件，经原配置对比和nginx语法验证后reload；不改变OA代理/TLS/应用路由。

`tests/test_deploy_oa_script.py`、`tests/test_deploy_runtime_examples.py`、
`tests/test_read_model_runtime_removal.py` 与生产 T+0/T+30 evidence。

## 流水拆分发布（2026-09-23）

0178/0179 纳入既有 forward-only 清单。新增固定运维入口 `external-turnover-cost-revoke <release> [--apply --operator <actor>]`，默认只读预览，经领域 owner 同事务撤销历史外部分配；执行后重启刷新进程镜像。`bank-transaction-split-smoke <release>` 仅创建事务内测试自有数据，100 次检查后强制回滚并校验无残留。两者不接受任意 SQL/shell；不创建或删除主数据库。输入/输出与性能范围见 [拆分验证](../../dev/bank-transaction-splits.md)。

0180 增量保存拆分分类实例，已退役的统一成本确认标记通过 `retire_bank_split_confirmation_flags` owner 工具预览/事务清理，不更改关系版本或成员，不创建数据库备份。既有子项缺失的第三层按已核实原确认事实经正式 PUT 修复；不在迁移 SQL 推断。

0180 的完整拆分分类实例也纳入既有 forward-only 发布清单：旧 writer 只修改 code/金额，不能同步更新完整实例，回切后可能留下错配归属。验证失败保留 maintenance 向前修复；不新增审核门禁或数据库备份。


0181 cost decision_mode 为 forward-only：退役人工决定后旧 writer 忽略模式会重新启用旧载荷。先发布理解模式的版本，再运行成本 owner 的 automatic migration CLI。数据恢复要求模式/连续版本/当前事实校验；不能回切忽略模式的代码。生产不创建全库备份、不删除主数据库。
