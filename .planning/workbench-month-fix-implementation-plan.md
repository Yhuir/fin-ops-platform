# 关联台月份错误修复实施计划

日期：2026-09-14。状态：计划已复审，2026-09-14 获授权实施、提交 main、推送和部署；实施中。

本计划采用普通逐步实施，不使用 GSD 执行器、子代理或额外工作流。诊断证据见 [根因报告](debug/workbench-id-month-503.md)。生产执行依据用户后续明确授权，计划本身不授予额外权限。

## 1. 复审结论与范围收紧

原方案根因正确，但需补充以下明确决策才能实施：

1. 不全局修改 `postgres_repositories/common.month_start`；其有多个其他业务消费者。本次在 Workbench 关系写入 owner 边界复用已有严格年月校验，控制影响面。
2. selection repository 已有真实 `scope_month`，提交校验 DTO 却遗漏该字段。优先透传现有查询结果，不另建日期查询 service、缓存、registry 或额外全量水合。
3. 不在通用幂等 replay 中加入动态重新计算。错误响应的已证实月份元数据做一次有审计的定点修正，之后仍返回已保存响应。
4. 不改写原始 relation history。撤回恢复目标的日期范围统一来自目标成员的当前有效 canonical facts，拓扑仍来自原有可证明历史；修复动作追加独立审计。
5. 只补本次关系 scope 错误码的 UI 分类，不重构全站错误体系。
6. 保留现有事务、typed member 独占、版本、幂等、审计和正式发布措施；不新增 hash、冻结 contract、baseline 文件或业务 gate。
7. 存量扫描不能只搜 `2097` 等未来日期；随机 ID 也可能产生合法且看似正常的月份。当前两条关系、四条历史、三条响应是已证实范围，不是全部异常上限。

不扩大到自动匹配规则重写、金额规则调整、通用日期库改造、所有旧模块清理、独立 cash 模块、全站性能重构或读模型恢复。

## 2. 模块与 I/O

```text
HTTP route：已有认证、权限、请求解析
  -> WorkbenchWriteFacade：编排本次动作
  -> 现有 selection repository：集合查询所选 canonical typed members 与 scope_month
  -> relation owner 内纯函数：归并范围
  -> 现有 relation command + UoW + repository：事务写入、history、幂等、既有 outbox
  -> 原 API response
  -> 页面一次普通 canonical GET
```

| Owner | 输入 | 输出与职责 |
| --- | --- | --- |
| selection repository | tenant、typed row IDs、现有 scope 参数、事务连接 | 现有 descriptor 中的 row identity、source kind、ETC batch identity、`scope_month: date/null`；SQL 只在 repository |
| relation scope 计算 | typed member 对应的权威 scope 值 | 单一 `relation_scope: all/YYYY-MM`、去重排序的 concrete `affected_months`；纯计算、零 I/O |
| write facade | 原请求、服务端认证上下文、selection 结果 | 预览/提交编排；不从 ID、摘要、项目名或 raw payload 猜月份 |
| relation command/UoW | 当前成员、合法 scope、已有版本和幂等参数 | 保持 canonical relation/history/idempotency 原子性；现有锁和失败回滚不变 |
| repository | 已校验的 relation delta | 原 SQL 字段和持久化 shape；scope-only 修正同步必要 normalized payload |
| repair CLI/service | 明确候选、旧值、新值、actor/reason、现有事务依赖 | 一次有审计的定点修正及回滚能力；不成为在线 fallback，不直接调用 OA 外部写接口 |
| 前端 | 现有 response 与 WorkbenchApiError.code | 稳定错误提示、备注保留；成功一次回读，不新增页面状态副本 |

内部 `scope_month` 不直接扩散到公共页面 row DTO。成功 HTTP 字段和类型保持兼容，包括 case、成员、amount_check、affected_months、affected_scope_keys；只纠正月份值。

自动匹配、ETC、免 OA、银行规则批次等独立生产者继续负责原有业务 scope 语义，不被强制改成与人工选择相同的范围计算规则；共享 relation writer 只执行合法 scope 校验。

