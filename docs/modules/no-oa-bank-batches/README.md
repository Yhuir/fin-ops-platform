# 免 OA 批次 API

入口：`/api/no-oa-bank-batches/*`。

维护现存 no-OA 批次提交/撤回及其正式关系；属于仍有调用方的 API 能力，不是独立导航页面。

## 边界与 I/O

输入：精确 batch/case identity、month/filter/page、actor、version/reason。输出：batches/total/page/page_size/filters、命令状态和受影响月份。

## 当前业务约定

- 应用 service 编排 batch 与正式 relation command，scoped mutation 保存批次、关系、历史和审计。
- GET 在请求内从 canonical 输入构造批次，不创建页面任务。
- 实际调用者包含注册 HTTP routes、BankFlow selection command 与 Workbench internal-transfer adapter；不能因没有导航页删除能力。
- 银行规则页面有独立 owner，本模块不成为其备用查询路径。

## 依赖方向

[流水规则批量处理](../bank-flow-rule-batches/README.md)、[正式关联关系](../workbench-relations/README.md)、[银行明细](../bank-details/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py](../../../backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py)
- [backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py](../../../backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py)
- [tests/test_platform_runtime_boundary_guards.py](../../../tests/test_platform_runtime_boundary_guards.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
