# PostgreSQL 回归失败修复计划

日期：2026-09-08。状态：**已获执行、提交 main、推送与部署授权；修复和验证进行中**。第 1–6 节保留审阅时的计划口径，当前执行进度与新增问题以第 7 节为准，不能把计划中的“通过”当作实测通过。

关联：[现金实施与原始验证结果](cash-module-implementation-plan.md#16-闭环修复实际执行2026-09-08)、[测试入口](testing.md)、[当前架构](../../ARCHITECTURE.md)、[Read Model 退役合同](../architecture/module-boundaries/read-model-contracts.md)。

## 1. 目标、证据和授权范围

目标是恢复可信、可重复的后端回归：修复失败的真实原因，使当前业务行为得到有效验证，而不是把测试输出改绿。

本计划以 `5128d7a92` 的代码和上一轮全量结果为分析起点：4087 项、6 failure、44 error、5 skip。这是历史结果，不是必须维持的用例总数，也不是新 baseline。50 个失败/错误条目不等于 50 个独立生产缺陷；其中两个错误发生在测试类初始化阶段，可能遮住多个尚未执行的测试。

已完成的诊断证据：

- 逐条阅读 50 个失败/错误堆栈，核对相关测试、迁移和当前 owner 代码。
- 独立本地 PostgreSQL 17 库复现待找发票、OA 精确附件刷新、系统审计两项，共四个原断言失败；没有访问生产。
- 待找发票原测试提前返回 `400 workbench_relation_canonical_member_missing`。仅通过现有 repository 补齐合成 canonical 银行/发票事实、保持原断言不变后，该项通过。
- OA 精确附件刷新前后均有两条不同用途的同步记录，两条的 key、version、payload 均未变化。
- 系统审计的三项追加写触发器检查通过，仅 coverage marker 缺失。在临时库补齐合成启用标记后，17 个普通业务页面 proof 全部通过。
- 可撤销登记三组/四组差异此前在旧 release 已复现。其它问题不据此统称为已证明的历史缺陷。
- 诊断库已删除；未创建数据库备份，未改应用、测试或生产。PG17 诊断不能替代后续与生产 PG16 对齐的回归。

2026-09-08 用户已进一步授权执行修复、提交/推送 remote main、部署与生产验证。默认修复范围仍为测试、必要的测试侧 helper 和文档；不预先改变业务规则、正式迁移、数据库约束或前端。完整准备后暴露真实业务问题时，先记录最小复现、影响范围和窄修复方案，再确认新增范围。

## 2. 根因清单与处理决定

### 2.1 执行错误：44 项

| 编号 | 数量 | 位置与根因 | 决定 |
| --- | ---: | --- | --- |
| E01 | 23 | `test_workbench_query_postgres_integration.py` 的共享准备仍插入旧多档 ACL，违反 0165 的 `app_settings_page_access_accounts_guard` | 更新当前权限样例；保留原工作台业务断言 |
| E02 | 1 | `test_postgres_state_store_integration.py` 的 lost-ack 测试仍提交/读取 `full_access_usernames` | 使用当前页面权限结构，保留提交不确定性、恢复、版本、审计验证 |
| E03 | 9 | cash HTTP 两项、兼容探针五项缺普通表；direct retirement 和 ETC store 两个类初始化遇到 cash schema 重复。迁移测试清空结构、现金测试只重建 cash、迁移记录与实际结构脱节 | 明确测试库生命周期，移除常规 cash 测试中的局部重建；兼容探针不自行改变候选 schema |
| E04 | 7 | 银行规则一项查已删 dirty 表、runtime infrastructure 五项调用已删 refresh 方法、turnover 一项向已删 projection 表写样例 | 删除纯退役机制测试；当前行为转为 canonical/零旧事件断言；历史迁移测试限定历史版本 |
| E05 | 1 | 银行导入审计构造缺失流水时直接 DELETE，无 transaction-local correction reason | 合法准备测试反例，不关闭金融事实保护 |
| E06 | 1 | 银行 reset 测试未提供已有 impact/recovery receipt/job 输入 | 复用现有受控重置测试准备，保留非法输入拒绝 |
| E07 | 1 | 金融事实审计 INSERT 缺必填 `counterparty_name_raw` | 补完整合成字段，不放宽正式 NOT NULL |
| E08 | 1 | 0131 迁移验证 SQL 的字符串拼接与 JSON `#>>` 缺括号 | 只修测试表达式，保留迁移结果和约束验证 |

### 2.2 断言失败：6 项

| 编号 | 数量 | 根因 | 决定 |
| --- | ---: | --- | --- |
| F01 | 1 | 待找发票测试用内存 import + `_persist_state()` 准备数据，但该全局保存已不再负责导入事实；未到故障点便被正式关系成员检查拒绝 | 测试通过 import fact owner 准备正式数据；不恢复全局保存导入的旧职责 |
| F02 | 2 | 系统“干净”样例清空 `audit.events` 后未补启用标记，operation-history proof 正确拒绝 | 在该测试类局部准备启用标记，不改全局清空 helper，不弱化审计 |
| F03 | 1 | OA 测试将全表只有一行当成目标完整同步标记不变；实际有 source 与 projection 两种 OA integration 元数据 | 比较精确 key 的刷新前后内容，并检查无新增 key，不硬编码整表一行 |
| F04 | 1 | ETC 数据库 `numeric(20,6)` 返回 `100.000000`，测试按文本期待 `100.00` | 持久化层用 Decimal 精确比较；用户格式由已有输出/格式化测试负责 |
| F05 | 1 | 可撤销登记已包含 `bank_flow_rule_batch` 第四组，测试仍精确要求旧三组 | 登记覆盖完整四组，按实际 owner 分开验证；不只是把 3 改成 4、6 改成 8 |

### 2.3 跳过：5 项

`test_etc_backend.py` 四项和 `test_etc_reconciliation_service.py` 一项依赖个人桌面的绝对 TXT 路径。改为自包含合成样例，保留无扩展名 TXT、解析记录、不同来源模式互斥等断言。删除这五项中的文件不存在即 skip 分支；不能把真实业务样本提交进仓库。

### 2.4 顶层原因

1. 生产架构已经改变，但部分测试仍把旧权限、旧保存入口、旧 projection 当作当前接口。
2. 测试库的“当前版本”和“历史迁移版本”缺乏清晰准备/释放责任，混合运行时互相污染。
3. 一些断言在检查偶然实现细节（全表数量、数据库文本小数位），没有准确检查业务约定。
4. 单项通过未覆盖混合顺序，类初始化错误又遮蔽后续断言；专项成功不能代替全量收敛。

这不支持重写现金账架构；也不支持把所有问题都归为无须处理的历史遗留。特别是二态权限迁移后的样例遗漏和现金混合测试准备，属于需要补齐的变更配套工作。

## 3. 边界与 I/O：只在测试层解决当前问题

| 层/owner | 输入 | 输出和责任 | 禁止 |
| --- | --- | --- | --- |
| `tests/postgres_test_utils.py` | 显式可销毁测试 DSN、精确迁移版本 | 准备/清理测试结构、运行已有迁移；失败明确传播 | 使用生产 DSN、猜连接、自动重试补表、修改正式迁移 |
| 常规 PG 测试类 | 当前完整 schema、该用例合成事实 | 断言当前 service/repository/API 行为；释放连接/线程 | 私自只重建部分 schema；依赖上一用例数据 |
| 历史迁移测试类 | 已登记的迁移前版本、精确历史样例 | 验证迁移变化及重复执行，退出后恢复干净当前结构 | 在最新 schema 中复活旧运行链；让旧结构留给下一类 |
| 旧代码/新 schema 兼容探针 | 调用者已准备的精确候选 schema、被指定的旧代码 | 固定写探针及现金哨兵不变证明 | 在探针内部再 apply“最新迁移”，改变正在验证的候选 |
| Settings/permissions 测试 | 当前 `page_access_accounts`、版本、明确 actor | 页面二态 ACL、005 权限、持久化/恢复结果 | 默认给全部页面授权、恢复旧档位或 OA role 反向授权 |
| Import/pending-invoice 测试 | 合成 import facts、明确关系命令 | 经现有 fact repository 准备，真实命令及失败状态落库 | 把测试准备代码塞进 route/global save；mock 掉被测事务 |
| Audit/reset 测试 | 局部启用标记、合法纠错/reset 输入及非法反例 | 真实保护、生效/拒绝、事务/审计结果 | 全局伪造审计健康、删除触发器、取消恢复凭据 |
| OA/ETC/关系测试 | 精确同步 key、Decimal 金额、按 owner 的操作 | 不变性、正确数值、完整提交/撤回及幂等 | 改生产金额精度、增造元数据、跨模块共用不适合的 UoW |

现金仍是同一生产 PostgreSQL、同一登录账号、独立 cash 表；普通页面不读现金、现金不读普通流水、不写全局历史。测试临时数据库不是第二个生产数据库。本次没有前端、API DTO、业务金额、正式表字段或生产 worker 设计变更。

## 4. 可执行实施顺序

以下是工作单元，不是逐项审批门禁。R1 → R2/R3/R4 → R5 → R6；默认串行推进，不创建多 agent 或新测试调度系统。

### R1：修复测试库生命周期（E03，先执行）

文件范围：`tests/postgres_test_utils.py`、`test_postgres_test_utils.py`、`test_cash_core.py`、`test_cash_runtime.py`、`test_cash_http_integration.py`、`test_cash_schema_compatibility.py`，以及已有破坏性历史迁移类的生命周期部分。

1. 使用显式、独占、名称满足现有 `fin_ops_cash_test_*` 保护的本地 PG16 测试库；普通和 cash 测试变量可以明确指向该库，但禁止并发运行会 reset 同一库的套件。外部 OA/对象存储仍用现有测试替身，不加载生产 token。
2. 常规当前版本测试类复用 `apply_test_migrations()` 准备完整结构，再准备自己的数据。移除 cash core/runtime 常规测试直接 DROP cash 后手工执行部分迁移的路径；0167 授权验证继续保留。
3. 历史迁移类复用 `reset_test_database()` 与 `apply_test_migrations_through()`，只在精确历史版本上构造旧字段/表。类退出恢复动作先清掉合成反例，再应用当前完整迁移。恢复必须在破坏性准备开始前注册到 class cleanup，包含初始化或断言失败路径；普通用例不每笔重建全部迁移。
4. `CashClosureMigrationTests` 属于迁移测试而非普通 cash 用例；保留原事实不变/三列适用性验证，但不在保留当前迁移记录的情况下只重建 cash。HTTP 普通池不变验证必须拥有真实普通表，不能换成虚假替代表。
5. 已扫描的迁移 reset 调用方包括 canonical contracts、settings ACL、invoice provenance、OA source alias、ETC summary anomaly、workbench reviewer identity；只统一生命周期，不改变各自迁移业务断言。runtime infrastructure 的 0008→0009 测试与当前队列测试分开生命周期，避免同类中的版本污染。
6. 兼容探针维持 caller-owned schema；测试执行前准备完整精确候选。清理只针对该探针创建的 ID，先验证现金哨兵未变再清理；不把清理当验证成功。
7. 只复用或补一个确有多处调用的测试侧恢复 helper，不引入抽象基类、registry、数据库池工厂、容器编排器。清理错误仍是错误，不吞异常，也不让恢复动作替换原失败报告。

验收：正常/失败退出均释放 HTTP server、线程和连接；历史迁移类→cash HTTP/兼容→普通查询的相邻组合正序与反序均能运行；最新普通表、cash 表及迁移记录一致；重复执行该小组合不出现缺表、重复 schema 或残留自有记录。先测小组合，不反复运行全量 4000 余项定位。

### R2：同步二态权限与事实准备（E01/E02/F01）

1. `test_workbench_query_postgres_integration.py`：局部样例改用当前 `page_access_accounts` 和版本，并保持 `raw_payload.normalized_payload` 一致。不能给无关测试账号补全权限；原有 23 项查询、分页、语义和查询次数断言全部继续执行。
2. `test_postgres_state_store_integration.py` lost-ack：提交当前字段，检查恢复 snapshot 的页面集合、version、mutation audit，并确认旧字段不再输出。继续覆盖“提交已成功但响应未知”，不得改成普通成功测试。
3. `test_app_postgres_mode_integration.py`：数据准备经现有 `import_fact_repository` 的明确持久化入口；本例是测试夹具，不恢复 `_persist_state()` 对导入事实的所有权。确认准备出的 IDs 可从 canonical 表读到，再注入 relation-created 后故障。
4. 保留/验证 command 的 `failed_recoverable`、`last_successful_status=relation_created`、正式关系和命令持久化；用相同 request 重放验证不重复关系、不重复有效副作用，并核对正常读取结果。没有到达故障点时不得算故障恢复覆盖。

验收：23 项工作台测试真正执行到业务断言；当前页面权限、005-only、拒绝/撤权、版本冲突和全局历史排除 cash 继续通过；待找发票原持久化失败恢复意图得到真实 PG 证明。

### R3：精确清理退役测试（E04，含被 E03 遮蔽的历史测试）

1. `test_runtime_infrastructure_postgres_integration.py`：删除五个专门验证已删除 refresh API 的用例，以及删除后确实无调用的 import/helper。保留当前 outbox 的去重、lease、attempt、retry、heartbeat、事务等测试，不能整文件删除或泛化成假的成功接口。
2. `test_app_postgres_mode_integration.py`：银行规则保存断言使用当前版本、审计、实际允许的领域任务和 canonical 结果；证明不存在已退役对象/没有新旧刷新事件。不能要求规则变化永远不产生任何合法领域任务。
3. `test_turnover_ledger_postgres_integration.py`：删除在当前 schema 插入退休 projection 行的准备；用真实 canonical 输入验证往来结果，并确认物理退休对象不存在。
4. `test_direct_canonical_runtime_retirement_migration.py`：0127 迁移仍值得验证，但应从 0126 开始构造样例，执行并验证 0127、重复执行不变；不要在已应用 0149 的 schema 中建回旧表。退出按 R1 恢复当前结构。
5. 删除前后扫描入口、调用方、测试引用、脚本和文档。历史迁移 SQL、既有校验、当前 outbox/worker、OA integration 的同步元数据不是本次删除对象。

验收：旧方法/表不作为最新 runtime 测试的依赖；`test_read_model_runtime_removal.py`、`test_retired_projection_event_audit.py` 和当前队列/worker 测试通过；历史迁移测试保留精确验证价值。

### R4：修正审计、金额、SQL、OA、登记与 ETC 样例（其余条目）

| 文件/范围 | 精确动作 | 必须继续证明 |
| --- | --- | --- |
| `test_audit_app_health_system.py`（F02） | 在该类 `_seed_clean_system` 中局部准备一个合法启用标记。全局 truncate 仍可清空 audit，避免改变其它测试的初始计数 | 正常系统 17 个普通页面 proof 通过；缺 marker 的明确反例仍拒绝，cash 不加入全局审计 |
| `test_audit_bank_transaction_import_page.py`（E05） | 缺失流水反例在同一事务设置已有 actor/correction reason 后精确删除 | 无原因拒绝、合法纠错留痕、删除后 orphan audit 检出 |
| `test_postgres_state_store_integration.py`（E06/E07） | reset 使用已有合成 receipt/job/impact 准备；银行事实样例补必填对方名 | 未授权/无凭据/漂移拒绝；合法 reset 的可重试文件清理；金融事实 append-only 和 before/after 保护 |
| `test_canonical_finance_domain_contracts_postgres_integration.py`（E08） | JSON 提取表达式加明确括号 | 0131 归一化结果、约束 validated、非法状态拒绝仍准确 |
| `test_oa_pending_payment_postgres_integration.py`（F03） | 刷新前记录精确 source key 与完整 key 集合，刷新后比 key/version/payload；不再预设整表一条 | 指定附件数据更新、完整同步标记不推进、未选中 OA 不变、无凭空新增同步 key |
| `test_postgres_state_store_integration.py`（F04） | 数据库标量以 Decimal 精确比较，不采用 float/tolerance 或改 schema scale | 保存/读回金额精确相等；已有序列化和 UI 金额格式责任不混入 DB 文本表示 |
| `test_reversible_relation_closure_postgres.py` 及既有 bank-flow-rule 测试（F05） | 分离“登记完整性”与“owner 执行证明”。登记明确四组；原三个 relation owner 的事务测试保留。第四组复用/补强银行规则批次 owner 的提交/撤回测试 | 第四组真实 batch/event/relation 原子性与重放，不用 Workbench 伪 checkpoint 代替；不能只增加常数或忽略第四组 |
| `test_etc_backend.py`、`test_etc_reconciliation_service.py`（5 skip） | 复用现有文本样例模式，补自包含合成 TXT 字节/最小样例；去掉桌面绝对路径和因本地样例缺失跳过的分支 | 无扩展名 TXT 走正确 parser、多条记录/金额/车牌、TXT/粘贴/PDF 来源冲突的 409 和具体 error、非法输入拒绝 |

若第四组已有等价真实 PG 事务测试，则直接复用并记录映射；若缺失，只在其 owner 测试文件补最小用例，不新增统一可撤销框架。登记断言由业务预期定义，不能把登记表自身再抄一遍作为“预期”而失去检错能力。

复审补充：`test_bank_flow_rule_batch_application_service.py` 中存在记录调用和修改内存状态的测试替身，不能凭文件名或用例名把这些结果计为真实 PG 事务证明。实施时将登记测试、service 替身测试、真实 PG 提交/撤回测试分别标注；第四组沿现有 `BankBatchApplicationService` 的真实持久化路径验证，不新增统一事务执行器。

### R5：分层回归、耗时记录与结果核对

实施时先准备明确的本地 PG16 空测试库并设置既有两个 test DSN；不在这里提供可误连生产的默认 DSN。保留现有保留库名/显式测试库校验。记录实际 PG 版本、测试组、数量、failure/error/skip 和耗时。

执行环境责任补充：`scripts/verify.sh` 的 `run_backend()` 会先调用 `run_clean_app_check()`；后者读取的是运行时 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL`，不是两个 test DSN。因此，只设置测试连接不能证明整个命令只访问测试环境。实施时在独立测试子进程中清除继承的 `FIN_OPS_POSTGRES_DATABASE_URL`、`DATABASE_URL`、`FIN_OPS_APP_STORAGE_BACKEND`，保留明确赋值的 `FIN_OPS_TEST_DATABASE_URL` 和 `FIN_OPS_CASH_TEST_DATABASE_URL`；让已有 clean check 验证未配置 PostgreSQL 时的拒绝启动分支，随后集成测试通过自己的测试连接运行。不要 source 生产 env、加载生产 token 或输出环境变量值；不得把生产连接复制到 test DSN。此为现有入口的运行方式说明，不新增环境加载器或检查门禁，也不修改共享验证脚本来掩盖失败。

使用现有入口，不新增验证框架：

1. 每组修完只跑该文件/类；在仓库根目录使用 `PYTHONPATH=backend/src:tests python3 -m unittest tests.<测试模块> -v`，避免漏掉源码/测试 helper 的导入路径。所有单项与组合命令沿用上述独立测试环境；这是待实施运行的命令格式，本轮没有执行业务测试。
2. 运行 R1 顺序/反序小组合，覆盖历史 schema→当前 schema、cash→普通/普通→cash；同一库串行，不靠重排默认 discover 顺序掩盖问题。
3. 运行当前权限、现金、普通关系/银行/往来/待找发票、OA、ETC、审计/reset、迁移与 runtime owner 回归；保留非法输入、事务失败、幂等、版本冲突、未知状态和清理失败覆盖。
4. 运行 `bash scripts/verify.sh lint`、`bash scripts/verify.sh backend`、`bash scripts/verify.sh docs` 与 `git diff --check`。backend 必须实际启用 PG 测试变量；环境缺失的大量 skip 不算真实 PG 通过。全量末轮一次，失败后仅复现受影响组，修正后再跑完整收尾。
5. 单列精确候选 schema + 旧代码兼容探针；它不是任意当前 schema 的常规单元测试，也不能被全量 discover 的混合上下文代替。
6. 汇总删除/迁移/新增测试的业务意图对应关系：原 50 个条目逐一记录原测试标识、根因编号、保留/迁移/删除理由、承接业务断言的测试及实际结果，5 个本地样例 skip 不再静默发生。这张结果表直接写入本计划，不另建 registry、manifest 或覆盖率平台。总数可以变化，但不能通过取消发现、放宽断言、增加 skip/expectedFailure 或删有用覆盖来清零。

七类测试适用性：

| 类别 | 本次责任 |
| --- | --- |
| 1 业务核心 | 适用：权限、金额、输入/状态、幂等等现有约定的断言修正与回归，不改变规则 |
| 2 服务层 | 适用：PG 持久化、提交不确定性、失败恢复、审计、reset 和资源释放 |
| 3 API | 适用：待找发票及 ETC 的正常/冲突/故障状态与关键返回字段，不只 HTTP 200 |
| 4 查询/任务 | 适用：canonical 读、精确 OA 更新、当前 queue；保留查询次数/分页断言。现金无新缓存或 worker，不为不存在机制添加测试 |
| 5 前端组件 | 默认不新增：无 UI/前端组件改动。若后续发现必须改真实响应或权限行为，需扩范围确认，并追加相关 Vitest/浏览器验证 |
| 6 端到端业务链 | 适用：真实 PG/HTTP 的准备→命令→失败/重放→读取、cash/普通事实互不变化，第四组批次真实提交/撤回 |
| 7 既有功能回归 | 适用：全量后端及影响模块；测试 helper 变化需要混合顺序/重复运行证明 |

性能策略：不改生产请求路径，因此不承诺这次让银行/工作台变快。保留已存在查询数量与有界分页断言，测测试准备/执行耗时，避免普通每个用例重放 168 个迁移、并发 reset 争锁、全量重复初始化。若需要提速，先定位测试耗时再复用类级准备；不加缓存、hash 或不透明“初始化已完成”标记。

以前银行/工作台并发尾延迟未达标属于独立、仍未关闭的问题；本次测试全绿不能替代性能验收。只有发现并获确认要改生产 SQL/service 时，才按现有指标测量对应 GET 的 p50/p95/p99、错误数与 query count，不新设性能门禁。

### R6：文档、收尾和是否发布

- 更新本计划的实际结果，并同步 `docs/dev/testing.md`、cash 的测试/实施记录，以及实际改变测试责任的模块 `tests.md`。已有历史数量保留为历史，不冒充本次通过。
- 文档核对发现当前入口仍混有旧 read-model/权限说明；仅修正与本任务有关的当前操作指引，历史记录明确归档语义。以 `ARCHITECTURE.md`、0149 和现有 owner 为准，不让陈旧文字诱导恢复旧接口。更大范围文档治理另列，不借本任务全仓改写。
- 无生产模块边界/I/O/表结构变化时，不重写前端设计、业务设计或数据库设计；若实际测试边界/文件范围变化，更新对应模块文档即可。
- 清理本任务独占的测试库、连接、临时目录/样例/输出；删除前核对精确名字和所有权，失败要报告，禁止吞清理异常。保留原 Excel、用户文件、主数据库、既有备份和生产 release。
- 不设计生产数据库备份，也不连接生产执行重置、建角色、写 OA 或造真实现金数据。若以后发现需正式迁移/备份，先提出独立窄方案并确认；不可借本计划删除任何现有备份。
- 若最终只改测试和文档，**无需为了测试变绿重启或重新部署生产**。提交、推送、合并和发布仅在之后获得明确执行授权时进行；若确有已获授权的 runtime 修复，再走已有发布入口及已有安全检查，不新增 gate。

## 5. 旧代码清理清单与保留条件

应移除：最新版本测试中的旧权限字段、对已删 refresh 方法/表的正向依赖、常规 cash 测试私自局部重建、旧全局保存导入式测试准备、无意义金额文本格式断言、个人桌面样例路径及静默 skip、删除上述内容后无调用的私有测试 helper/import。

必须保留：所有已发布迁移；精确历史升级测试的旧字段/对象；当前 outbox 和四个 worker；金融事实/审计/reset 保护；cash 的同库同账号、双向模块读取隔离与全局审计排除；普通 App 的既有 cash-special；固定旧代码/新 schema 兼容探针。

没有调用关系证据，不删除公共实现；代码旧不是删除理由，仍承担当前行为的代码不得删除。不新增生产 fallback 或兼容旧输入分支。

## 6. 复审与未决边界

| 用户要求 | 本计划复审 |
| --- | --- |
| 模块化、清晰 I/O | 通过：fixture/schema/owner/API 分责；测试准备不回流生产全局保存 |
| 简单完整、不过度设计 | 通过：复用 unittest、既有 helper/repository 和模块测试；无新平台、框架、工厂或多套运行时 |
| 高性能 | 范围明确：不动线上热路径、按组验证、类级准备；保留查询预算。不能把测试修复当性能优化 |
| 清除污染旧链 | 通过：删除失效测试依赖，保留历史迁移与安全措施，删除前后扫描调用方 |
| 不影响其它页面 | 最小风险方案：默认应用代码零改动，真实 PG 全量/隔离回归。无法数学保证零 Bug，不作绝对承诺 |
| 备份/数据库安全 | 无生产备份计划；只清理精确任务测试资源，禁止删除主库/用户备份 |
| 无兜底 | 通过：错误明确、无重试补表/恢复旧 API；显式测试生命周期清理不属于业务 fallback |
| 不新增 hash/冻结 contract/baseline/gate | 通过：只用既有 Git、类型、事务、唯一约束、迁移工具及普通测试，不削弱已存在保护 |
| 不用 GSD | 通过：本计划和现有入口即可；没有 GSD 执行或自动任务 |

仍须诚实保留的边界：

1. 23 项工作台测试及类初始化被阻断的测试，准备修好后才会执行后续断言，可能暴露更多实际问题；不能预先宣布全量必过。
2. 第四组银行规则批次必须完成 owner 级覆盖核对；不能把注册项更多直接当作代码冗余，也不能套错事务实现。
3. 缺失的真实 ETC 样本无法证明其全部未知格式都被覆盖；本轮保证五个原测试的明确业务意图由合成样例执行，真实新格式仍需真实样例。
4. 不因“不能影响其它页面”而跳过跨模块回归；也不因“完整闭环”扩张成整套 UI/架构重做。

设计阶段复审结论（2026-09-08）：补齐现有 backend 入口的运行时/测试连接分离、单项命令导入路径、替身与真实 PG 证据区分、逐项测试迁移去向；不增加实施阶段或审批门禁。当时仅完成文档，不将计划通过标为修复通过；随后获实施授权，实际结果见 §7。

设计阶段结论：计划可执行，不需要新增生产架构。实际状态见下节。

## 7. 执行记录（2026-09-08）

### 7.1 范围与环境

- 实施起点 `main=origin/main=5128d7a9260be1946ae514f6e5d575c31dd0dabe`；执行前四个计划文档是本任务已有变更，没有覆盖其它代码修改。
- 本地独占 Docker PostgreSQL 16，端口只绑定 `127.0.0.1:55438`，库 `fin_ops_cash_test_regression_20260908`。未访问生产做测试准备，未创建备份、未修改主数据库、未创建生产角色。
- 常规 cash core/HTTP/runtime 准备完整 schema，保留实际库名保护并在迁移/清理前检查。现金隔离哨兵改为真实 `app.bank_transactions`，不再创建伪普通流水表。
- 六个历史迁移类、cash 0168、direct retirement 0127、runtime 0009 均明确历史版本及 class cleanup；只复用一个恢复 helper。runtime 当前队列测试迁移准备上移到类级。
- 已删除五个纯退役 refresh 测试；保留 outbox/lease/attempt/retry、历史迁移、兼容探针及金融事实保护。未恢复旧方法、旧表或全局保存导入职责。
- 新增 schema 恢复顺序/失败传播/初始化失败清理测试、真实银行规则批次事务测试、待找发票重放、缺审计标记反例；ETC 五个原 skip 改为合成样例，不再读个人桌面文件。

### 7.2 原失败项承接与新增发现

| 原因 | 实施与断言承接 |
| --- | --- |
| E01/E02（24 项） | 当前二态 ACL fixture、原工作台 23 项业务测试与 lost-ack 恢复继续执行 |
| E03（9 项） | 完整当前 schema / 精确历史 schema 生命周期分离；cash HTTP 普通事实表、五项旧代码兼容写探针保留 |
| E04（7 项） | 删除五个退役 API 测试；银行规则验证零旧 refresh 事件；往来在 canonical 空/实数据上验证，断言旧表不存在 |
| E05/E06/E07/E08（各 1 项） | 合法纠错原因、既有 reset receipt、必填对方名、JSON 提取括号；原失败/回滚/约束意图保持 |
| F01 | import fact owner 落库后真正到达故障点；同 request 重放，命令完成且关系成员唯一 |
| F02（2 项） | 局部 coverage marker；17 页健康正例与缺 marker 拒绝反例 |
| F03 | 精确 OA watermark key/version/payload 及完整 key 集合刷新前后相等 |
| F04 | Decimal 精确数值比较；同样修正被初始化问题遮住的金融纠错 JSON 数值文本断言 |
| F05 | 完整四组登记；三组旧 UoW 保留，第四组实际 HTTP→PG 提交/撤回/重放/事件异常回滚，不冒充统一 checkpoint |
| 5 skip | 自包含 TXT 多记录/车牌/金额样例；三项原意图已执行，另两项暴露以下真实上传问题，未以 skip 或改期望掩盖 |

新增发现：

1. 工作台统一搜索样例显式插入 `+08` 时间却假设数据库 session 也是中国时区。Docker 默认 UTC 导致文本不同；测试类现以 `PGTZ=Asia/Shanghai` 明确原样例时区并退出恢复，不更改生产时区/SQL。原日期搜索断言保留。
2. 银行规则审计已持久化到 PostgreSQL，`AuditTrailService.as_dicts()` 只返回隔离单测的内存 entries。测试改查 durable action/outcome，并验证合法重算 job；不能因内存列表空而称生产漏审计。
3. **ETC 无扩展名 TXT 真实失败**：原五个跳过测试恢复后，两项 API 返回 `400 invalid_document_upload`，未到正常导入或已有 PDF 的 `409 ticket_root_source_mode_conflict`。原因是 `inspect_untrusted_document` 在解析前要求受支持后缀。此处不是金额/样例问题，也不能把文件名改成 `.txt` 让测试变绿。本轮已向用户请求窄范围确认：只在票根入口识别有效纯文本，保持共享上传策略、资源限制、签名和其它入口不变。**确认前不改应用边界，不宣布测试全绿或部署完成。**

### 7.3 验证与交付状态

第一批 128 项执行到业务断言后暴露时区、数值文本及第二处旧 dirty 查询；均已定位修正。正向混合 109 项发现新增测试 SQL 通配符需参数化；反向混合 126 项发现新增缺标记反例应检查 system 聚合错误而非子页错误码；这些测试侧问题均已修正并由后续全量运行确认。

完整真实 PG16.14 回归：`bash scripts/verify.sh backend` 实际运行 **4093 项，4091 通过、2 failure、0 error、0 skip，372.968 秒**。原 50 个错误/失败项的修复或退役承接已执行；五个桌面样例 skip 不再存在。剩余两个 failure 均是 §7.2 的同一 ETC 无扩展名上传问题，不是原断言被放宽后的“绿”。

最后一轮数据库生命周期复验覆盖 cash 0168 历史迁移、cash HTTP、cash schema compatibility、工作台 PostgreSQL 查询、runtime infrastructure：正序 **56 项全部通过，63.474 秒**；反序 **56 项全部通过，60.441 秒**。两轮使用同一临时数据库，验证当前与历史 schema 准备/恢复在这两种执行顺序下可连续运行，并非保证所有可能排列均已穷举。

`bash scripts/verify.sh frontend`：**96 个文件、1230 项全部通过，306.17 秒；生产构建通过，4.45 秒**。保留现有 chunk >500 kB 提示及 Node/React Router 提示，未通过调整 warning 阈值隐藏，也未借此扩张前端重构。

`bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 均通过。测试七类中 1–4、6、7 适用并有对应修改/回归；第 5 类没有新增组件测试，因为 UI 未改，但已复跑完整前端回归。本轮没有新依赖、正式迁移、生产 hash/contract/baseline/gate 或业务 fallback。

现有生产只读状态检查：API 与四个 required worker active，实际 WorkingDirectory 仍为 `main-20260908-cash-closure-final/src`。未切换 release，未写 OA/现金或创建受限角色。既有银行/工作台尾延迟风险未因测试修改而关闭。

Git 再次 fetch 确认 `HEAD...origin/main` 左右差异均为 0，remote main 仍为 `5128d7a92`；本任务修改保留在工作区，**尚未 commit/push/deploy**。原因是暴露了需确认的真实上传行为，不将已知失败包装成完成。获窄范围确认后应完成 ETC 入口与拒绝路径测试，复跑相关及全量回归，再从已推送 main 经现有 deploy helper 发布，并做授权范围内生产只读浏览器与 p50/p95/p99 验证。

暂停前已确认临时测试数据库没有其它客户端连接，随后移除本次独占测试容器 `finops-cash-regression-20260908` 及其匿名数据卷，并清理本次 `/tmp` 日志目录；关键结果保留在本节。删除的是可重新生成的测试数据和临时日志，没有创建或删除生产备份，没有触碰本机既有数据库、主数据库或其它容器。下次继续时需重新建立同等隔离的测试环境。

### 7.4 银行排序修复期间的再次全量验证

随后用户另行授权[银行同时间排序修复](bank-same-time-ordering-repair-plan.md)、commit/push all changes 到 main 后部署。本节旧测试修复与文档随该提交一并交付；ETC 运行时上传策略仍待单独范围确认，不能将银行发布写成 ETC 已修复。

重新建立独占 PG16 库 `fin_ops_cash_test_bank_order` 后，最终完整 `bash scripts/verify.sh backend` **4121 项，4119 通过、2 failure、0 error、0 skip，499.114 秒**。新增银行用例和旧账户测试迁移已纳入 discover；仅余相同两个 ETC 无扩展名 API 用例，没有新的跨模块失败。银行发布继续走既有受控发布检查，不绕过检查、不恢复 skip 或修改期望值消除 ETC 失败。
