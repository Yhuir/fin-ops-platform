# 第三次审阅：完整闭环与遗漏检查

## 入口与调用方

已覆盖：

- 页面 route、frontend API client和 mutation handlers；
- list/detail/submit-selection/submit/withdraw/reset endpoints；
- application、domain batch service、relation command adapter；
- PostgreSQL read repository和state store；
- read model producer、worker、queue/readiness；
- Page Audit、测试和模块文档。

标签规则子链路明确排除，No-OA及其它页面只做回归。

## 失败与并发

实施必须验证：

- invalid page、未知 batch、空/重复/跨月/跨银行选择；
- optimistic version conflict与重复请求；
- relation conflict/not found；
- reset部分候选已撤回或 relation缺失；
- 数据库失败时批次和关系均回滚；
- worker失败时 read model保持 refreshing/stale并可重试；
- background reconcile超时只提示警告，不把已提交的 command谎报失败；
- route切换、重复点击和卸载后请求不会覆盖新状态。

## 旧代码删除清单

必须删除或替换 bank-flow可达的：

- no-OA schema值、新 ID生成、display tag和idempotency namespace；
- subclass对 `no_oa_*` 方法的直接调用；
- bank-flow worker使用shared base application的旧边界；
- route legacy error translation map；
- reset同步 `refresh_batches(...)` 循环；
- frontend withdraw/reset对完整 downstream targets的同步等待；
-与上述旧行为绑定的测试和文档断言。

必须保留：

- No-OA页面真实使用的代码；
- 历史 batch ID可读写兼容；
- canonical relation fan-out；
- durable freshness gate与当前权限/审计。

## 七类测试适用性

1. 业务核心：适用，覆盖批次状态、ID namespace、选择校验、reset。
2. Service：适用，覆盖原子保存、bulk cancel、read port和refresh targets。
3. API合同：适用，覆盖shape、权限、冲突、freshness。
4. Read model/cache/job：适用，覆盖分页proof、stale/refreshing/fresh、worker完成与重试。
5. 前端交互：适用，覆盖loading、局部更新、同步中、按钮禁用和错误反馈。
6. E2E：适用，覆盖submit→fresh→withdraw→fresh及reset主路径。
7. 回归：适用，覆盖No-OA、Workbench、银行明细、标签规则和Audit。

## 发布与回滚

- 代码和文档只在所有本地门禁通过后提交到 main。
- 部署唯一 SHA；不做历史 ID migration。
- 回滚为应用 release回滚；新前缀 batch rows只是派生投影，旧版仍可按 relation mode读取，不需要回滚业务数据。
- 生产写验证优先使用安全 no-op/可撤销样本；reset-all具有业务影响，不为性能测试擅自触发。其生产级性能以真实 PostgreSQL受控数据或现有真实操作证据验证，除非用户明确授权并存在可安全恢复窗口。

## 第三轮判定

没有遗漏会阻止闭环的架构、失败、权限、审计、回滚、性能或隔离条件。计划可以进入详细实施计划；详细计划不得增加本审阅未证明必要的新基础设施。
