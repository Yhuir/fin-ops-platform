# 第 2 项：流水规则配置链路详细实施计划

## 目标

将规则保存从“settings 写入 + 两次全 relation 扫描 + N 次 relation/history/fan-out + 重复 lifecycle/enqueue”收敛为 O(1) 的“settings/audit 单写 + bank-flow 单次 durable refresh”，保持 GET/API/UI 合同不变，并彻底移除 bank-flow 可达的旧同步路径。

## 实施步骤

### 1. 锁定 bank-flow 专属 settings shape

修改 `AppSettingsService`：

- 将规则规范化抽成中性的 requirement-rules helper，并用显式参数区分：
  - no-OA 可读取/生成 legacy `selected_tag_codes`；
  - bank-flow 只读取 `rules` / `requirements_by_tag_code`，结果只含 `version` 与 `requirements_by_tag_code`。
- 将标签归档 detach helper同样改为中性 helper；bank-flow 不读取或生成 selected 字段。
- `update_bank_flow_rule_batch_tag_rules(...)` 在版本和规则校验后比较规范化 requirement map：
  - 相同：直接返回当前 public payload；不写 store、不配置 category service、不写 audit；
  - 不同：version +1，单次保存并记录既有 audit action。
- 不改变 public GET/PUT response shape、错误码或权限。

### 2. 一次性清理持久化 legacy 字段

新增 migration `0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql`：

- 只处理 `app.app_settings.settings_key='app_settings'` 下的 `bank_flow_rule_batch_tag_rules`。
- 把 legacy `selected_tag_codes` 中尚未出现在 `requirements_by_tag_code` 的 code 合并为 `{requires_oa:false, requires_invoice:false}`。
- 删除 bank-flow policy 内的 `selected_tag_codes` 与 `inactive_selected_tag_codes`。
- 不修改 `no_oa_bank_batch_tag_selection`。
- 记录 migration evidence 到 `raw_payload`；SQL 必须幂等。
- 更新 migration 清单和 migration contract tests。

### 3. 收敛 application I/O

修改 `BankFlowRuleBatchApplicationService.update_tag_selection(...)`：

- 调用 bank-flow settings writer。
- 通过返回 version 与已校验 expected version 判断 semantic change。
- no-op 立即返回。
- actual change 只调用一次现有 `BankFlowRuleBatchReadModelRefreshProducer`，scope 为 `all`、reason 为 `bank_flow_rule_batch_tag_rules_changed`、metadata 为 bank-flow relation mode。
- 删除 `after_mutation(...)`、relation sync 和 broad lifecycle 调用。

### 4. 删除旧链路代码

从 `BankBatchApplicationService` 删除：

- 无路由/worker生产调用方的 base `tag_selection_payload` / `update_tag_selection`；
- `_sync_bank_flow_rule_relation_requirements`；
- `_sync_turnover_rule_relation_requirements`；
- 仅由上述方法使用的 relation requirement 推导、比较和 row helper；
- 失去用途的 turnover constants/imports。

保留：批次创建时用于写入新 relation 审计提示的 `_paired_requirement_metadata_for_relation_mode(...)`，以及独立 `NoOaBankBatchApplicationService` 的 legacy 行为。

### 5. 更新和新增测试

#### 业务核心单元测试

- rules 语义相同为 no-op，version 不变。
- actual change version +1。
- 重复/未知/停用/legacy selected 输入继续 fail fast。

#### Service 层

- actual change 只 enqueue 一次 `bank_flow_rule_batch/all`。
- no-op 不 enqueue。
- 保存不调用 active relation list/update、broad lifecycle 或 turnover I/O。
- audit 只在实际变化时写一次。

#### API 合同

- GET/PUT shape 不变且没有 selected 字段。
- optimistic conflict 与权限/错误 shape 保持。
- 删除“PUT 后追溯改写 relation metadata”的旧断言，替换为“existing relation metadata 不变、formal relation 仍 paired”。

