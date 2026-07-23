# 免 OA 流水批量处理测试

- Business core：batch submit/withdraw、规则、版本冲突、relation metadata。
- Service/persistence：原子 `save_no_oa_bank_batch_mutation(...)`、rollback、精确 changed case/month、零 Workbench snapshot。
- API contract：single/bulk submit、withdraw、权限、错误码、空 targets、无 `workbench_rebuild_queued`。
- Read model/worker：missing/stale/fresh、精确 scope enqueue 与发布。
- Integration/regression：no-OA 与 bank-flow relation mode 隔离、Workbench 展示与撤回恢复。
- 无独立当前前端页面，因此本模块不新增 frontend component/E2E；相关可见行为由 Workbench/bank-flow 回归覆盖。
