---
phase: 12-etc-tickets-improvements
status: passed
score: "6/6 requirements; 7/7 must-have truths"
verified_at: "2026-07-18T17:08:26+08:00"
verifier: gsd-verifier
baseline_commit: 04db660a57ee6dcb09bbd69200c4ce57ee3d9f2f
verified_commit: 08b94bed4b6bb79722df3cc3d1914436bc2cfb24
production_status: external_gates_pending
---

# Phase 12 ETC 票据改进独立验收

## 结论

**通过。当前代码达到 `READY_FOR_UNIFIED_DEPLOYMENT`。**

这一结论的精确定义是：ETC 票据三状态闭环、提交审批可用性、OA 草稿幂等与未知结果恢复、窄读高性能链路、Audit 一致性、旧页面链删除和跨页面隔离，均已在当前代码、自动化测试和静态架构门禁中闭合；没有发现阻止统一部署的本地代码缺口。

这不是“生产性能已经验证通过”的声明。本阶段未部署、未操作生产数据，也未在真实 OA、对象存储、PostgreSQL 竞争和三页面混合负载下测量 p95/p99。生产验证仍是统一部署后的外部门禁，详见“生产外部门禁”。

## 验收范围与方法

- 对比基线 `04db660a57ee6dcb09bbd69200c4ce57ee3d9f2f` 与验收提交 `08b94bed4b6bb79722df3cc3d1914436bc2cfb24`。
- 实际变更共 36 个文件，其中 24 个为代码/测试文件，其余为模块长期文档和 GSD 过程记录。
- 直接检查页面、HTTP route、application service、domain service、repository/state store、Audit、测试和模块文档；不以实施总结替代代码事实。
- 重新执行 ETC 相关后端与前端核心测试，并复核主控已完成的跨页面、E2E、构建、schema、lint/docs 和代码审查门禁。
- 验收期间未修改业务代码、未提交、未推送、未部署、未执行生产 migration/queue/worker 或业务数据操作。

## Requirements 验收

| Requirement | 状态 | 验证结论 |
|---|---:|---|
| PAGE-14 | 通过 | Phase 12 的 context、research、plan、validation、summary、review、fix 和本报告形成完整链路；长期事实已同步到 ETC 模块、API、架构和运维文档。 |
| PAGE-04 | 通过 | 本阶段未修改 `.planning/codebase/` 生成物，未用过期代码地图替代当前代码事实。 |
| PAGE-05 | 通过 | 实施前已识别 ETC 页面、application/domain service、repository/state store、Audit、Import Center 正式 consumer、模块边界、风险和验证责任。 |
| PAR-01 | 通过 | 用户明确要求在 `main` 工作；实际修改范围聚焦 ETC 链路及必要共享接口，未发现与其它页面并行实现重叠的业务写目标。 |
| PAR-02 | 通过 | 长期文档更新由计划明确包含，且仓库规则要求状态机、边界、API、Audit 和运维事实发生变化时同步维护。 |
| PAR-03 | 通过 | 代码审查迭代完成后，最终状态、边界、测试矩阵、性能门槛和部署后门禁均已沉淀到长期文档。 |

## Must-have truths 验收