#### Read model / job

- actual change 产生单一 bank-flow durable refresh。
- source version 变化后 stale/refreshing → worker completion → fresh。
- no Workbench/turnover dirty/outbox。

#### 前端

无 UI/interaction 代码变化；运行现有规则抽屉测试，证明读取、编辑、保存、错误反馈没有回归。

#### E2E

运行现有 bank-flow rules flow；如现有断言包含旧 relation 重写语义则更新为 formal relation 合同。

#### 回归

- no-OA legacy selected API 仍可读写。
- bank-details 标签字典、turnover ledger、Workbench formal relation grouping、bank-flow batch operations 不回归。

### 6. 加机械边界门禁

在 bank-flow backend boundary tests 中锁定：

- bank-flow rule save body 不包含 `list_active_relations`、`update_relation_metadata_for_case_id`、`_sync_*relation_requirements` 或 `after_mutation`。
- base service 不再声明旧 sync 方法。
- bank-flow settings normalized snapshot 不含 selected 字段。
- no-OA legacy service仍有自己的 selected contract，防止误删其他页面能力。

### 7. 文档影响

更新：

- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `state-machine.md`
- `tests.md`
- `implementation-notes.md`
- `docs/dev/api-contracts.md`
- `docs/architecture/module-boundaries/canonical-facts.md`（仅在当前描述仍要求 broad fan-out 时）

删除“requirements 决定 Workbench paired/open”和“保存规则追溯改写已有 relation”的过期事实；写明 existing formal relation metadata 是历史快照，规则只影响未来候选/新批次。

### 8. 验证顺序

1. 目标单元/service/API/boundary/migration tests。
2. `bash scripts/verify.sh lint`。
3. bank-flow、no-OA、Workbench grouping、turnover、read-model queue 相关回归。
4. 前端 `BankFlowRuleBatchPage` 现有测试和 production build（仅一次，不做重复无意义 CI）。
5. 真实 PostgreSQL 空库应用 0001–0111，并执行目标后端测试。
6. diff/docs/migration clean checks。
7. commit、push main、使用 `./scripts/deploy-oa.sh` 部署唯一 SHA。
8. 生产验证：
   - exact SHA / services / workers / migration 0111；
   - 20 次页面壳、GET、Page Audit 性能回归；
   - 使用当前规则执行一次 no-op PUT，证明 ≤500ms、version 不变、无 audit/relation/queue 写；
   - 实际变化路径用真实 PostgreSQL性能测试验证，不为测量而改变生产业务规则；
   - bank-flow Page Audit pass/fresh/drained；
   - Workbench、bank details、turnover、no-OA 页面 Audit/queue 无新增污染。

## 完成定义

- 代码、测试、文档、迁移、旧代码删除、部署和生产证据全部完成。
- 性能门槛全部通过。
- bank-flow 规则保存不再读取/写入任何 existing relation。
- no-OA legacy 与第 3 项批次操作无功能回归。
- 工作树干净、main 与 origin/main 一致；然后才能进入第 3 项“批量处理”。

## 计划自审

1. **生产级**：包含 optimistic lock、权限/审计保留、durable queue、迁移、回滚、真实 PostgreSQL与生产验证。
2. **模块化/I/O**：settings writer、application orchestrator、refresh producer各自单一职责；不跨 relation/turnover 边界。
3. **不过度设计**：不新增基础设施；运行时路径只剩 settings/audit + 单 enqueue。
4. **高性能**：actual change 和 no-op 都为 O(1)，删除两次全量 relation 扫描与 N 次写放大。
5. **旧代码清理**：覆盖 runtime methods、helpers、persisted legacy shape、旧测试和旧文档，不留 fallback。
6. **不影响其他页面**：不改变 shared formal relation、no-OA/turnover contracts或其他 read model；有回归与 Audit 门禁。

结论：实施计划符合全部要求，没有需要再增加的新架构层，可以实施。