## 3. 月份事实与算法

来源固定复用 `_resolve_source_descriptors` 已有合同：

- 银行：`bank_transactions.txn_month`。
- 发票：canonical `invoice_month`。
- completed OA：现有 OA `scope_month/application_date` 的 owner 解析结果。
- in-progress OA：现有 admission scope 解析结果，不读审批时间推断。
- ETC summary：现有 batch/source descriptor，不解析 summary ID。

计算规则：

1. 仅以 canonical descriptor 为输入；实际 `date/datetime` 转成 YYYY-MM，字符串复用现有 `normalize_workbench_scope_key` 校验。
2. 所有目标成员都有月份且月份集合只有一个值：relation_scope 为该月。
3. 跨月，或存在业务合同允许为空的月份：relation_scope 使用既有 `all`，concrete affected_months 只包含有事实依据的月份；数据库继续按现有方式把 all 存为 NULL。
4. 缺日期与非法非空日期分别处理：已有源合同允许 null 时不增加“每条必须有日期”的新准入条件；明确非法值由 owner 报错，不取当前日期、不解析 ID、不吞错置空。源合同要求日期的记录仍遵守原有验证。
5. 请求的 month 继续服务原选择/查询范围语义，不能覆盖关系成员的真实日期。金额、权限、完整性、备注门槛维持现有规则。
6. affected months 同时覆盖本次受影响的 before/after canonical 成员；多月不截断。撤回恢复范围在既有锁内基于 current + predecessor 的目标成员计算。
7. preview 复用本次只读 selection 的结果；submit 复用本次事务 selection 的结果，禁止把 preview scope 当提交事实。

最多增加一个 Workbench 专用的小型纯函数模块，例如 `services/workbench_relation_scope.py`；若已有合适模块容纳则直接扩展。不得引入接口工厂、注册表、策略层或新依赖。

## 4. 执行步骤与完成条件

### A. 建立真实回归样本

- 使用合成 OA/银行/发票，不依赖真实业务文件；复用现有 test builders。
- 银行 ID 保留触发特征 `209440`，另造合法误匹配 `209703`、`202608`、多命中和无数字场景。
- 核心样本：3 OA + 1 bank + 7 invoice，三栏均 437 元，日期跨月；另有单月、允许缺日期、ETC、in-progress OA。
- 在现有 scope/command/UoW 测试中补真实 resolver 组合，不能继续把目标月份函数 mock 为固定值。
- 真实 PostgreSQL 用例复现当前非法 INSERT，并验证修复后关系、history、幂等同成同败。
- 完成条件：新回归在旧实现上明确失败；失败原因正是日期/范围错误，不是环境缺失。

### B. 接通内部 scope I/O，修复写链

- `postgres_repositories/workbench_page_selection.py`：把已查到的 scope_month 加到内部 validation/selection 输出；保持 typed exact-set、tenant、source alias 语义。
- `workbench_write_facade.py`：preview/confirm、cancel/withdraw、个人垫付及仍在调用的特殊关系 helper 改用 canonical scope；confirm handler 的最终持久化值来自事务内结果。
- `workbench_relation_command_service.py`：接收合法 scope；撤回目标拓扑仍使用原历史，目标 scope 使用已锁定成员的 canonical 范围。避免再次逐行读取或独立开事务。
- `postgres_repositories/workbench_relation.py`：在 Workbench 写入边界复用既有 scope 校验再交给 month_start，保护所有正式关系生产者；不改变通用 month_start 合同。
- `server.py`：仅保留路由、依赖组装与 HTTP 映射；撤除已替代的日期推断回调，不把新业务计算塞回 Application。
- scope-only 修正保持 relation status、mode、typed members、金额、版本的现行拓扑语义。仅纠正范围不伪造 confirm/withdraw，不无故增加 topology version。
- 完成条件：新回归通过，成功响应不含 ID 生成的伪月份，既有关系生产者测试通过。

