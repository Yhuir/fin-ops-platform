# 试点模块选择

**原则:** 先选择最高频出 bug、边界收益明显、测试入口相对可控的模块。试点目标是验证方法，不是一次解决全系统。

## 选择标准

### 高优先级信号

- 最近频繁改动或频繁回归。
- 涉及多个页面或多个 read model。
- 有 canonical write + read model refresh + operation barrier。
- 前端页面和 API client 较大。
- 已有测试基础，适合补齐回归闸门。
- 文档模块完整，适合沉淀 IO 合同。

### 降低优先级信号

- 纯展示页面，无复杂写入。
- 没有 read model/worker。
- 业务边界过大，试点周期不可控。
- 依赖太多尚未稳定的共享边界。

## 候选模块

### Candidate A: `reconciliation-workbench`

优势：

- 是核心业务链路，回归影响大。
- 涉及 active generation、relation、candidate、read model、operation barrier、frontend domain events。
- 当前 dirty worktree 也集中在 workbench 相关文件，说明这里可能是近期高频变更区。
- 已有大量测试，例如 workbench API、selection、query、SQL runtime。

风险：

- 范围最大，业务规则最多。
- Workbench 有特殊 active generation 模型，不能机械套普通 read model。
- 作为第一个试点可能过重。

适合策略：

- 不把整个 workbench 作为一个试点。
- 选择一个窄边界，例如 “workbench partial relation / amount check / query API IO contract”。

### Candidate B: `bank-details`

优势：

- 页面和 application service 较大。
- 有 read model refresh、tag rules、category confirmation、operation barrier。
- API 和前端页面都较清晰。
- 适合验证“页面模块 IO 合同”。

风险：

- 与 pending invoice、workbench、ledger 等模块有关联。
- 自动标签和手工分类可能影响多个下游。

适合策略：

- 试点 auto-tag rules 或 category confirmation 这类边界。

### Candidate C: `pending-invoices`

优势：

- 业务状态、规则、read model、relation detail、batch attach 等边界丰富。
- 文档和测试较完整。
- 能验证 API contract、read model、前端 drawer/table 状态。

风险：

- 与 invoice lifecycle、OA pending、input usage、output collection 等模块交叉多。
- 规则变更影响域广，需要谨慎。

适合策略：

- 先做 read-side IO 合同，不先动规则写入。

### Candidate D: `oa-pending-payments`

优势：

- 页面边界相对明确。
- route module 已存在。
- 有 relation、bank candidates、read model、pending invoice rules dependency。

风险：

- 与 OA projection、pending invoice、workbench 交叉。
- 最近已有 quick work 记录，可能存在正在变化的需求。

适合策略：

- 适合作为第二批，而非首个试点。

### Candidate E: `batch-accounting`

优势：

- roadmap 仍指向 `server.py`，可验证 legacy route extraction 方法。
- 页面相对小于 workbench。

风险：

- 可能依赖 workbench relation read facade，涉及回滚/撤回语义。
- 如果测试薄弱，先补测试成本较高。

适合策略：

- 适合作为 route/server.py migration 试点，但不适合作为 read model 全链路试点。

## 推荐试点顺序

### 推荐首个试点: `bank-details` 的 category/tag 写入边界

理由：

- 有业务写入、read model refresh、operation barrier、前端交互和权限测试需求。
- 复杂度低于完整 workbench。
- 可以验证模块 IO 合同模板是否足够覆盖实际改动。
- 可以验证“写入成功”和“read model fresh”分离。

建议试点边界：

- 自动标签规则更新。
- 手工分类确认/撤销。
- 银行明细列表 read model freshness。

### 第二候选: `reconciliation-workbench` 的窄边界

理由：

- 核心业务风险最高。
- 但不建议全量 workbench 作为首个试点。

建议试点边界：

- partial relation / amount check / query response contract 中选择一个。

### 第三候选: `pending-invoices` read-side IO

理由：

- 适合验证 read model 和 drawer/detail contract。
- 不先触碰规则写入，可以控制风险。

## 试点启动前必须完成

- [ ] 用户确认试点模块。
- [ ] 读取目标模块 `docs/modules/<module>/README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md`、`e2e-coverage.md`。
- [ ] 用 CodeGraph/静态扫描列出目标模块 entry points。
- [ ] 填写完整 IO 合同。
- [ ] 填写影响分析和测试闸门。
- [ ] 明确不做全量重构。

