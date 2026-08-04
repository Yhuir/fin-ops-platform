---
phase: quick
plan: 260804-wam
type: execute
status: in_progress
date: 2026-08-04
---

# 关联台 OA/发票金额不一致异常闭环

## 目标

在正式关系组唯一分组出口按分精确比较 OA 合计与发票含税合计；不一致时生成可持久化忽略/恢复的异常，并用统一右侧抽屉取代旧“已处理异常/已忽略”弹窗。

## 边界与 I/O

- 输入：正式关系组的 canonical OA/发票行、当前金额异常处理状态、当前 Workbench read-model version、操作者身份。
- 输出：关系组及发票行上的 `amount_anomaly`；异常分页读取；幂等忽略/恢复写入和审计事件；受影响月份 read model 刷新。
- 事实源：canonical OA/发票金额；`app.workbench_exception_cases` 仅保存人工处理决策，不复制关系或业务金额。
- 不改变：关联完成状态、自动匹配、银行金额规则、普通异常处理语义、权限模型。

## 任务

1. 扩展金额校验服务与关系分组服务：只在同时存在 OA 和发票且金额均可解析时生成稳定 fingerprint；精确到分，无容差、无真假判断。
2. 在 PostgreSQL 异常仓储增加金额异常处理状态的批量读取、分页读取、幂等忽略/恢复和审计；复用现有异常表，不新增表或依赖。
3. 增加统一异常读写 API，并接入现有 Workbench freshness/version 与写权限门禁。
4. 前端增加 typed anomaly contract、发票来源下方 chip 和统一 `AppDrawer`；删除旧独立“已忽略”入口、两个 modal 及首屏启发式异常扫描。
5. 补齐金额规则、仓储/API、read model、组件交互和关键端到端回归测试；更新模块边界与状态机文档。
6. 完成 lint/typecheck/build/tests/performance smoke，审阅 diff，提交并推送 main；按标准入口部署并做生产只读与双状态写入恢复验证。

## 验收

- OA 合计与发票含税合计不同 0.01 元即显示 `金额不一致`；完全相等不显示。
- 忽略后显示 `已忽略：金额不一致`，进入“已处理异常”；恢复后回到“进行中的异常”。
- 异常抽屉始终按三栏关系组显示，分页不依赖主页面当前已加载数据。
- read-export 不能调用写接口；full-access/admin 可写且 actor 只能来自服务端会话。
- 无旧“已忽略”按钮或 modal，无旧前端 label/status 启发式作为异常事实源。
- 写入幂等、有审计、版本冲突 fail closed；生产部署后 read model 收敛且页面性能无显著退化。