### C. 删除旧链并核对跨入口

必须移除的旧责任及符号：

- `ROW_ID_MONTH_RE`、`_row_month_scope_from_row_id`。
- `_month_scope_for_selected_row_ids` 及注入/调用。
- `_scope_keys_for_row_ids` 的 ID 推断及注入；消费者迁移为 canonical scope 后删除该实现。
- `_row_month_scope` 中 ID fallback、仅检查字符串形状的 `_normalize_month_from_value`；消费者迁移后删除无调用方法。
- `_operation_scope_keys_for_rows_and_row_ids` 合并伪 scope 的分支及目标测试中的固定月份桩。

按路由入口 -> API client -> facade -> command -> repository -> worker/恢复/测试/docs 扫描。只删除已迁移、无有效消费者的旧代码，不能把独立 cash、ETC 或免 OA 的有效功能误删。

完成条件：全仓库运行时中上述错误链零引用；新代码没有按 ID 解析日期的等价实现。此项以扫描和行为测试核实，不新增 hash gate。

### D. 修复诊断与有限的 UI 反馈

- 关系写日志包含 request ID、阶段、异常类型，保留堆栈，避免敏感 payload。
- 复用现有日志读取方式核对异常与 request ID。本次根因已定位，不修改 `finops-deploy-control` 或扩建运维诊断工具；其日志展示问题单独记录，不作为业务修复前置条件。
- 非法请求月按现有 400 合同；服务端 scope 不变量错误使用一个明确的内部错误分类，不误报用户输入错误或临时数据库故障。
- 仅为该错误分类补 WorkbenchApiError 和关联预览 UI 的不可盲目重试映射；未知临时错误和网络重试继续遵循现有行为。
- 完成条件：同一请求编号能读到异常，前端不泄漏 SQL，不丢备注，已提交后回读失败不会重复提交。

### E. 存量纠正与回滚

只读调查与修复生产数据分开。新代码和真实测试完成后，再执行受控修正。

1. 批量扫描 relation、相关成员 canonical scope、历史 before/after、committed responses；覆盖合法月份误判，区分已证实异常、正确历史语义和证据不足。不把所有月范围与当前数据不同的历史记录都判成 bug。
2. 生成精确候选清单：实体主键/版本或旧值、原因、旧 scope、新 scope、涉及的幂等记录；不打印业务密钥。不存在稳定证据的项保留未解决说明，不猜改。
3. 复用 relation/幂等 repository 和既有审计事务模式，增加一个窄的维护命令。若缺少 scope-only repair 能力，只增加相应方法；不挤进 requirement-repair 等无关业务命令，不做通用修复框架。
4. 同事务加现有适用锁，比较旧值/updated_at/现有版本后写新值，竞争失败就回滚；无需新 hash 或快照门禁。
5. 纠正 relation 表 scope 与 normalized payload 的对应字段；保持 status、members、amount、mode、拓扑版本。追加明确 scope repair 审计，不能让它成为“最近一次确认”并改变撤回拓扑。
6. 原四条 relation history 保持原貌；新的撤回逻辑基于 target members 计算 scope，确保旧错误月份不再传播。审计详情仍展示当时事实及修复记录。
7. 对证实受影响的三条 committed responses，定点纠正范围元数据并记录旧/新字段审计；保留请求、key、fingerprint、状态、case、原业务结果和原事件标识。不删除记录、不重发业务事件、不在 replay 热路径动态重算。若历史成员/日期证据不足，则不自动修正该响应。
8. 验证第二次执行零变更；scope-only 修正不能额外触发 OA 支付重算。现有 reconcile signature 仅包含 status/version/members，应通过真实测试确认这一点，不禁用正常业务 outbox。
9. 回滚只还原本次受影响且仍匹配修复后值的字段，保留新增审计。存在后续业务改动时拒绝覆盖新事实，列出差异。

