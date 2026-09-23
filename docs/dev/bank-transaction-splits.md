# 流水拆分 I/O 与验证

业务事实见 [流水拆分](../product-specs/bank-transaction-splits.md)。本次不使用 GSD。

## API

- GET /api/bank-transactions/{parent-or-child-id}/splits：解析原流水，返回 transaction_id、canonical_transaction_id、amount、written_off_amount、direction、version、category_code、parts、tag_definitions、can_edit。
- PUT 同一路径：输入 version、parts[{id?,category_code,amount}]；金额为十进制字符串；空 parts 撤销时提供 category_code。actor 来自登录身份。成功返回持久化完整对象、changed、affected_months；旧版本 409、不合法合计/金额/标签 400、流水不存在 404、无认证 401、无页面授权 403。
- POST /api/bank-transactions/splits/query：输入 transaction_ids[]，输出 rows[] 与输入顺序一一对应。两个子项属于同一父项时仍按请求数返回，避免位置错绑。固定次数 SQL，无逐行 load。
- tag_definitions 是显示合同，含 code、label、path、primary_label、sub_label、status 与配置语义，不暴露自动分类规则全文。子项与配置分开持久化，标签更新不复制成银行原始事实。

## 模块与事务

route 仅 HTTP/session 映射；BankTransactionSplitService 校验金额及版本并编排一次事务；PostgresBankTransactionSplitRepository 只拥有银行拆分表与审计。BankTransactionSplitRelationService 调用关系、成本、批次与往来 owner 的事务端口，失败整体回滚；提交后只发布既有关系内存 delta。

锁先取关联成员有序 advisory locks，再锁银行父行并重读金额，防 split 与 relation 写互锁；版本 CAS 防覆盖。子项属于多个关系时撤销拆分需先撤回相关关系，不合并不同业务意图。历史记录保留原证据；恢复时只允许明确完整身份组投影到当前子项，禁止恢复已删除成员。

BankTransactionUnit 是服务层只读用途 DTO，继承银行字段用于现有行组装，但不送入导入写口。原始银行详情独立使用 parent_transaction，金额统计使用 unit.amount。标签由配置 role/code 决定；外部往来子项不增加发票实付款。

## 旧链路清理

- 用途 SQL 由 app.bank_transactions 切到 app.bank_transaction_units；银行余额、导入去重、主身份审计保留原表。
- 成本不再依靠外部往来本金填写“不计成本”来伪装用途；既有外部决策由迁移工具撤销。
- 父流水已拆分时旧整笔标签写口明确拒绝，不默默覆盖子项。
- 共享 TwoColumnTagPicker 替换成本专有重复选择器，各银行抽屉复用同一拆分组件。
- 往来旧内存分类中的固定类别列表/手工回退改用配置语义及 canonical query owner。

## 测试矩阵

| 类别 | 必须验证 |
|---|---|
| 核心单元 | 精确分币、无效/重复/外来身份、同标签多项、空项撤销、语义角色、无本金重复计费 |
| 服务/持久化 | 原事实不变、完整事务回滚、并发版本冲突、关系/成本/批次/往来审计、无重复副作用 |
| API | 单笔/批量形状、权限、会话actor、错误状态、版本冲突、完整回读 |
| 查询/缓存/后台 | canonical 列表与汇总一致、标签筛选、父行计数、关联事件、批量读取；无新增read-model/worker |
| 前端 | 双栏选择、加删改、合计、保存错误、关闭重开、多笔草稿保护、所有详情入口 |
| 端到端 | PostgreSQL保存→用途投影→往来/成本/待票，真实浏览器提交/回读，发布后生产回读 |
| 旧回归 | 未拆分、导入/撤回、余额、批次/撤回历史、OA/发票、权限、过滤分页与导出 |

## 发布与数据处理

先提交并推送 remote main，唯一发布入口 ./scripts/deploy-oa.sh。0178/0179 引入拆分存储/用途视图；发布后若已写拆分事实，旧代码不能解释用途，不允许回到旧读取链路。

撤销历史外部成本先运行 `python3 -m fin_ops_platform.tools.revoke_external_turnover_cost_allocations` 预览，再以 `--apply --operator <会话操作人>` 同一事务执行，随后再次预览应为零。生产通过 `sudo -n /usr/local/sbin/finops-deploy-control external-turnover-cost-revoke <release> [--apply --operator <actor>]` 加载既有运行环境；执行后使用既有 restart 命令清除进程中的关系快照。工具只撤销被识别的成本决策与其确认状态，不删除银行/OA/发票。审计保存撤销前数据用于明确恢复。

如发布产生临时数据库备份，验证成功后只移除本次 exact backup 文件；不得删除主数据库。测试仅使用名字明确标识 test 的隔离数据库，任务结束清理本次测试库。

性能目标沿用现有合同：读 p95≤1000ms、p99≤2000ms，写到可见 p99≤3000ms。记录样本数与环境；单次生产样本或 no-op 写不能证明完整写入 p99。完成证据在此文后续发布记录追加。

## 性能探针

`finops-deploy-control bank-transaction-split-smoke <release>` 在单个回滚事务内创建自有测试流水，按当前有效标签运行 100 次真实拆分校验、持久化、关系 owner、审计及用途投影读取，并确认父流水/审计均未残留。它不修改真实业务流水，测量不包含 HTTP、提交及已有关系场景，不能替代 HTTP 写到可见 SLO。HTTP 读取使用正式 release gate；隔离 PostgreSQL 的完整提交后回读另行记录。

## 本地验证记录（2026-09-24）

- 后端 pytest 全量收集 4,990 项，首轮 4,903 passed / 32 failed / 55 skipped。失败涵盖独立普通成本被本金专属 OA 干扰的实际回归及旧 SQL/启动/标签/发票来源测试合同；逐项修正后，全部失败所在的 9 个测试文件统一复验 284 passed。未跳过或放宽失败断言。旧发票来源期望按已有 2026-09-20 OA 来源优先合同更新，未改发票生产逻辑。
- 成本所有测试在真实 PostgreSQL 下 184 passed，含独立普通费用保留及共享 OA 不误删。
- 现金独立 PostgreSQL 补测 127 passed；全量默认未提供现金专用 DSN 的跳过由此补充覆盖。
- 前端 113 文件 / 1,509 测试通过，拆分浏览器流程 1 passed；生产构建、Ruff、docs、diff check 均通过。
- 本地完整事务提交并回读 100 次：p50 18.97 ms、p95 22.32 ms、p99 26.83 ms；批量读 100 次 p99 17.07 ms。该数据不含网络，也不代表已有复杂关联的生产 HTTP 写入分位数。
- 原银行表的余额、身份与金融金额不变，子项保存、并发冲突、失败回滚、往来/成本/待票/OA、批次及导入撤销均有针对性验证。生产发布记录由既有 release gate 持久化，发布后另跑统一抽屉、拆分读 API、金额错误拒绝与事务回滚性能探针。
