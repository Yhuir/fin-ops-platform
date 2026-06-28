# Legacy Read Model 生产证据归档

日期：2026-06-26

> 2026-06-28 更新：本 runbook 已进入 legacy evidence archive。页面级 read model 正在下线，`read-model-scope-contract` helper、scope repair 脚本和 `tests.test_read_model_scope_contract` 已删除。后续生产验证应证明页面走 direct API/canonical facts，而不是证明 read model freshness 闭环。

本 runbook 仅保留为历史归档，不再作为当前 main 的发布或验收入口。当前生产验证应使用 direct API、canonical facts、durable outbox、worker heartbeat、App Health 和业务写后重读证据。

## 目标

- 证明页面读 API 走 direct API/canonical facts，不把 legacy stale/missing/failed/unavailable payload 当作当前页面结果。
- 证明写操作成功后返回 affected scopes/ids/months 或 true outbox side effects，并且页面通过 direct refetch 展示最终状态。
- 证明前端写后不依赖 operation barrier endpoint；legacy read model 只作为删除清单或历史诊断。
- 证明高行数 scoped read path 满足可接受延迟，并且不是无界全量扫描热路径。
- 证明生产样本验证后已恢复到操作前状态。

## 禁止事项

- 不把 Admin Token、cookie、DSN、私钥、生产 env、原始敏感 payload 写入 repo、`.planning/`、docs、日志、截图、shell history 或测试 fixture。
- 不通过数据库修改来制造验证样本、伪造 fresh、跳过业务写操作或修正非样本数据。
- 不直接写 legacy readiness 表来通过验证。
- 不删除 current-effective outbox blocker 来制造“收敛”。
- 不对业务事实表执行无界 update/delete/truncate。

## 前置门禁

1. main 本地和 `origin/main` 必须一致，并且本地工作区干净。
2. 发布前必须已经跑过本地 L3 验证：

```bash
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_manifest tests.test_runtime_worker_registry
PYTHONPATH=backend/src python3 -m unittest -q tests.test_read_model_freshness tests.test_read_model_refresh_gateway
PYTHONPATH=backend/src python3 -m unittest -q tests.test_runtime_worker_read_model_refresh_scopes tests.test_app_status_overview_service
PYTHONPATH=backend/src python3 -m unittest -q tests.test_write_operation_slo_audit tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate
bash scripts/verify.sh docs
npm run build
git diff --check
```

3. Admin Token 只能来自安全弹窗、系统级 secret store 或当前进程临时环境变量；不得从普通聊天粘贴到 transcript。
4. 生产 SSH/root 和 deploy 权限可用；如果不可用，只能记录 PSCIP-L3 完成和 PSCIP-L4 证据缺口。

## 发布

发布入口固定为：

```bash
./scripts/deploy-oa.sh
```

发布前记录：

- 本地 commit。
- 备份分支。
- 生产当前 release commit。
- rollback release。

发布后先执行只读检查，不做修复：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_worker_manifest --json
```

旧 `read-model-scope-contract` 发布 helper 已删除；不得用页面 read-model scope repair 作为发布证据或恢复手段。

## 只读证据

对每个受影响页面或后台任务采集：

- app health / readiness status。
- outbox pending/processing/failed/dead-letter 状态。
- worker heartbeat 和 required worker 状态。
- direct API status/latency/row count。
- schema/source version proof。
- scoped query latency 或 EXPLAIN evidence。

证据只记录 metadata，例如 route/module、scope key、status、latency、row count、job id、event id、timestamp；不记录原始敏感业务 payload。

## 写操作样本

样本选择原则：

- 每个核心页面至少一个低风险写后读闭环样本，或明确说明该页面没有独立写操作。
- 优先选择业务上可逆的样本。
- 每个样本 apply 前必须有 restore plan。
- 样本操作必须通过业务 API、业务 UI 或已有业务 command 执行，不用数据库修改执行验证动作。

每个样本记录：

| 字段 | 要求 |
| --- | --- |
| sample_id | 可追踪但不暴露敏感内容 |
| page/module | 页面或模块 |
| operation | 业务操作名称 |
| before snapshot | 操作前最小必要状态 |
| expected targets | affected ids/months/scopes 或 direct API route |
| apply method | API/UI/command |
| observed outbox | event/scope metadata |
| observed worker | worker/status/latency metadata |
| observed page result | API/page direct payload metadata |
| restore method | business inverse 或 bounded DB restore |
| post-restore proof | canonical state + direct API result |

## 恢复策略

恢复优先级：

1. 业务撤回、取消、恢复、重新确认等业务 inverse。
2. 已有业务 repair/recovery command。
3. 仅当没有业务恢复路径时，使用预批准的 bounded DB restore protocol。

### Bounded DB Restore Protocol

只有恢复验证样本到操作前状态时允许使用，且必须满足全部条件：

1. operation-before snapshot 已采集，包含恢复所需的最小列和值。
2. exact predicate 可证明只命中本样本行，例如主键、版本、tenant、业务 ID 全部匹配。
3. 单事务执行，事务内先校验命中行数，再 update/insert/delete。
4. 写入审计记录或保留命令输出，说明 reason、sample_id、predicate、affected row count。
5. post-restore verification 通过：业务事实、read model dirty/outbox、页面 direct read API 均回到期望状态。

如果无法建立 operation-before snapshot、exact predicate、transaction safety 或 post-restore verification，必须 hard stop；不能扩大 DB 修改范围。

## 性能证据

高行数页面至少记录一种证据：

- scoped query latency p95/p99。
- `EXPLAIN (ANALYZE, BUFFERS)` 或等价 query plan。
- SLO smoke 工具输出。

重点证明热路径按 scope/partition 读取，不扫描无界 canonical facts、全量 JSON snapshot 或 legacy collection。

## 关闭条件

某个 read model 只有同时满足以下条件，才能标记 PSCIP-L4：

- manifest、scope policy、worker registry、App Status registry 和 docs 一致。
- 读 API fresh/status 合同通过生产或等价真实 runtime 验证。
- 写样本能从业务操作追踪到 dirty/outbox、worker、projection、readiness 和页面 direct read 结果。
- 样本恢复完成并验证。
- 性能证据通过。
- 旧链路已删除，或有 guard 证明 normal production path 不可达且有删除条件。

## Hard Stop

遇到以下情况停止并记录缺口：

- 无安全 token 输入或安全 secret source。
- main 不能安全发布或回滚路径不明确。
- 生产 SSH/root/DB 访问不可用且没有等价验证入口。
- 样本恢复缺少 operation-before snapshot、exact predicate、transaction safety 或 post-restore verification。
- current-effective dirty/outbox blocker 无法解释。
- worker/readiness 不收敛且继续验证会污染样本。
- 需要无界或破坏性数据库操作才能继续。
