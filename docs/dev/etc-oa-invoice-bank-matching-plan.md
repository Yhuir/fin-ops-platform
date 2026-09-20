# ETC、OA 与银行流水关联闭环实施计划

日期：2026-09-20。状态：实现及本地验证完成，生产发布结果见任务验证报告。

本计划采用直接实施和现有验证入口，不使用 GSD，不增加项目管理框架。仅记录实施决策，不把本计划描述为已经上线的行为。

## 1. 目标与业务口径

1. ETC 批次已提交且对应 OA 身份已经确认时，持久化 OA＋ETC 汇总发票的正式关系，关联台同组展示；无需等待流水或 OA 审批完成。
2. 对应流水在提交前已经存在，或提交后才导入，均进入同一自动匹配链，补入原关系；不得生成重复关系或丢失批次成员。
3. OA 进行中不阻止三项配对，不单独成为未配对原因。关系成员和其他既有完成条件满足时进入已配对区域，OA 标签继续显示进行中。
4. 审批、支付、关联分别表达。配对不得修改 OA 审批状态，也不得让进行中 OA 提前取得成本确认资格。
5. 来源身份能够证明的 OA＋ETC 关联不以金额相等为前提。OA 应付额、ETC 发票合计、补充凭证金额分别保留；银行自动核对以 OA 应付额为目标，发票差额按原有异常规则显示。
6. 金额相同不是业务身份。自动加入银行必须有有效收款证据、正确方向/币种、适用日期和唯一归属。明确的部分付款可保留关系，自动推断仅处理唯一可证明的候选，不按任意子集凑数。
7. OA＋发票但缺流水时仍为同一个待补全组；三项都有但存在金额/材料异常时沿用既有异常展示与审阅规则，不因本次需求绕过它们。
8. 已证明的来源关联与尚未证明的银行匹配独立收敛：银行候选缺失、重复或搜索达到既有资源上限，均不得阻止安全的 OA＋ETC 关系落库。来源身份本身冲突则只隔离受影响批次，保留明确错误；不把业务歧义与数据库/事务失败混为同一种可忽略情况。

## 2. 已确认事实与未决技术事实

生产样本：业务批次 `etc_business_batch_241146`，外部批次 `etc_20260915_001`，提交批次 `etc_batch_0047`，47 张发票、合计 1711.33 元。

- OA：`oa-pay-0121b3b5-b0de-11f1-b875-024207e7fd4a`，杨丽萍，支付申请，2026-09-15，收款方刘树刚，1711.33 元，进行中。
- 银行：`txn_imported_b7359de3ef7f4fafa862f76792aa9ac9`，2026-09-14，刘树刚，支出 1711.33 元，备注 ETC还款。
- 批次已经人工确认提交，但 `oaRowId` 为空；已同步 OA 的 `etc_batch_id` 为空。
- 草稿 ID `6aa8ff2569252c470e7d59d4` 与正式文档 ID `6aa8ff4969252c470e7d59d5` 不同，不能直接当作同一标识。
- 生产查询返回三个 `no_active_relation` 独立组。

代码与内存复现确认的问题：

| 问题 | 当前位置 | 必须改变的行为 |
| --- | --- | --- |
| ETC 候选及提交校验只读 completed OA | `postgres_repositories/workbench_formal_relation.py` | 接受同一事实合同内的 completed 和 admitted in-progress OA |
| ETC 只能补入已有 case，没有 case 就跳过 | `workbench_matching_orchestrator.py::_resolve_etc_batch_links` | 明确来源关系可直接生成初始 OA＋ETC 正式计划 |
| ETC summary 没有完整进入 matcher facts | 同上 repository 的 `load_batch` | 初始匹配与关系扩展都得到完整 typed summary facts |
| 支付申请的三字个人收款方没有有效共同证据 | repository 的 `_oa_fact` / `_evidence_keys` | 定义支付申请收款人的明确证据，不改成通用短名称碰撞 |
| 进行中 OA 强制未配对 | `workbench_relation_requirements.py`、`postgres_repositories/workbench_page_query.py` | Python 完成判断与 SQL 分区同步去除该限制 |

