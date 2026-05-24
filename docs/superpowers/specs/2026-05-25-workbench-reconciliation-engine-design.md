# 关联台统一配对引擎设计

日期：2026-05-25

## 背景

关联台当前负责把 OA、银行流水、发票放在同一工作台中展示，并支持自动候选、手工确认、撤销、异常处理和特殊业务类型。现有代码已经有自动匹配规则、特殊规则、候选落库、读模型投影和分组展示，但配对判断分散在多个层次：

- `WorkbenchMatchingRules` 生成普通候选。
- `WorkbenchSpecialPairRuleService` 和 `WorkbenchSpecialRuleDetector` 生成特殊候选。
- `WorkbenchMatchingOrchestrator` 按月份重算候选。
- `WorkbenchSqlProjectionBuilder` 仍会在投影阶段重建和应用候选。
- `WorkbenchCandidateGroupingService` 还会合并候选并把部分分组晋级为自动关闭。
- API 层保留了旧 payload 候选应用路径。

这种结构导致自由匹配、特殊匹配、展示分组和读模型刷新之间边界不清。用户明确要求不要救急或临时方案，而是重新梳理成生产级整合方案。

## 已确认口径

- 自动展示状态只保留 `paired` 和 `open`。
- 不再使用 `needs_review` 作为关联台展示状态。
- 如果可以确定配对，三项或两两关系直接进入 `paired`。
- 如果无法唯一确定，相关行保持独立 `open`，不放在同一行。
- 配对规则采用唯一性优先：多个同级候选冲突时不按分数强行选择，全部保持 `open`。
- 自由匹配优先看金额，再看跨来源文本重复证据。
- 自由匹配字段范围：
  - OA：申请人、项目名称、申请事由。
  - 流水：对方户名、摘要、备注。
  - 发票：销方名称。
- `WorkbenchReconciliationEngine` 作为统一编排入口。
- 自由匹配和特殊匹配分域处理。
- 特殊匹配不走自由匹配规则，例如内部往来款、外部往来款、工资、现金周转、冲账。
- 特殊匹配和自由匹配最终进入同一套 row 占用、生命周期、读模型和审计机制。
- 现有 dirty scope 机制可以作为迁移期入口复用，但最终生产机制必须升级为 DB-backed dirty scope 队列。

## 目标

- 建立关联台唯一配对决策入口，避免规则、投影和分组层重复判断。
- 用生产级规则矩阵替代零散候选规则。
- 三项配对优先于两两配对。
- 两条可信两两关系可以在严格约束下升级为三项配对。
- 特殊业务类型先识别和占用，避免被自由匹配误吸收。
- 候选、配对、异常、手工确认都有明确生命周期和审计。
- 读模型只消费决策结果，不再生成或晋级配对。
- 前端只展示后端稳定结果，不在页面里推断配对。
- 匹配任务由数据库队列和 worker 驱动，支持幂等、重试、并发控制和监控。

## 非目标

- 不重做 OA、银行流水、发票导入和同步的业务事实源。
- 不把特殊业务类型并入自由匹配规则。
- 不用分数最高原则替代唯一性原则。
- 不把疑似候选展示成同一行。
- 不在首版引入新的外部队列基础设施。
- 不把 Redis 作为匹配正确性的依赖。
- 不保留 SQL 投影和分组服务里的业务配对判断作为长期路径。

## 推荐方案

采用方案 A：统一 `WorkbenchReconciliationEngine`。

方案比较：

| 方案 | 内容 | 结论 |
| --- | --- | --- |
| A | 建立统一配对引擎，特殊匹配和自由匹配分域，统一 row 占用、生命周期和投影 | 推荐；边界清晰，符合生产级要求 |
| B | 在现有规则上关闭 `needs_review` 并补唯一性检查 | 改动较小，但混乱边界仍然存在 |
| C | 把主要匹配放入 SQL/物化视图 | 批量性能好，但规则解释、测试和变更成本高，不适合作为第一阶段核心 |

## 总体架构

```text
WorkbenchReconciliationEngine
  ├─ ManualRelationGuard
  ├─ SpecialRuleEngine
  │   ├─ internal_transfer
  │   ├─ external_turnover
  │   ├─ salary / no_oa_bank_batch
  │   ├─ cash_turnover
  │   └─ offset / 冲
  ├─ FreeMatchingEngine
  │   ├─ oa_bank_invoice
  │   ├─ oa_bank
  │   ├─ oa_invoice
  │   └─ bank_invoice
  ├─ ClaimResolver
  ├─ DecisionStore
  └─ DecisionProjector
```

