# 免 OA 流水批量处理测试

- Business core：batch submit/withdraw、规则、版本冲突、relation metadata。
- Service/persistence：原子 `save_no_oa_bank_batch_mutation(...)`、rollback、精确 changed case/month、零 Workbench snapshot。
- API contract：canonical list/pagination/filter、single/bulk submit、withdraw、权限、错误码、空 targets、无 runtime freshness 字段。
- Read model/worker：不适用；负向合同断言 no-OA event、scope、worker、env、repository 与 projection service 不再存在。
- Integration/regression：no-OA 与 bank-flow relation mode 隔离、Workbench 展示与撤回恢复。
- 无独立当前前端页面，因此本模块不新增 frontend component/E2E；相关可见行为由 Workbench/bank-flow 回归覆盖。