已核实：OA 表单编辑器提交时仅保存已注册字段，正式单据不存在 `etcBatchId/businessBatchId`。正式 `field101` 保存全部上传附件路径；新批次记录相同路径作为准确来源身份，OA sync 只提取路径、不执行支付申请 OCR。历史样本本地没有保留路径，使用用户确认的精确 OA owner 经已有 manual-status command 补齐，禁止假设草稿 ID 等于正式 ID。

## 3. 模块与 I/O

复用现有 canonical 表、正式 relation command/UoW、OA sync 与 workbench-matching worker。没有新增 read model、缓存、轮询服务、通用事件总线或第二套候选库的需求。默认无新依赖、无新表；只有实际证明现有存储无法表达已验证身份时，才单独说明最小 schema 变化。

| Owner | 输入 | 输出与允许写入 | 不承担的职责 |
| --- | --- | --- | --- |
| ETC application/service/repository | 当前业务批次、成员、已提交决定、版本、当前 actor、已验证 OA 身份 | ETC 自有状态/精确身份、审计、同事务 matching scopes | 不直接拼 relation SQL，不改 canonical 发票财税字段 |
| OA adapter/sync | 真实 OA 表单、正式业务/流程身份、批次关联信息 | completed/admitted canonical OA、规范化批次引用、变化 scopes | 不在 GET 中访问 OA，不改审批结果，不增加支付申请 OCR |
| Formal matching fact repository | 精确变化月份、相关 typed IDs/active cases | 批量 OA/银行/普通发票/ETC summary facts、明确来源边、已有占用 | 只拥有 SQL 读取和事务内事实重验，不决定 UI 状态 |
| Pure matching engine/orchestrator | 完整 facts、明确来源边、已有关系和人工撤回记录 | 新建/扩展计划、无法唯一判断的原因 | 纯规则不做 HTTP/SQL；不按金额伪造来源 |
| Relation command/UoW | typed 计划、ETC link、当前 actor/版本 | 唯一 active relation、完整成员、历史/审计、既有支付事件 | 不把整个 Application 注入，不写外部 OA 审批 |
| Workbench canonical query/DTO/UI | 已提交事实、关系、筛选分页参数 | 一致的同组展示、paired/unpaired、真实 OA 标签和异常 | 不在浏览器临时拼组，不根据显示标签创建关联 |
| 其他页面 | 自己的 canonical query＋正式关系 | 既有银行、待付款、发票使用、成本、税金等语义 | 不把 Workbench paired 当作审批通过或成本资格 |

关键文件范围：

- 身份链：`services/etc_service.py`、`etc_business_batch_application_service.py`、`oa_adapter.py`、`mongo_oa_adapter.py` 及其现有 owner repositories。
- 匹配：`services/postgres_repositories/workbench_formal_relation.py`、`workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`、`workbench_etc_batch_link.py`。
- 正式写入：`workbench_relation_command_service.py`、`workbench_uow.py`、现有 relation/ETC repositories。
- 展示：`workbench_relation_requirements.py`、`workbench_canonical_rows.py`、`workbench_relation_grouping.py`、`postgres_repositories/workbench_page_query.py` / `workbench_page_hydration.py`、实际消费状态的 Workbench/ETC 前端组件。
- 调度：现有 matching dirty queue 事务 writer、OA sync/import producer；不增加 worker。

## 4. 顺序执行任务

### A. 把身份链和失败样本确定下来

1. 只读追踪本笔原始草稿、提交后的文档和流程，核对 OA 表单正式支持的持久字段及 existing source aliases；区分文档 ID、流程 ID、表单类型 ID、canonical row ID。
2. 找出 `etcBatchId` 未保留的确切边界，确定一种正式、可往返验证的身份传递合同。复用已验证的 OA 字段/来源引用和本地批次记录；不依赖申请事由文本，不把未注册的扩展字段视为会被 OA 保留。
3. 未来批次与历史样本使用同一个规范化身份解析入口。历史样本必须有真实来源证据；不能从同金额、同日期补造原始 OA 字段。
4. 将真实数据脱敏成稳定 fixture，先加入失败测试。至少包含审批中、无银行、银行先到、47 张批次、相同金额歧义。

交付：准确的身份往返合同、原始问题复现、当前无关联证据。若外部 OA 实际不提供任何可验证映射，明确记录这一事实并先解决该外部合同；不得改为金额/文本兜底后宣称自动关联完整。

