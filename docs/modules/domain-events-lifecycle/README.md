# 领域任务通知

入口：`跨模块任务边界`。

在业务写入需要异步处理时传递精确领域意图，不承担页面刷新或浏览器业务状态。

## 边界与 I/O

输入：owner、tenant、event/job identity、幂等信息、精确对象/月份和审计上下文。输出：与事实一致提交的领域任务及后续结果。

## 当前业务约定

- OA 同步和支付状态使用 outbox；设置重置和关系要求重算使用对应事件；匹配使用独立 dirty scopes。
- 导入通过 job.import_jobs 直接领取，不经第二事件中转。
- 同事务写入保证事实与通知一致；消费者按版本/幂等处理重复和重试。
- 普通写后当前页面按需 GET，其他页面下次访问查询相同事实；不广播隐藏页面 I/O。

## 依赖方向

[后台任务](../runtime-workers/README.md)、[正式关联关系](../workbench-relations/README.md)、[设置](../settings/README.md)、[OA 集成](../oa-integration/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py](../../../backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py)
- [tests/test_derived_data_lifecycle_service.py](../../../tests/test_derived_data_lifecycle_service.py)
- [tests/test_settings_data_reset_service.py](../../../tests/test_settings_data_reset_service.py)
- [web/src/test/PageRouteHost.test.tsx](../../../web/src/test/PageRouteHost.test.tsx)
- [web/e2e/settings-data-reset-flow.spec.ts](../../../web/e2e/settings-data-reset-flow.spec.ts)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
