# 第 3 项：流水规则批量处理详细实施计划

## 目标

在不改变业务规则、权限和API response shape的前提下，把列表从“双全量读取 + Python分页/摘要”收敛为SQL分页与聚合；把详情从逐成员读取改为现有bulk query；把reset从逐relation + 同步逐月重建改为一次bulk cancel + 一次原子保存 + 后台scoped refresh；统一前端写后本地可见与后台收敛；清除bank-flow可达的no-OA旧合同。

## 实施步骤

### 1. 建立 bank-flow专属分页 read I/O

修改 `BankFlowRuleBatchReadModelRepositoryPort` 与现有 PostgreSQL read model repository：

- 新增 `read_bank_flow_rule_batch_page(filters, page, page_size)` 窄接口；
- SQL只读取当前页payload，使用 `LIMIT/OFFSET`；
- 同一 repository返回total、按batch_type/status聚合count/amount、source-version summary和readiness；
- 查询数固定，不随总batch数增长；
- 空数据在fresh时返回fresh空页，在readiness缺失时返回missing/refreshing，禁止伪装fresh；
- 保留现有 `list_bank_flow_rule_batch_rows({batch_id})` 作为单项恢复路径；不改变No-OA list方法。

在 `BankFlowRuleBatchApplicationService` 覆盖list orchestration：

- 只走专属paged port；
- 对当前页执行presentation/label mapping；
- 使用aggregate facts构建与当前完全一致的summary/categories；
- active rule tags即使为零仍出现在categories；
- 使用source-version summary做一次freshness比较；
- 缺失/过期时只enqueue现有bank-flow scoped refresh。

前端将page size从200改为50，不改分页交互。

### 2. 消除详情 N+1

- 在 `PostgresStateStore` 暴露已有 `PostgresCoreRepository.list_bank_transactions_by_ids(...)`；
- 在 `ImportNormalizationService` 增加窄bulk读取，内存模式继续从当前map批量解析；
- application的bank transaction rows-by-IDs改为一次bulk调用并按输入ID恢复稳定顺序；
- 未找到row保持当前忽略/错误合同；重复ID不造成重复SQL或错误排序；
- category与relation仍使用现有bulk能力。

### 3. 收敛 reset command

- Bank-flow application直接实现专属reset编排，不再调用shared旧reset路径；
- 收集submitted candidates、row IDs、case IDs和affected months；
- 领域service顺序变更batch状态，但关系取消只调用一次现有 `cancel_relations_for_row_ids(...)`；
- 复用一个bank-flow reset idempotency namespace；
- 删除请求内按month调用 `refresh_batches(...)`；
- 用一次 `save_bank_flow_rule_batch_mutation(...)` 原子保存changed relations和batches；
- 只返回既有results/summary/affected months/targets；worker按month重建draft；
- no candidates为O(1) no-op，零写入、零enqueue。

单批submit/withdraw继续复用当前原子保存，不引入新UoW；仅修正namespace/error和bulk取数。

### 4. 统一前端 foreground/background 边界

- submit保留现有command成功后本地更新；
- withdraw收到response后立即从当前bucket移除或更新batch，关闭drawer并解除foreground遮罩；
- reset收到response后切到unsubmitted，清空冲突选择，进入现有轻量background refreshing状态；
- 新增/收敛一个只提取 `bank_flow_rule_batch` targets的本地reconcile helper；完整targets仍由现有事件机制广播给其它页面；
- 后台只等本模块affected month fresh后reload；超时显示warning，不把已成功command显示为失败；
- refreshing期间禁用本页冲突写操作，读取/导航保持可用；不新增solid modal。

### 5. 删除 bank-flow可达旧代码

修改shared `BankBatchService`的当前配置点，而不是复制算法：

- 增加显式schema version和batch ID prefix配置，默认保持No-OA；
- bank-flow构造统一使用 `BANK_FLOW_RULE_BATCH_SCHEMA_VERSION` 与 `bank_flow_rule_batch_`；
- scoped child service继承同一配置；
- historical IDs不改写，仍可get/detail/withdraw；新生成draft使用新prefix。

修改bank-flow application/worker边界：

- 提供中性bulk bank rows、source versions、stale reasons方法名，bank-flow不再直接调用 `no_oa_*`；
- bank-flow `resolve_labels`输出 `流水规则`；
- bank-flow idempotency、history、reason和errors使用正式namespace；
- worker构造 `BankFlowRuleBatchApplicationService` 或等价专属port，不再把bank-flow运行事件交给no-OA命名application边界；
- source versions使用bank-flow schema常量；
- 删除 `BANK_FLOW_RULE_BATCH_LEGACY_ERROR_CODES` 及其message fallback。

加architecture guard：bank-flow route、application、worker wrapper、frontend不得出现 `no_oa`、`NO_OA`、`免OA`；历史ID兼容测试使用显式fixture例外，不允许runtime fallback。