### B. 修复来源识别和可靠触发

1. 修复 A 定位的字段传递/读取边界；OA sync 对 completed 和 admitted in-progress 输出相同的稳定批次引用，不新增一套 ETC 状态探测器。
2. 批次查询和事务内重验消费同一个“有效 OA＋精确批次身份”定义；去除 ETC 专用 completed-only 限制，但不放开删除、无效、冲突或失去准入的记录。
3. 已验证的 OA 身份通过 ETC owner 的窄端口同步到已有批次/提交事实。禁止已建正式关系而 ETC 删除入口仍因 `oaRowId` 为空认为可随意 reset。
4. ETC 提交事实及对应 matching dirty scopes 采用同一 PostgreSQL 事务；替换把可靠性完全交给提交后回调的旧路径。OA/import 继续复用各自现有事务 dirty-scope writer。
5. 覆盖批次发票月份、OA 月份及真实银行月份。本样本涉及 7/8 月发票和 9 月 OA/流水；已知关联按身份定向读取，不能因月份不在当前窗口而丢掉关系成员。
6. 幂等重放不创建新草稿、不改原金额、不重复写审计；匹配过程中新的事实到达使用现有 dirty-scope 再次处理机制，不丢更新。
7. 身份与关系变更采用当前行版本和窄字段写入；不得由旧的整批内存 snapshot 覆盖已验证的关联。相同 OA 快照重复同步不清空绑定；真正失效或身份变化必须由当前源生命周期事实证明。同步字段缺失不能直接冒充“用户撤销了关系”。

交付：提交先到、OA 先到、银行先到三个顺序都能进入同一匹配入口；业务提交成功后进程退出不丢后续匹配任务。

### C. 让明确来源直接形成 OA＋ETC 关系

1. 在现有 fact repository 批量构造 ETC summary：稳定 ID `etc-summary-<external id>`，真实发票数量/合计、币种、来源批次、已验证 OA 引用。汇总是现有 relation 成员，不新增 canonical 发票。
2. 在普通组合匹配之前处理明确来源边，允许直接产生 OA＋summary 的正式计划；已存在合法 case 时扩展原 case。单轮计划应合并，避免先写两项又重复保存同一 case。
3. 统一 create/extend 输入，将完整 typed 成员和 ETC link 一次提交现有 relation UoW。不能先写 metadata 再补成员，也不能把没有 case 的候选丢弃。
4. 同一批次只有一个有效 owner；兼容历史已关联关系的规范化输入，但不维持旧 matcher 与新 matcher 双链。冲突显式输出，不抢别的 active case。
5. OA 与 ETC 发票金额不等仍建立已证明的来源关系；按真实差额输出异常，不改 summary 金额伪装平衡。
6. 先生成独立安全的来源计划，再尝试银行扩展；银行业务歧义只放弃该扩展，不撤销来源计划。UoW 的 SQL、版本或审计失败仍整笔回滚，并通过既有 durable 任务明确失败/重试，不能吞错后部分报成功。

交付：没有银行时 OA 与 47 张发票在一个待补全组；重复运行零新关系/重复 summary/重复成员。

### D. 银行自动补入与关系生命周期

