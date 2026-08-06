# 免 OA 流水批量处理模块边界与 I/O

日期：2026-08-06

## 模块状态

- 状态：retained legacy canonical API boundary；read-model runtime 已退休。
- 当前边界可信度：high。
- 删除条件：生产数据、工具和回归测试都不再需要 `relation_mode=no_oa_bank_batch` 后，另立迁移计划；不得让当前 bank-flow 页面回退到本模块。

## 职责与输入

- Route 只处理 `/api/no-oa-bank-batches/*` HTTP mapping、权限和 payload 校验。
- Application service 负责 no-OA batch submit/withdraw/bulk submit、canonical relation command 与原子 mutation persistence。
- 实际消费者包括 server 注册的 legacy HTTP routes、BankFlow selection command 和 Workbench internal-transfer command adapter；这些消费者只调用 canonical application boundary，不使用旧 no-OA projection。
- 写入输入是显式 batch/case identity、actor、version/reason 与精确 affected months；不接受下游 read-model target planner。
- 列表查询按请求 month/filter/page 调用 `refresh_batches(apply_relation_repairs=False)`，再从 canonical batch service 读取；GET 不访问 freshness gateway、dirty scope、outbox、readiness 或 Redis。

## 输出与持久化 I/O

- 普通写只提交 no-OA batch facts、relation/history/audit 与信息性 affected scopes。
- `freshness_targets`、`operation_barrier_targets` 为空；旧 `workbench_rebuild_queued` 响应字段和 `after_mutation(...)` callback 已删除。
- `persist_mutation(...)` 只调用 `save_no_oa_bank_batch_mutation(...)`，保存 scoped pair relation 与 no-OA batch snapshot；禁止同步生成/写入 Workbench read-model snapshot。
- 列表响应只返回 canonical `batches/total/page/page_size/filters`；不返回 `read_model_status`、`refresh_enqueued`、source versions 或 job/barrier target。
- `no_oa_bank_batch.read_model.refresh`、worker registration/env、repository port 和 projection service 已删除；历史表与 runtime rows 只供上一 release 回滚。

## 依赖方向

- 允许依赖：Workbench relation command/snapshot port、no-OA canonical state store、权限与审计。
- 禁止：调用 bank-flow route/service 作为 fallback；写 Workbench read model；普通写产生页面 dirty/outbox；无月份 fallback `all`。

## 文件范围与验证

- Backend：`routes_no_oa_bank_batches.py`、`no_oa_bank_batch_application_service.py`、共享中性 batch core。
- Persistence：`save_no_oa_bank_batch_mutation(...)`、canonical no-OA PostgreSQL tables。
- Tests：`tests/test_no_oa_bank_batch*.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`。
