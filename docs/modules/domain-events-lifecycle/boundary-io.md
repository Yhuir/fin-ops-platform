# Domain Events / Lifecycle 边界与 I/O

日期：2026-08-15

## 状态

该模块不再承担跨页面刷新。普通写入和 import confirm 只提交 canonical facts 与明确领域任务；所有页面下次
normal GET 读取同一事实源。

## 当前事件 owner

- `oa.sync` -> OA sync worker。
- `import.process.requested` -> import worker。
- `settings.data_reset.requested` -> settings-maintenance worker。
- `settings.bank_relation_requirements.recalculate.requested` -> settings-maintenance worker。
- Workbench matching -> matching domain scope/orchestrator。

## I/O

- 输入必须有 owner、tenant、job/event identity、idempotency、bounded payload 与 audit context。
- 输出通过 owner service/repository 写 canonical facts、job/outbox/attempt 或 matching domain scope。
- 禁止 broadcast page event、projection target、hidden page I/O、通用 fan-out executor。

## 删除合同

旧 derived lifecycle refresh producers/executors、scope mapper、page worker handler 和 frontend operation barrier
不得恢复。历史 repair 若改变 canonical relation，消费页在下一次 direct GET 观察结果。