1. 支付申请以明确收款方为对象；日常报销保留已有申请人证据。申请人和收款人不得混用。
2. 复用实际 canonical 字段：能够取得双方明确账户时校验账户一致；缺少明确业务引用时，姓名至少两个有效字符且相等、同币种/支出方向、金额和日期成立且候选唯一，可按组合证据自动处理。账户明确冲突必须排除；缺账户不额外设置“一律不能自动匹配”的门槛。个人支付申请的姓名组合搜索使用申请日期与交易日期相差不超过 30 个自然日的有界窗口，允许先付款；该窗口不套用到已验证的明确业务引用，也不限制 OA＋ETC 的来源关联。日常报销继续沿用其既有审批/申请日期规则，不混改。
3. 通用公司户名规则不整体放宽。ETC 备注仅可解释业务，不单独授权匹配；不依赖先手工分类流水。
4. 银行核对目标是 OA 应付金额，ETC 发票汇总保留真实金额；有补充凭证差额时不能要求所有 pane 总额相等才能补银行。该处理限于已证明的 ETC 来源组，不放宽普通组合匹配。
5. 单笔唯一匹配优先；分笔/合并付款复用有界组合规则，仅在唯一证据和合计成立时自动处理。证据不足的部分付款仍可由既有人工关联处理，不生成任意金额子集。
6. 已有 OA＋ETC 组自动扩展保持原 case ID。ETC summary 与跨月成员必须被 fact loader 完整加载，否则明确报告输入缺失，不能静默跳过。
7. 将 ETC 的来源绑定接入既有关系恢复语义：撤回/删除银行边保留 OA＋ETC；补充凭证删除不删除来源关联；人工拒绝银行关系不会被下一轮自动重建。普通关系撤回历史规则保持有效。纯 OA＋ETC 来源组不通过关联台的普通“撤回关联”解除来源；真正撤销来源走 ETC/OA owner 的已有业务操作，页面说明操作含义，不能偷偷撤回后又自动重建。
8. OA 完成只更新状态，不换组。OA 撤销/删除或重提按真实 lifecycle identity 处理失效绑定和新身份；保留银行/发票事实及审计，不把失效来源强行保持为有效。没有新旧流程证明时不迁移到同额新 OA。
9. “同一批次只有一个有效 owner”不等于“一个关系只能包含一个批次”。扫描已有多 OA/多批次关系的 link 读写能力，保留合法成员和来源，不因本次补关联覆盖原 metadata。一笔银行候选同时涉及多个已有 case 时，不偷抢某个 case 或默认把几个 case 合并；只有既有正式合并合同能证明唯一结果时才复用，否则明确显示待人工合并，不新增通用自动跨 case 合并算法。

交付：源关系稳定，银行前后到达等价，撤回和删除不会造成孤儿成员、重复关系或“删后立即自动恢复”的循环。

### E. 修复分区并保护其他页面

1. 同时修改 `evaluate_bank_relation_completion` 与 direct page SQL 的 in-progress 阻断；保留未知/无效 OA 身份检查、材料要求、金额异常及既有人工审阅语义。
2. 删除只用于强制未配对的 SQL CTE/join 和前端分支；保留所有真实流程状态字段、标签和筛选。列表、分页计数、搜索、详情、异常入口必须同口径。
3. 本次审批与配对分离适用于普通及 ETC 合法 OA 关系，不做 ETC 专属“假 completed”例外。无银行的 OA＋发票继续同组待补全。
4. 不改成本审批准入：进行中 OA 仍不能提前确认为成本；已完成兄弟单元仍可独立处理。
5. OA 待付款及外部支付同步继续消费正式 active outflow，沿用现有已付/待付合同；不顺便重构部分付款状态机，不写 OA 审批结果。
6. 银行明细、待找发票、进项使用、税金、导入、批量账务继续由各自 query owner 解释关系。ETC 内部 47 张成员与统一发票池 canonical 数量是不同统计口径，不为了配对补造缺少的 canonical 发票。
7. 自动配对由 worker 完成，不以用户打开页面为条件；关联台下一次普通 GET 直接读取结果。已提交而匹配尚未落库时不能把提交成功显示为配对成功。保留当前页正常进入/重进/刷新机制，不新增隐藏页面全量刷新或持续轮询；端到端测试分别验证后台已经收敛和页面读取结果。

交付：样本三项同组且在已配对区域，OA 仍标记进行中；其他页面的业务资格与金额不被 paired 标签污染。

### F. 历史数据收敛、文档及发布验证