| # | 必须成立的事实 | 状态 | 代码与测试证据 |
|---:|---|---:|---|
| 1 | ETC 批次具有“未提交 → 暂存 → 已提交”三个明确桶 | 通过 | 后端状态映射、Audit 常量和前端三标签使用同一状态语义；创建 OA 草稿后进入暂存，确认已创建 OA 后进入已提交。 |
| 2 | 选择“未创建 OA”必须回到未提交，并保留批次、发票和核对数据 | 通过 | `revoke_business_batch_oa_draft` 清理草稿/提交关联与当前归属，但保留 `invoice_ids`、import batch、source task 和核对事实；没有物理删除整批数据。 |
| 3 | 首屏与选中详情不再加载全量对账任务、重复详情或对象存储 | 通过 | 列表走 2 次 SQL，详情走 3 次 SQL；页面首屏仅拉批次列表，选中后并行拉一个精确 task 和一个精确 detail；invoice 附件存在性由持久化引用/哈希派生。 |
| 4 | OA 创建具备稳定幂等键、短锁、CAS 和未知结果恢复 | 通过 | prepare 在本地锁内校验并持久化 attempt，外部 OA I/O 在锁外执行，complete/fail/unknown 均按 attempt CAS 收敛；传输不确定性进入 unknown，不伪装失败重试。 |
| 5 | Audit 对三状态、关联 owner、task 元数据和陈旧 creating fail closed | 通过 | Audit 使用一次 canonical snapshot，检查 bucket/key、owner、attempt、intent key、pending metadata 和 durable event clock；陈旧 creating 会失败而非误报通过。 |
| 6 | ETC 页面旧链已移除，并由架构门禁防止回流 | 通过 | 页面不再调用全量 reconciliation task 列表，不再维护双重 selection，不再走旧 task delete/兼容 fallback；静态 guard 禁止旧调用与热路径回退到全量 state/object store。 |
| 7 | 改动不会污染其它页面的功能或 read model | 通过 | 无 migration、schema、read model、cache、queue、worker 变更；共享 `server.py` 仅做 ETC route dispatch，共享 state-store 仅增加 ETC 聚焦接口；Import Center 正式 task consumer 保留并纳入回归。 |

## 关键链路独立检查

### 1. 提交审批可用性

- 服务端 `evaluate_etc_oa_draft_action` 是按钮可用性的唯一业务判定源，覆盖 `read_only`、`creating`、`pending`、非法状态、空发票、task 缺失、task 未导入和 ready。
- 列表与详情响应都附带同一 action contract；前端只显示服务端给出的显式 disabled reason，不再自己猜测业务状态。
- 创建命令再次执行相同服务端判定，并对关联 task 做 fail-closed 校验，避免“按钮可点但服务端拒绝”或“按钮灰色但实际可提交”的双重口径。

### 2. 三状态闭环

- 创建 OA 草稿成功后，批次进入暂存/confirmation pending。
- “我已创建 OA”把目标暂存批次转为 submitted，并同步 submission、invoice current owner 和批次状态。
- “我没有创建 OA”撤销草稿，批次回到未提交；保留本地批次、已导入发票、import batch 和核对事实，只清理本次 OA 草稿/提交归属。
- 手工确认使用明确的 batch ID 与 expected version；前端操作目标绑定当前行/抽屉批次，不会误用旧 selection。

### 3. 高性能读链路

- PostgreSQL 列表由 SQL 负责 owner/bucket/filter/sort/page/count，固定 2 次 SQL，不再加载整份 ETC state 后在 Python 中筛选。
- 详情固定读取目标 batch、目标 invoice IDs 和目标 task，共 3 次 SQL。
- 列表摘要不返回 `invoiceIds`；65 张发票的详情响应机械预算不超过 250 KB。
- 热路径不调用对象存储 `read/exists`；PDF/XML 可用性由 durable ref/hash 派生。
- 前端首屏没有 `fetchEtcReconciliationTasks`；选择批次后只有一个业务详情请求和一个精确 task 请求，并共享取消边界。

### 4. OA 写链路一致性

- OA intent key 在一次用户意图内稳定；仅 unknown 结果保留同一 key 供恢复，不对明确失败盲目复用。
- 本地锁只包住 prepare 校验和 attempt 持久化，真实 OA HTTP 调用在锁外，避免长时间阻塞其它 ETC 操作。
- prepare/complete/fail/unknown/recover 都只保存目标 business batch、submission attempt 及相关 invoice/import batch，并使用 expected version/CAS 防止并发覆盖。
- OA 传输错误或响应无法判定时进入 durable unknown；管理员恢复接口要求明确 decision、reason、evidence 和 expected version，且只允许二选一别名字段。
- 关联 reconciliation task 的 OA draft metadata 持久化失败会回滚内存状态与 audit counter，避免半写。