备份策略：优先使用本次精确修正行的临时前值副本；如既有正式流程要求额外备份，仍遵守现有保护。本次不做 schema 修改、不删业务事实，不为几个 scope 字段自行扩大成全库备份项目。上线及数据验证完成后自动清理本任务创建的备份、临时副本和回滚导出，记录清理结果。保留原始业务审计及修复审计；不删除用户已有备份、其他任务文件或主数据库。未完成验收时不提前清理恢复材料、不宣称任务结束。

### F. 性能与跨页面验证

- scope 计算只遍历本次 descriptor，加月份集合去重排序；不新增逐行 I/O。
- confirm 复用现有事务 selection 查询，scope 本身新增 SQL round-trip 目标为 0；撤回复用既有 current/predecessor canonical 批量载入。任何额外查询须说明缺失事实及实测成本。
- 保持一次 mutation + 一次 canonical GET，不新增轮询、缓存、read model、worker、全历史扫描或更长 timeout。
- 隔离库以 11 成员为核心样本，并在现有业务数量上限内选择 100、500 成员或相应允许规模测完整提交/撤回；先核对现有上限，不为压测扩大接口能力。记录查询数、DB 时间、提交时间、GET 时间和 DOM 可见时间；不能以原来的快速失败 589ms 作为成功性能基准。
- 相同成功 fixture/环境作前后比较；沿用现有读 API p95 <=1000ms、p99 <=2000ms，成功响应至页面可见 p99 <=3000ms。声称 p99 通过须满足既有至少 100 样本要求，样本不足标记未测，不新增阈值 gate。
- 生产仅认证、有界、只读采样；压测、合成写入和数据库失败注入在隔离 test 数据库执行。
- 回归页面：关联台、银行明细、OA 待付款、待找发票、进项使用、销项收款、成本统计，以及共享关系 writer 的 ETC、批量账务、免 OA、往来款。验收金额/成员/状态/总数、月份过滤、跨月 case 完整性、排序分页、权限、导出及正常读返回。
- 不承诺绝对零回归或未经测量的耗时；出现退化须定位并处理，不能把验收阈值调宽或改返回内容掩盖。

### G. 文档、正式发布与收尾

- 更新直接 owner 的 `boundary-io.md`、state-machine、tests：真实 scope 输入、内部 I/O、旧逻辑删除、历史恢复和修复责任。
- 仅更新实际受影响的 API 和数据修复运维文档；本次不修改日志读取 helper 或发布架构。
- 相关模块保留的 read-model 历史叙述不能用于设计；此次更新与本链相关的过时内容，不顺带重写整棵文档树。
- 在实际发布获授权后，使用 `scripts/deploy-oa.sh`，保留既有正式发布验证和上一 release 回滚能力；不手工覆盖运行目录。
- 发布后重新调查候选再修数据，避免使用过期列表。真实用户 437 元关联的确认只能在用户授权执行该业务动作时提交；不能为验证擅自修改真实关联。隔离环境必须完整验证同构业务链。
- 完成只读生产验证、必要的既有发布观察和本任务备份清理后，交付文件清单、删除清单、实测耗时、测试结果、数据修正数量、未解决项。若回滚代码会恢复 ID 推断，明确仍存在原 bug，不能把“服务恢复”当“修复完成”。

## 5. 七类测试及执行入口

| 类别 | 本次要求 |
| --- | --- |
| 业务单元 | 日期归并、合法/非法随机 ID、跨月/单月/null、canonical scope 独立于 ID；新行为用真实 resolver |
| Service/repository | 内部 scope I/O、UoW 回滚、history 与幂等原子性、scope-only 修正/重复执行/回滚冲突 |
| API | confirm/withdraw DTO、错误码、权限拒绝、重复 key/冲突、旧成功 shape |
| read model/cache/job | read model/cache 不适用：本次无相关运行时；既有 OA outbox 成功一次、失败零事件及修正无额外事件适用 |
| 前端 | 成功一次 GET、备注/错误、重复点击、提交成功但回读失败、已有临时错误重试 |
| E2E | 真实 PostgreSQL 的 3:1:7 确认 -> 同组读取 -> 下游 -> 撤回 -> 历史恢复；浏览器同链映射 |
| 旧功能回归 | 关系生产者、跨月页面读取/筛选/导出、成员/金额不变、历史与幂等传播路径 |