执行边界：

1. 已生效手工关联优先，相关 row 不进入自动自由匹配。
2. 特殊规则先识别，确定性特殊结果先占用 row。
3. 自由匹配只处理没有被手工关联、异常单、特殊规则占用的普通 row。
4. 冲突统一由 `ClaimResolver` 处理。
5. 决策统一写入 `DecisionStore`。
6. SQL read model 只投影决策结果。
7. 前端只展示 `paired` 和 `open`。

## 自由匹配总原则

自由匹配只处理普通 OA、流水、发票之间的关系。

所有自动配对必须同时满足：

1. 金额一致。
2. 方向兼容。
3. 有跨来源有效文本重复证据。
4. 组合唯一无冲突。

金额按分为单位精确比较，不做模糊金额匹配。

文本重复项必须经过规范化：

- 去空格。
- 统一大小写和全半角。
- 去常见标点。
- 去低信息公司后缀。
- 过滤低信息词，例如 `报销`、`付款`、`费用`、`有限公司`。
- 低信息词不能单独作为配对证据。

唯一性优先级高于打分。同一 OA、流水或发票如果能形成多个同级候选，全部保持 `open`。

## 三项配对规则

### OA + 流水 + 单张发票

条件：

- OA 金额 = 流水金额 = 发票金额。
- 方向兼容。
- 三者之间存在有效证据链。
- 组合在当前月份唯一。

有效证据链示例：

- OA 项目或事由命中流水备注，发票销方命中流水对方户名。
- OA 申请人命中流水备注，发票销方命中 OA 事由或流水对方户名。

成立则输出 `paired`。

### OA + 流水 + 多张发票

条件：

- OA 金额 = 流水金额 = 多张发票价税合计。
- 多张发票必须是唯一合计组合。
- 每张发票都能通过销方名称或 OA/流水文本证据归入同一业务语境。
- 如果同金额下存在多个发票组合，保持 `open`。

成立则输出 `paired`。

### OA 来源附件发票 + 流水

条件：

- 发票来自该 OA 的附件来源链路。
- OA 金额 = 流水金额 = 附件发票合计金额。
- 流水和 OA 之间至少有一个有效重复证据。
- 流水候选唯一。

成立则输出 `paired`。

如果 OA 金额 = 流水金额，但附件发票合计金额不一致，不自动配对，保持 `open`。

### 两两关系升级三项

两条可信两两关系可以升级为三项配对：

```text
OA + 流水 可配对
OA + 发票 可配对
且共享同一个 OA
且金额闭合
且没有其他同级候选冲突
=> 升级为 OA + 流水 + 发票 三项配对
```

金额闭合要求：

- 单张发票：OA 金额 = 流水金额 = 发票金额。
- 多张发票：OA 金额 = 流水金额 = 发票合计金额。
- 附件发票：OA 金额 = 流水金额 = OA 来源附件发票合计金额。

流水和发票之间可以没有直接文本重复。OA 可以作为桥接证据。但 explain 必须记录这是桥接三项配对，而不是强三项配对。

三项证据等级：

- 强三项配对：OA-流水、OA-发票、流水-发票都有证据。
- 桥接三项配对：OA-流水、OA-发票有证据，流水-发票无直接证据，但金额闭合且唯一。

两者都可以输出 `paired`，但审计证据必须区分。

## 两两配对规则

两两配对只能在三项配对无法成立时执行，不能抢占可成立的三项配对。

### OA + 流水

条件：

- OA 金额 = 流水金额。
- 方向兼容。
- OA 申请人、项目名称、申请事由与流水对方户名、摘要、备注存在有效重复项。
- 双方唯一匹配。

成立则输出 `paired`。

### OA + 发票

条件：

- OA 金额 = 发票金额，或 OA 金额 = 唯一发票组合合计。
- OA 申请人、项目名称、申请事由与发票销方名称存在有效重复项。
- 组合唯一。

成立则输出 `paired`。

### 流水 + 发票

条件：

- 流水金额 = 发票金额，或流水金额 = 唯一发票组合合计。
- 流水对方户名、摘要、备注与发票销方名称存在有效重复项。
- 组合唯一。

成立则输出 `paired`。

## 匹配优先级

固定优先级：

1. 已生效手工关联。
2. 特殊匹配确定结果。
3. 三项自由匹配。
4. 两两自由匹配。
5. `open` 独立展示。

冲突处理原则：