### 5. Audit 与可操作后一致性

- Audit 直接检查 canonical snapshot，不依赖页面缓存或额外 projection。
- 未提交、暂存、已提交各自有严格 occupancy/owner/submission contract。
- 暂存状态要求关联 task 的 OA draft metadata 与 batch 一致。
- `creating` 缺 attempt/key/audit 信息或超过 15 分钟仍未收敛时失败。
- 关联归属变化后允许历史批次保留成员关系，但 current owner 必须唯一，避免错误地把合法撤销/重关联判为重复 owner。

## 旧代码移除与保留边界

已从 ETC 票据页面链路移除：

- 页面首屏全量对账任务加载。
- `selectedTaskId`、task import batch 等与 business batch 并行维护的双 selection 状态。
- 选中一个业务批次时重复拉取详情的旧 effect。
- 页面旧 task delete 行为和兼容 fallback。
- 热路径回退到 `load_etc_state`、完整 reconciliation state 或对象存储探测。

有意保留：

- `/api/etc/reconciliation-tasks*` 及其 API client，因为 Import Center 仍是正式生产 consumer。
- 输入发票用途页面的 OA 反提 route；它属于不同业务模块，不是 ETC 票据旧链。

因此，“移除旧链”按 consumer 事实执行，没有为了清理而误删其它页面的正式入口。

## 自动化验证证据

### 独立 verifier 重新执行

| 命令 | 结果 |
|---|---|
| `PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py tests/test_audit_etc_tickets_read_model_tool.py tests/test_etc_reconciliation_service.py tests/test_platform_runtime_boundary_guards.py -q` | 450 passed, 5 skipped, 34 subtests passed |
| `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py -k 'ops_tax_etc_oa_draft_save_locks_and_compares_the_target_version' -q` | 1 passed, 34 deselected |
| `cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx` | 2 files、91/91 passed |
| `git diff --check 04db660a57ee6dcb09bbd69200c4ce57ee3d9f2f` 与 `git diff --check` | 通过 |

后端合计复现计划门禁：**451 passed、5 skipped、34 subtests passed**。

### 主控本轮已完成的发布准备门禁

| 门禁 | 结果 |
|---|---|
| ETC + Import + Cost + OA + Tax + Workbench 前端回归 | 12 files、286/286 passed |
| Chromium ETC 票据 E2E | 9/9 passed |
| Chromium ETC Import E2E | 5/5 passed |
| Production build | 通过；仅有既有依赖 CSS/chunk warning |
| Schema drift | `false` |
| 代码审查 | 自动迭代 3，24 个代码/测试文件，0 findings |
| fixer lint/docs/ruff/diff | 全部通过 |

独立 verifier 没有重复运行完整 286 项前端回归、14 项浏览器 E2E、production build 与全部 lint/docs；这些结果作为同一提交上的主控发布准备证据记录，独立复跑聚焦最关键的 451 项后端门禁和 91 项 ETC 前端门禁。

## 七类测试覆盖复核

| 类别 | 适用性 | 覆盖结论 |
|---|---:|---|
| 1. 业务核心单元测试 | 适用 | 覆盖三状态转换、按钮 eligibility、非法状态、空输入、版本冲突、幂等、unknown 恢复和保留数据语义。 |
| 2. Service 层测试 | 适用 | 覆盖 application/domain service、目标作用域持久化、OA 外部调用锁外、CAS、部分失败回滚与 Audit 记录。 |
| 3. API contract 测试 | 适用 | 覆盖列表/详情/action contract、expectedVersion、权限、恢复请求严格二选一、409/unknown 结构和响应体预算。 |
| 4. Read model/cache/job 测试 | 适用 | 本阶段未新增 read model/cache/job；测试确认 Audit 直读 canonical snapshot、无 freshness 伪装，并由架构 guard 防止热链绕回全量 state/object store。 |
| 5. 前端组件与交互测试 | 适用 | 覆盖三标签、loading/empty/error、按钮 disabled reason、抽屉确认、目标批次绑定、状态本地合并、unknown 提示与 selection 竞态。 |
| 6. E2E 业务流 | 适用 | ETC 票据 9 项与 ETC Import 5 项保护导入、核对、创建草稿、暂存确认/撤销和页面刷新关键链路。 |
| 7. 既有功能回归 | 适用 | 286 项跨 ETC/Import/Cost/OA/Tax/Workbench 前端测试、后端边界测试和浏览器 E2E 保护正式 task consumer、其它页面与共享接口。 |