首先运行受影响的现有测试文件；新增测试尽量放入原文件，维护 CLI 确有新模块时才建立对应测试文件。

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_page_selection_repository \
  tests.test_workbench_relation_command_service \
  tests.test_workbench_relation_repository \
  tests.test_workbench_uow_contract \
  tests.test_workbench_auth_context_idempotency \
  tests.test_workbench_postgres_idempotency_repository

# 实施时提供本任务隔离 test DB；测试工具不得指向生产库。
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_query_postgres_integration \
  tests.test_workbench_pending_oa_relation_lock_postgres_integration

cd web
npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx
npx playwright test e2e/workbench-relation-fanout.spec.ts e2e/workbench-withdraw-flow.spec.ts e2e/workbench-permissions-flow.spec.ts --project=chromium
```

真实跨页面 fixture 补入现有 PostgreSQL integration；其余相关 relation/ETC/往来款测试按触及文件执行。最终运行既有 `bash scripts/verify.sh lint`、`backend`、`frontend`、`docs` 及 `git diff --check`，沿用正式发布要求。失败修正后只重跑受影响项，最后进行一次必要的汇总验证，不循环执行全部检查。

## 6. 再次自审

| 用户要求 | 审阅结论 |
| --- | --- |
| 模块化、清晰 I/O | 通过：repository 供 canonical scope；纯函数计算；service 编排；route 不承载业务 |
| 简单、不过度设计、完整闭环 | 通过：主链接通现有字段，最多小纯函数；存量修正是已证实问题必需，不是扩建平台 |
| 高性能 | 设计通过、实测待执行：复用 existing selection，scope 零新增查询目标；明确完整成功链测量 |
| 移除旧代码 | 通过：明确删除正则、helper、注入与 fallback；迁移所有有效消费者后删除 |
| 不污染其他页面 | 设计通过、回归待执行：公共 month_start 和 DTO shape 保持；共享 writer 生产者及下游必须测试 |
| 指出不合理理念 | 通过：绝对零 bug 无法保证；性能需实测；不能因少 gate 删除事务/幂等；备份须验收后才清理 |
| 完成后清理备份、禁止删主库 | 通过：仅本任务备份/临时副本纳入清理；主库和已有备份不碰 |
| 禁止兜底 | 通过：没有 ID/当前时间推断、吞错或双路径；允许的 null 作为明确业务输入处理 |
| 默认不加 hash/frozen contract/baseline/gate | 通过：使用主键、事务、已有锁、旧值比较和普通测试；既有正式发布保护保留 |
| 不用 GSD | 通过：普通实施计划，不调用执行器或生成 GSD 阶段编排 |

审阅发现的遗漏已纳入：scope_month 内部 DTO 丢失、合法月份静默错误、normalized payload 一致性、修复事件污染最近确认历史、scope-only 修正的 OA outbox 副作用、幂等响应稳定性、缺日期不能新增通用阻断、跨月受影响范围、生产写验证授权、本任务备份最终清理。

追加复审收紧：运维日志读取工具修改移出本次范围；性能样本遵守既有业务数量上限，不为测试扩大接口能力。这两项均不影响本次根因修复与数据闭环。

结论：修订后的计划通过复审。现已实现 canonical scope 透传、旧链路删除、事务内范围计算、恢复旧关系的范围重算、专用错误反馈及离线定点修复工具。专项 146 项测试通过，包含真实 PostgreSQL 的 437 元、3 OA/1 bank/7 invoice 确认、幂等重放、撤回、写入故障回滚和修复工具竞争/重复/恢复。前端全量 1,339 项及 10 项既有浏览器流程通过；发布、全量后端最终结果及生产验证以本次交付报告为准。
