# 成本统计模块

## 当前产品模型

成本统计有两个业务分组。

`项目成本`保留三个视图：

- `按项目`：项目 → 费用类型 → 成本明细。
- `按费用类型`：费用类型 → 成本明细。
- `按银行账户`：银行账户 → 项目 → 成本明细。

三个视图消费同一个成本事件集合，期间、搜索和合计口径一致，只改变分组维度。`按银行账户`不是银行流水浏览器。

`银行流水`包含两个视图：

- `按标签`：主标签 → 子标签 → 银行流水明细。
- `按时间`：当前范围 → 银行流水明细。

两个视图消费同一个 canonical 银行流水集合，支出、收入和净支出分别统计；`净支出=支出-收入`。页面只展示支出与收入，净支出保留在 API、导出和校验合同中。银行明细仍负责账户余额、账户维度筛选和流水维护；成本统计不恢复与其重复的原始`按银行`视图。

银行账户归属规则保持确定性：

- 有 OA 的成本关系只查看关系内支出流水；恰好一个非空账户时归入该账户。
- 没有账户或存在多个不同支出账户时归入`银行账户未确定`。
- 退款账户不参与账户归属。
- 无 OA 成本行使用该笔支出流水自己的银行账户。

页面与导出接受 `time|bank_tag|project|expense_type|bank_account`。旧 `bank` view 与旧“按标签/按时间标签规则”仍不存在。

五个视图的页头统一只展示银行流水、支出流水和收入流水。左中栏使用 HeroUI `ListBox`：名称完整换行，金额使用 HeroUI“支/收”短 Chip，不显示展开按钮、百分比、归集数或净额；项目只显示费用类型数，费用类型只显示明细数或项目数，银行账户只显示项目数。

## 读取与写入边界

成本统计是 canonical direct-read 页面，不是 read model 消费者。每个 explorer、详情、预览或导出请求：

1. 在 PostgreSQL `REPEATABLE READ READ ONLY` 事务中读取本次范围所需事实；
2. 项目成本 view 由 repository 批量读取银行流水、OA、active relation、人工分配和无 OA 设置；流水 view 只读取范围内银行流水与批量有效标签投影；
3. `CostStatisticsPolicy` 分别生成唯一成本事件集合或真实银行流水集合并完成聚合；
4. query service 负责视图筛选、稳定 cursor 分页和 API DTO；
5. route 只处理 HTTP、权限和错误映射。

普通读取不使用 Cost queue、worker、Redis、dirty scope 或旧投影。复杂关系人工分配与无 OA 虚拟项目仍是当前成本人口的正式输入；保存成功后当前页面重新读取 canonical facts。

## 成本口径

- active 关系只要有 OA 未完成，整组不进入成本人口，也不能落入无 OA 项目。
- 全部 OA 完成后，关系净支出 `N = 支出合计 - 明确“付错退款”`。
- OA 合计 `O = N` 时按 canonical OA 单元金额自动形成成本；`O != N` 时进入人工分配。
- 人工分配必须满足 `C + X = N`，其中 `C` 为逐 OA 单元成本，`X` 为明确填写的不计入成本金额。
- `N = 0` 不形成成本；`N < 0` 明确失败。禁止比例猜测、默认项目、旧值回退或资金来源级伪分配。
- 无 active OA 关系的支出只有命中用户配置的无 OA 虚拟项目标签时才进入成本人口，费用类型固定为“无 OA 分类”。

## 性能合同

- 每次请求一个数据库快照；集合式批量读取，不做逐行或逐关系 I/O。
- 三个项目成本视图复用同一成本构建链；`按银行账户`只增加线性账户归属与分组，不读取银行明细 read model。
- 两个流水视图复用同一批量银行读取与标签投影，在 OA/关系/人工分配查询前返回；不逐行分类。
- 项目成本 Explorer 与导出不加载展示无关的标签投影；退款识别和无 OA 项目规则只读取明确需要的标签事实。
- 搜索先过滤当前视图事实，再计算汇总、分面和分页。
- 右栏固定每页 20 条，显式上一页/下一页；滚动不触发请求。
- 导出受 `COST_STATISTICS_EXPORT_ROW_LIMIT` 保护。
- 性能以本地/生产多次测量的 p50、p95、max 为证据；没有数据支持时不增加缓存、索引、worker 或新表。

## 入口

- 页面：`/fin-ops/cost-statistics`
- Explorer：`GET /api/cost-statistics/explorer`
- 导出：`GET /api/cost-statistics/export-preview`、`GET /api/cost-statistics/export`
- 详情：`GET /api/cost-statistics/bank-transactions/{id}`、`GET /api/cost-statistics/allocations/{id}`
- 无 OA 规则：`GET|PUT /api/cost-statistics/no-oa-rules`
- 人工分配：`GET /api/cost-statistics/manual-allocations`、`PUT /api/cost-statistics/manual-allocations/{case_id}`

## 维护文档

- [边界与 I/O](boundary-io.md)
- [状态机](state-machine.md)
- [测试矩阵](tests.md)
- [验收规格](e2e-spec.md)
- [实施决策](implementation-notes.md)
