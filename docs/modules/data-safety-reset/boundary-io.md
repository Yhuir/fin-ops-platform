# Data Safety Reset 模块边界与 I/O

日期：2026-08-15

## 输入

Admin session、当前 OA 密码复核、reason、精确 impact fingerprint、一次性 recovery receipt 与 idempotency key。

## 执行

API 只原子消费 receipt、创建 background job/outbox 和 audit。`settings-maintenance` worker 锁定目标、重算
fingerprint，再通过 owner repositories 清理明确 canonical tables。未知/漂移/活动任务均在删除前 fail closed。

## 输出

Job status、精确删除计数、audit 与必要的 OA sync/Workbench matching domain work。完成只证明 reset job 的
canonical 操作完成；页面随后 normal GET 读取当前事实。

## 禁止边界

- 不在 API thread 中执行大删除。
- 不接受任意表、SQL、通配 scope 或默认密码。
- 不恢复旧 projection rebuild/refresh 链。
- 不删除主数据库；只删除 reset 合同明确登记的业务数据。