没有测试类别被判定为不适用；第 4 类以“未引入新 read model/cache/job，并验证 canonical/Audit 和禁止旧热链回流”为本阶段的适用范围。

## 性能结论：机械预算已通过，生产指标待部署验证

### 当前已通过的本地机械门槛

- 列表：固定 2 次 SQL。
- 详情：固定 3 次 SQL。
- 热路径对象存储：0 次 `read/exists`。
- ETC 页面首屏全量 task 请求：0 次。
- 单次选中重复 business detail 请求：0 次。
- 65 张发票详情 JSON：不超过 250 KB。
- OA 外部网络 I/O：不持有 ETC 本地长锁。

这些门槛直接消除了本轮确认的主要结构性慢点，且由测试/静态 guard 固化；不能用它们替代真实生产延迟数据。

### 统一部署后必须执行的生产外部门禁

| 场景 | p95 目标 | p99 目标 |
|---|---:|---:|
| 批次列表 | ≤ 300 ms | ≤ 500 ms |
| 批次详情 API | ≤ 500 ms | ≤ 800 ms |
| 提交按钮 action-ready | ≤ 500 ms | ≤ 800 ms |
| 页面核心详情可操作 | ≤ 800 ms | ≤ 1.2 s |
| 写后新状态可见 | ≤ 500 ms | ≤ 800 ms |

部署后还必须验证：

- 真实 OA 服务成功、明确失败、超时/断线 unknown 及管理员恢复。
- 真实对象存储配置下热路径仍无附件探测 I/O。
- 真实 PostgreSQL 数据量、索引选择、锁竞争和并发写下的 p95/p99。
- 创建草稿、确认已创建、撤销回未提交、重关联后 Audit 仍通过。
- ETC 与成本统计、OA 待付款核对、关联台的混合读写负载隔离，不出现其它页面回归或 read model 污染。
- canary、错误率、日志、版本冲突率和回滚路径。

若任一生产指标未达标，应以生产 trace/SQL plan/外部 OA 分段耗时定位后再做定点优化，不能在缺少证据时新增 projection、cache、queue 或兼容 fallback。

## 模块化与隔离结论

本阶段维持简单的现有分层：

`React page → ETC API DTO → ETC route → application service → ETC domain service / focused repository`

- 页面只处理交互、展示和请求取消，不自行重建业务 eligibility。
- route 只做权限、请求解析和 HTTP 映射。
- application service 组装列表/详情 DTO 和 action contract。
- domain service 负责 OA 状态机、幂等、CAS、Audit 语义和业务转换。
- repository/state store 负责 SQL、目标作用域持久化与版本锁。
- Audit 只读 canonical 事实，不写业务状态。

没有新增 broker、projection、cache、worker、兼容 API、通用状态机框架或跨页面共享 UI 状态。设计满足生产完整性，但没有为未来 OCR 或未知扩展提前增加层次。

## 最终发布判定

**Phase 12 ETC 票据：`READY_FOR_UNIFIED_DEPLOYMENT`。**

- 本地代码/发布准备：通过。
- 阻塞统一部署的代码缺口：无。
- 已知旧链污染：无；正式跨页面 consumer 已保留并回归。
- 生产性能、生产 Audit、真实 OA/对象存储/PostgreSQL、三页面混合负载：待统一部署后验证。
- 本次验收未部署，也未执行任何生产写操作。

因此可以把本阶段纳入统一部署候选，但只有部署后的外部门禁全部通过后，才可以宣称“生产高性能和生产 Audit 完整闭环”。