- 已生效手工关联永远优先。
- 特殊确定结果优先于自由匹配。
- 三项自由匹配优先于两两自由匹配。
- 同级候选冲突时不强配，全部保持 `open`。
- 所有回退为 `open` 的原因必须记录在 explain/debug 信息中。

## 特殊匹配边界

特殊匹配不使用自由匹配规则，不参与“金额一致 + 文本重复”的普通配对判断。

特殊匹配范围包括但不限于：

- 内部往来款。
- 外部往来款。
- 工资。
- 现金周转。
- 冲账。
- 无 OA 管理批次类规则。

特殊匹配原则：

- 能确定则输出 `paired`。
- 不能确定则保持 `open`。
- 不输出 `needs_review`。
- 特殊匹配占用的 row 不再进入自由匹配。
- 如果特殊匹配和自由匹配都尝试占用同一 row，默认特殊匹配优先，并记录冲突 explain。

## 状态模型

展示状态只保留：

| 状态 | 含义 |
| --- | --- |
| `paired` | 系统或人工已经确定配对，进入同一行 |
| `open` | 没有唯一确定配对，独立展示 |

内部决策生命周期可以包含：

| 内部状态 | 含义 |
| --- | --- |
| `proposed` | 引擎内部生成的候选，不直接展示 |
| `paired` | 唯一无冲突，可投影为同一行 |
| `open` | 无配对或冲突回退 |
| `suppressed` | 被异常单或手工关联压制 |
| `consumed` | 被手工确认或其他高优先级事实消费 |
| `expired` | source version 或 rule version 过期 |

前端不得展示内部状态，除非后续新增管理员 debug 面板。

## 决策数据模型

建议新增或升级关联台决策表，保留现有候选表迁移兼容：

```text
read_model.workbench_reconciliation_decisions
  id
  tenant_id
  scope_month
  decision_key
  decision_type          paired|open
  match_domain           manual|special|free
  match_shape            oa_bank_invoice|oa_bank|oa_invoice|bank_invoice|bank_bank|single
  rule_code
  rule_version
  row_ids
  row_types
  oa_row_ids
  bank_row_ids
  invoice_row_ids
  amount
  direction
  cardinality            1:1:1|1:1:N|1:1|1:N|N:1|single
  evidence
  blockers
  conflict_set
  source_versions
  consumed_by_relation_id
  suppressed_by_exception_case_id
  created_at
  updated_at
```

要求：

- `decision_key` 稳定，由 scope、rule、row ids、rule version 生成。
- `evidence` 记录金额、方向、重复字段、规范化 token、桥接路径。
- `blockers` 记录为何没有配对，例如金额不闭合、多个候选、特殊规则占用、异常单压制。
- `source_versions` 用于判断 stale 和 replay。
- 手工确认必须消费相关自动决策。
- 撤销手工确认必须重新标记该月 dirty。

## 执行机制升级

现有代码已有 dirty scope 和后台 worker 雏形，但当前主要依赖进程内 `WorkbenchMatchingDirtyScopeService` 和 state snapshot。生产级重构必须升级为数据库队列驱动。以下 7 条为最终设计要求。

### 1. 数据变化只写 dirty queue

以下动作完成并提交后，必须在同一个数据库事务中写入或更新 `job.workbench_matching_dirty_scopes`：

- OA 同步或重建。
- 银行流水导入。
- 发票导入。
- 手工确认关联。
- 撤销关联。
- 异常单创建或关闭。
- 特殊规则配置变化。
- 自由匹配规则版本升级。

写路径只标记月份 dirty，不在用户请求中执行重匹配。

### 2. Worker 从数据库领取月份

Worker 使用数据库队列领取可执行 scope。

要求：

- 领取时使用数据库锁，例如 `FOR UPDATE SKIP LOCKED` 或等价机制。
- 同一月份同一时间只能被一个 worker 处理。
- 支持多个 API/worker 实例同时运行。
- 进程内锁只能作为单实例优化，不能作为正确性依赖。

### 3. 延迟合并

写入 dirty scope 时设置 `available_at = now + 1-3 分钟`。

目的：

- 合并一次导入或同步产生的多次变化。
- 避免同一月份短时间内重复计算。
- 保持用户体验在分钟级刷新。

如果同一月份在延迟窗口内再次变更，只更新 reason、source version 和 `available_at`，不新增重复任务。

### 4. 执行仍按月份增量

Worker 不做全表扫描，只处理 dirty 月份。

每次执行必须带：

- `scope_month`
- `source_versions`
- `rule_version`
- `request_id`
- `started_at`

如果 source version 和 rule version 没有变化，可以跳过重算并标记完成。