1. 对已提交但未关联的 ETC 批次做一次有界只读清单，区分身份缺失、状态限制、无初始 case、占用冲突；只让有来源证明的记录进入同一正常 matcher。
2. 本笔历史身份补齐通过已有 owner/service 与审计；必要时增加明确的一次性、精确对象修复入口，不能把历史修复变成常规隐藏 fallback。禁止直接 SQL 拼关系。
3. 上线前先在隔离 PostgreSQL 数据库完成真实事务、故障、并发和端到端验证；主库不生成测试 OA、不撤销真实付款来做测试。
4. 执行阶段使用项目既有 `./scripts/deploy-oa.sh` 发布，不添加新的发布审批体系。发布前后读取同一业务样本与性能数据，核对 matching worker、正式成员、审批标签、页面统计和下游语义。
5. 生产回读至少核对：唯一 active case、OA/银行各一、ETC summary 一、47 个真实 ETC 明细、1711.33 元真实金额、审批仍进行中、无重复 canonical 发票/关系；重放不新增写入。
6. 更新 ETC、OA integration、workbench-relations、reconciliation-workbench 的 boundary/state/tests 与对应产品口径。更新 affected runtime I/O 文档；没有职责变化的其他页面只补回归证明。
7. 本计划不要求全库备份。若历史修复确需恢复前像，只保存本次精确记录；验证成功后清理本次备份/恢复文件与临时测试数据库，保留审计。主数据库、主库文件和非本次创建的备份不进入清理集合。失败尚待恢复时先恢复或解决，再清理，不提前销毁恢复材料。
8. 回滚前检查上一 release 能否读取本次新增的关系事实；没有 schema 改动也不能假设完全可回退。使用既有发布恢复入口，必要时暂停受影响 matching worker，保留 durable 任务。数据恢复只针对本次确实改动且当前版本仍可证明未被后续业务修改的记录；通过 owner/正式关系命令修正，禁止整库覆盖、清空关系或删除任务来伪造恢复。后续真实写入已发生的对象采取向前修复，不能拿旧前像覆盖。恢复后验证其他页面和 worker，再清理本次恢复材料。

## 5. 必须删除的旧逻辑

| 删除/替换对象 | 范围与条件 |
| --- | --- |
| ETC completed-only 查询及锁定重验 | 迁到统一 completed/admitted 输入后同时删除两处旧限制 |
| 无已有 case 就丢弃 ETC 来源候选 | 由明确来源初始计划替换，不保留旧无 owner 分支作为第二路径 |
| 普通匹配完再单独补 ETC 成员的时序依赖 | 完整成员进入单轮正式计划；复用仍必要的校验/metadata helper |
| 已有关系 loader 缺 summary / 跨月成员的盲区 | 同一事实读取入口补齐，不用扩展失败后全库重试兜底 |
| Workbench `oa_in_progress` 强制未配对分支及专用 SQL join | 同时替换领域规则、查询和旧测试预期；成本模块同名审批规则不删 |
| ETC 提交后回调作为唯一匹配触发 | 以同事务 durable 标记替换，去掉重复 enqueue/多路 writer |
| 依赖“oaRowId 空即安全”的错误删除判定 | 使用同一已验证 identity/active binding 合同，防止新旧删除语义不一致 |

删除前对入口、调用方、API client、repository、worker、测试、文档做 whole-repo symbol/text scan；删除后重复扫描确认无活动调用。既有历史 migration、审计事实和仍有明确消费者的 public helper 不因名称旧而盲删。已退役 ETC 探测器、read model、页面 refresh worker 不恢复。

## 6. 性能目标与验证方法

- 页面继续 direct canonical GET，零 matching/enqueue/OA HTTP/OCR；查询次数不随 47 张成员逐票增长。
- 匹配按精确 scope、batch ID、typed member 和金额/收款证据索引缩小输入；不新增全库两两比较，不扩大任意组合搜索预算。
- 同批批次、OA、银行、summary 采用集合读取；一次 UoW 合并保存；无变化重放零业务写，自动保存不再次投递自己。
- 核心 GET 沿用项目目标：p95 ≤1000ms，p99 ≤2000ms。相同数据与筛选条件，发布前后使用至少 100 次有界请求，报告样本数、p50/p95/p99、错误率；采用串行或低并发，避免给生产施压。
- 当前规模下，事实已落入本地且没有积压时，匹配计算与持久化初始目标 p95 ≤2 秒；端到端另计等待 worker 和外部 OA 同步的时间，不能把外部尚未到达的数据承诺为瞬时关联。
- 本地用当前规模和扩大规模的脱敏 fixture 检查查询次数与增长趋势；生产检查实际计划/耗时。只有观察到具体慢 SQL 才补最小索引，不预建缓存。

这些是验收目标，不是本次已经取得的性能结果。性能不达标必须报告原因和实测值，不能用空结果或减少正确性检查换速度。

## 7. 测试与验收矩阵