### 6. 测试

#### 业务核心

- 新bank-flow batch ID/schema/display tags/idempotency namespace；
- 历史ID仍可读、提交/撤回；
- submit/withdraw/reset状态与version conflict；
- 空、重复、未知、跨标签/月/银行和内部往来选择。

#### Service

- paged port只返回当前页，summary基于全过滤范围；
- list不调用两次full-row list；
- detail 1次bulk transaction read；
- reset 1次bulk cancel、1次原子persist、0次同步refresh；
- persistence失败恢复batch/relation内存快照且DB无半写；
- no-op reset零写。

#### API合同

- list/detail/mutations response shape不变；
- pagination total/page/pageSize准确；
-权限、invalid input、unknown、conflict、relation failure和persistence failure；
- stale/refreshing/missing/fresh与enqueue字段诚实。

#### Read model/job

- SQL分页与聚合真实PostgreSQL结果一致；
- source versions一致/混合/缺失；
- write使month refreshing，worker完成后fresh；
- stale event skip、失败重试、dirty scope cleanup；
- reset不产生`all` full refresh（明确无month时除外）。

#### 前端

- list page size 50与pagination；
- submit/withdraw command成功后≤一轮state update可见；
- reset显示同步中并禁用冲突按钮，fresh后reload；
- downstream Workbench未fresh不阻塞当前页面；
- timeout warning、API failure、route切换、重复点击和drawer关闭。

#### E2E与回归

- submit→bank-flow fresh→withdraw→bank-flow fresh关键路径；
- reset受控数据主路径；
- No-OA、Workbench、银行明细、流水规则标签配置、Page Audit无回归；
- architecture guard证明旧链不可达。

### 7. 文档影响

更新：

- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `state-machine.md`
- `tests.md`
- `implementation-notes.md`
- `docs/app-architecture/` 中该页面读写时序（若当前描述仍为同步等待）
- `docs/architecture/module-boundaries/read-model-contracts.md`（仅记录paged read port/freshness合同，不扩张模块所有权）

长期文档只写最终事实，不写原始prompt或阶段过程。

### 8. 验证顺序

1. 目标业务/service/API/repository/worker/frontend/architecture tests。
2. 真实PostgreSQL目标测试，验证SQL分页、bulk detail、原子reset与query-count上限。
3. `bash scripts/verify.sh lint`。
4. bank-flow全量相关后端与前端测试；No-OA、Workbench、银行明细、规则配置回归。
5. production build与既有关键E2E各一次，避免重复无意义CI。
6. docs/diff/migration/architecture clean checks。
7. commit、push main，部署唯一SHA。
8. 生产只读性能：页面壳、all/month list page size 50、small/large detail、Page Audit各20次。
9. 生产安全写验证：选择可撤销样本执行submit/withdraw，记录command response→本地可见→bank-flow fresh→Audit fresh/drained耗时；不得擅自reset全部生产业务批次。
10. reset用真实PostgreSQL生产规模fixture或安全窗口验证；验证HTTP不再同步rebuild。若存在用户授权且可恢复窗口，再执行生产reset。
11. 验证No-OA、Workbench、银行明细、规则配置Audit无污染；工作树干净、main=origin/main后才进入第4项。

## 完成定义

- 性能门槛全部通过；若month worker p95仍>2s，继续在本阶段优化现有worker SQL，不能把未达标写成完成。
- Audit在读、submit、withdraw和reset后均通过，refreshing期间状态诚实。
- bank-flow运行链不再产生或输出no-OA schema/ID/tag/error/idempotency合同；历史ID兼容明确受测。
- 不新增基础设施，不写其它页面私有read model，No-OA和其它页面无回归。
- 代码、测试、文档、部署、生产证据、commit/push和干净工作树全部闭环。

## 计划再次自审

1. **生产级**：包含权限、审计、optimistic conflict、原子回滚、durable freshness、真实PostgreSQL、发布回滚与生产证据。
2. **模块化/I/O**：Route、application、domain、read repository、relation command、worker、frontend各自边界明确；页面不跨写其它read model。
3. **不过度设计**：零新依赖、表、缓存、queue、worker和UoW；只复用现有能力并增加窄I/O。
4. **高性能**：删除两次全量list、详情N+1、reset同步重建和跨页面等待；门槛可测。
5. **旧代码清理**：覆盖ID、schema、UI tag、errors、idempotency、worker、route、tests和docs，同时安全保留历史身份。
6. **隔离性**：bank-flow专属read port和UI reconcile；shared canonical relation变化只经既有fan-out，其他页面有回归/Audit门禁。
7. **完整闭环**：分析、三轮审阅、实施步骤、七类测试、部署、生产写后性能和失败条件均已定义。

结论：计划满足全部要求，没有需要增加的新架构层，可以进入实施。