### 5. 失败可重试

失败时写回 dirty scope：

- `attempt_count`
- `last_error`
- `available_at`
- `status`
- `updated_at`

重试使用退避策略。超过阈值后进入 `failed`，但不丢失 scope。管理员可以手动重试。

Worker 崩溃后，超过租约时间的 `running` scope 可以被其他 worker 重新领取。

### 6. 页面不阻塞

用户打开关联台时：

- 页面读取最近一次稳定 read model。
- 如果当前月份 dirty 或 stale，只触发后台刷新，不在请求线程内重建。
- 前端可以展示“配对结果刷新中”的轻量提示。
- 刷新完成后 read model 版本更新，前端重新拉取。

页面读取路径不得成为匹配计算主路径。

### 7. 保留手动重建

管理员可以对指定月份执行手动重建。

手动重建必须遵守：

- 不覆盖手工确认关联。
- 不覆盖已生效特殊匹配。
- 只重建自由匹配决策。
- 记录操作者、原因、开始时间、结束时间、影响行数和错误信息。
- 可重复执行且结果幂等。

## 读模型投影

SQL 投影只消费 `workbench_reconciliation_decisions` 和手工关联事实。

长期目标：

- 移除 SQL 投影中的候选重建逻辑。
- 移除分组服务中的自动关闭晋级逻辑。
- 保留分组、排序、分页和展示聚合。

投影规则：

- `paired` 决策形成同一 group。
- `open` 行独立展示。
- 手工关联 group 优先于自动 group。
- 特殊 group 带特殊标签，但不通过自由规则解释。
- 冲突和未配对原因只进入 debug/explain，不把冲突行合并展示。

## 错误处理和一致性

- 所有匹配运行必须有 `request_id`。
- 每个月份匹配运行必须记录开始、完成、失败和耗时。
- 旧任务不能覆盖新 source version 的结果。
- 手工确认和撤销必须在事务内写关系事实、消费或释放决策、标记 dirty。
- 异常单创建和关闭必须压制或释放相关决策，并标记 dirty。
- 特殊规则配置变化必须标记受影响月份 dirty。
- 规则版本变化必须支持显式 backfill。

## 验证策略

测试分层：

1. 规则单测：每个 rule_code 一组 golden cases。
2. 文本规范化单测：低信息词、公司后缀、摘要、备注、销方名称。
3. 三项配对单测：1:1:1、1:1:N、来源附件、桥接三项。
4. 两两配对单测：OA-流水、OA-发票、流水-发票。
5. 唯一性冲突单测：同金额多个候选时全部保持 `open`。
6. 特殊规则隔离单测：特殊占用 row 不进入自由匹配。
7. pipeline 测试：导入/OA 变化 -> dirty queue -> worker -> decisions -> read model -> API group。
8. 手工确认测试：确认后自动决策 consumed，撤销后重新 dirty。
9. 异常单测试：异常创建后 suppressed，关闭后恢复重算。
10. Worker 测试：DB 锁、租约超时、失败重试、source version 防旧覆盖。

验收标准：

- 前端不存在 `needs_review` 展示状态。
- 无法唯一确定的候选不会出现在同一行。
- SQL 投影和分组服务不再产生业务配对判断。
- 多实例 worker 不能同时处理同一月份。
- 导入后正常在分钟级完成 dirty 月份刷新。
- 手工确认、撤销、异常单和规则版本升级都有可追溯审计。

## 迁移步骤

1. 写入本设计并评审确认。
2. 建立 `WorkbenchReconciliationEngine` 接口和 decision DTO。
3. 实现自由匹配文本规范化、金额闭合、唯一性 resolver。
4. 将特殊规则接入 engine 的 special domain。
5. 新增或升级 decision store。
6. 将 dirty scope 切到 DB-backed queue。
7. 将 worker 改为数据库领取和幂等执行。
8. 将 SQL 投影改为只消费 decisions。
9. 删除分组服务中的业务自动关闭晋级。
10. 前端收敛到 `paired` / `open`。
11. 补齐 pipeline 和 worker 测试。
12. 做单月 shadow replay，对比旧结果和新结果。
13. 灰度切换生产路径。
14. 保留短期回滚开关，稳定后删除旧候选应用路径。

## 待确认事项

- 收入方向是否纳入自由匹配首版。
- 文本低信息词表是否需要业务方维护入口。
- 附件发票金额不一致是否永远保持 `open`，还是允许某些特殊规则接管。
- 手工重建入口放在关联台页面还是运维设置页。