七类中：1、2、4、5、6、7 适用；第 3 类覆盖本次既有 API 语义变化，无需新增 endpoint。第 4 类只测领域后台任务与 direct GET 一致性，read model/cache 专属状态不适用，因为运行时已退役。

| 类别 | 验证重点 | 现有入口 |
| --- | --- | --- |
| 1 业务单元 | 精确来源先建组；审批不阻断；个人收款角色；空值/冲突/同额歧义；真实差额；分笔边界 | `test_workbench_free_matching_engine.py`、`test_workbench_relation_grouping.py`、OA adapter tests |
| 2 服务与事务 | 成员/link/审计同事务；CAS、唯一 owner、失败回滚、撤回恢复、幂等 | `test_workbench_matching_orchestrator.py`、`test_workbench_formal_relation_repository.py`、ETC backend/删除 tests |
| 3 API 合同 | 既有字段/权限不变；列表与详情同组、统计一致；错误不伪成功；提交重复请求 | Workbench API、ETC API、page query tests |
| 4 后台与读取 | 事件顺序、提交后崩溃、处理中再变更、重复消费、跨月完整事实、GET 零写 | matching queue/worker tests、`test_workbench_query_postgres_integration.py` |
| 5 前端交互 | 提交后状态、同组/展开47张、审批标签、两区切换、搜索筛选分页、错误反馈、权限 | `EtcTicketManagementPage.test.tsx`、受影响 Workbench component tests |
| 6 端到端 | ETC提交→OA同步→两项关系→银行导入→同case三项；反向到达；撤回银行→保留两项 | ETC/银行导入/关联台/OA待付款 Playwright＋真实PG集成 |
| 7 回归 | 普通报销34元已修复链、银行/发票页、待付款、成本审批、税金、批量账务、导出、权限、原撤回保护 | 对应模块既有测试和定向跨页E2E |

必要场景：

- OA、批次、银行的不同到达顺序，均收敛到唯一关系。
- 进行中→完成保持 case；进行中和已完成 OA 混合组按相同配对规则处理。
- 身份缺失明确可解释；两个 OA 指向同批次、同额同名两个流水不被任意抢配。
- 银行姓名与 OA 申请人不同但与收款人一致；账号明确不一致时不自动加入。
- 跨7/8/9月、重复同步、重复提交、并发两个 worker、事务中途失败。
- OA/发票有差额和补充凭证，不伪造金额；删除补充凭证不拆来源关系。
- 银行撤回/删除、人工拒绝、批次删除/reset 与 OA 重提的当前 owner 一致。
- 本批47 ETC明细和既有canonical成员不重计、不补造；税率/金额/来源保持原事实。
- 银行候选歧义或搜索预算耗尽仍保存已证明的 OA＋ETC 来源组；数据库或审计失败不得伪装成这类业务歧义。
- 明确业务引用跨越姓名组合日期窗口仍走明确引用规则；旧快照不抹掉已提交身份；合法多批次关系不被单批次 metadata 覆盖。
- 发布恢复保留后续真实业务写入，任务不被丢弃；无法安全反向覆盖时明确向前修复。

实施后的验证命令（不是本次已执行结果）：

```bash
bash scripts/verify.sh lint
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_orchestrator tests.test_workbench_formal_relation_repository tests.test_workbench_relation_grouping tests.test_workbench_page_query_repository tests.test_etc_backend tests.test_mongo_oa_adapter -v
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
```

真实 PostgreSQL 集成测试使用项目现有测试 DSN 合同和显式 disposable 数据库；不能把数据库依赖跳过当成验证通过。先运行定向失败样本，修复后做相关集成，再在最终状态运行一次全套，不反复无差别全量测试。生产管理员 token 只经 `scripts/with-production-admin-token.sh` 加载。

## 8. 复审结果

