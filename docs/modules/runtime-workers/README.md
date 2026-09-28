# 后台任务

入口：`独立 worker 进程`。

执行需要恢复、租约和有限重试的领域任务；页面查询在请求内完成。

## 边界与 I/O

输入：已登记事件、直接 import job 或匹配 scope，带 tenant/identity/version/actor。输出：领域事实、任务结果、attempt、heartbeat 与结构化失败。

## 当前业务约定

- registry 精确登记四个实例：oa-sync 消费 oa.sync/oa.payment_status.reconcile；workbench-matching 消费 matching dirty scopes；import 直接领取 job.import_jobs；settings-maintenance 消费 reset 与银行要求重算事件。
- 事实源是 PostgreSQL 队列/任务表，不使用第二 broker。worker 不依赖 HTTP、Application 或请求 cookie。
- 任务有租约、有限重试、幂等与领取版本；失去 owner 的执行者不能提交。退出释放本次领取，强制退出通过 lease 到期恢复。
- 导入正式事务锁定 job 和当前权限，业务事实/审计/成功状态原子提交；取消与提交互锁。
- OA 附件准备可分批 deferred，保留已完成解析但不提交部分权威快照；真实解析错误明确失败。
- 匹配以 owner 命令提交，不自我循环投递；变化范围使用真实成员月份，避免逐行重建。
- 部署、监控和命令参数从 registry 派生，四个实例的 poll/lease 调优属于运行配置。

## 依赖方向

[OA 集成](../oa-integration/README.md)、[正式关联关系](../workbench-relations/README.md)、[设置](../settings/README.md)、[银行流水导入](../imports-bank-transactions/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/services/runtime_queue.py](../../../backend/src/fin_ops_platform/services/runtime_queue.py)
- [backend/src/fin_ops_platform/services/runtime_worker_registry.py](../../../backend/src/fin_ops_platform/services/runtime_worker_registry.py)
- [backend/src/fin_ops_platform/services/runtime_worker.py](../../../backend/src/fin_ops_platform/services/runtime_worker.py)
- [backend/src/fin_ops_platform/app/worker.py](../../../backend/src/fin_ops_platform/app/worker.py)
- [backend/src/fin_ops_platform/services/runtime_worker_handlers.py](../../../backend/src/fin_ops_platform/services/runtime_worker_handlers.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/workbench_matching_queue.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/workbench_matching_queue.py)
- [tests/test_runtime_worker_registry.py](../../../tests/test_runtime_worker_registry.py)
- [tests/test_runtime_worker.py](../../../tests/test_runtime_worker.py)
- [tests/test_runtime_queue.py](../../../tests/test_runtime_queue.py)
- [tests/test_deploy_runtime_examples.py](../../../tests/test_deploy_runtime_examples.py)
- [tests/test_read_model_runtime_removal.py](../../../tests/test_read_model_runtime_removal.py)
- [tests/test_etc_formal_matching.py](../../../tests/test_etc_formal_matching.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