| 用户要求 | 复审结论 |
| --- | --- |
| 模块化、清晰 I/O | 每项事实有唯一 owner，纯计算不做 I/O，正式写入复用 command/UoW |
| 简单且完整闭环 | 修复现有链路，无新平台层；覆盖身份、初始关系、补流水、状态、撤回、跨月、历史数据 |
| 高性能 | 有具体 GET/匹配目标、查询次数约束和生产测量；不承诺未测的毫秒级结果 |
| 移除旧链 | 有明确删除清单；区分 Workbench 旧阻断与成本合法审批规则 |
| 其他页面不出问题 | API shape 与事实口径保持；审批/支付/成本分离；以回归证明，不能保证绝对零bug |
| 指出不合理理念 | 不接受仅金额配对、全操作全库重算、审批中等于已审批、证据缺失也强行自动化 |
| 备份清理与主库保护 | 默认不全库备份；仅本次恢复材料/临时库在成功后清理；禁止主库删除 |
| 禁止兜底 | 无旧链降级、字符串猜归属、假状态或静默成功；明确错误与现有durable重试不属于兜底 |

第二轮复审通过。补齐了明确引用不受姓名搜索窗口限制、银行歧义不阻断来源落库、旧快照保护、多批次现有关系保留以及精确回滚，未增加模块、worker 或审批步骤。

实施就绪仍有一个明确技术事实要在任务 A 中查清：真实 OA 的稳定身份往返；已列为首项工作，不能跳过后声称修复完整。所有阶段以本笔生产事实回读和回归证据结束，不以“代码已写”代替业务闭环。

## 9. 实施与验证记录

已落地：正式 `field101` 附件路径往返、来源先建组、后到银行扩展、进行中配对分区、来源撤回保护、多批次 metadata/列表/详情、提交事实与 matching dirty 同事务、事实版本与批次快照并发校验。删除未注册 OA 表单扩展字段、completed-only ETC 候选、事后追加 summary、submitted 后重复回调，以及把主批次身份套到全部 summary 的读取逻辑。没有新增依赖、表、worker、read model、页面轮询或兜底。

生产只读核对：批次 `etc_business_batch_241146` 的 47 个正式发票号与 OA 文档 `6aa8ff4969252c470e7d59d5` 的全部附件名完全一致，正式 `processId` 对应计划中的 OA。历史补齐使用已有 `manual-oa-status` command，记录此核对依据，不向外部 OA 写假字段。

本地验证包括 389 项定向单元/服务/API 回归、67 项 direct-query pytest、8 项新增 PostgreSQL 来源事务/并发测试，以及既有 36 项 query PostgreSQL 集成。新增多批来源用例同时验证 compact/full detail；真实金额差额继续按原异常规则保留同组待处理，不能伪装成平衡。

前端 106 文件 / 1369 项 Vitest 及生产构建通过。浏览器定向 58 项中 57 项通过；成本抽屉 100 行折叠在固定 400ms 采样末帧未归零，隔离复测及修复前 `main` 的独立代码快照均复现。此代码未被本次修改，保留失败证据，不修改断言、不宣称浏览器全部通过。

生产发布前串行各 100 次 GET 基线：关联台 p50/p95/p99=704.522/865.567/959.080ms；批次详情=139.239/215.325/292.872ms；两者零错误。发布后使用相同探针复测，最终 release、业务同组与测量结果由本任务生产验证报告记录。

最终自审：模块边界保持，全部新关系通过同一正式 UoW，来源数据留在各 owner；有歧义不按金额抢配；进行中配对不改审批/成本资格；新旧链路不并行；GET 不写任务。无数据库备份需求，结束时仅删除本次自建隔离测试数据库与临时测试文件，不操作主数据库。

全量后端入口 `FIN_OPS_TEST_DATABASE_URL=<本次隔离库> bash scripts/verify.sh backend`：4302 项、0 失败，52 项因现金模块专用测试 DSN 未设置而跳过；随后把 `FIN_OPS_CASH_TEST_DATABASE_URL` 指向本次隔离库，现金核心、运行时及 HTTP 集成 59 项全部通过。新增匹配 PostgreSQL 测试单独真实执行。补充 canonical 银行账户 envelope 回归，防止公共解析函数展开后再次展开而丢失账户冲突证据。`verify.sh lint/docs` 与 `git diff --check` 通过。

生产首轮验证发现：进行中 OA 的跨月补查缺少常规读取中的工作流号、项目和日期/币种规则，导致相同 OA 在两个入口的事实不一致。已删除补查中的独立简化投影，改为同一 repository 内共享字段定义；新增真实 PostgreSQL 失败复现及修复回归。规则版本更新后，失败月份通过现有运维重试入口恢复，不删除失败记录或跳过事实冲突校验。
