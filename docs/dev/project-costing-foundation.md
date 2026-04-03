# 项目成本测算底座说明

本文档对应 Prompt 08，说明当前项目维度底座的边界、项目归属优先级、查询口径，以及后续演进到正式成本测算模块的扩展路径。

## 1. 当前实现范围

当前已经落地：

- 独立 `ProjectCostingService`
- 项目归属记录 `ProjectAssignmentRecord`
- 项目汇总读模型 `ProjectSummary`
- 项目接口：
  - `GET /projects`
  - `GET /projects/{project_id}`
  - `POST /projects`
  - `POST /projects/assign`
- 原型页最小 `项目归集` 视图

当前不做：

- 成本分摊算法
- 毛利与利润口径
- 多项目拆分归属
- 独立 BI 看板

## 2. 项目归属优先级

项目归属优先级固定为：

1. `手动指定`
2. `OA 单据带出的项目`
3. `对象已有 project_id`
4. `无归属`

这样做的目的有两个：

- 保留人工纠偏能力，避免 OA 或导入历史字段锁死后续归属
- 让“原始归属”和“人工覆盖”可追溯，不把两者混成一个字段

因此，系统新增了独立 `ProjectAssignmentRecord`，专门记录人工指定动作及审计信息。

## 3. 当前支持的归属对象

项目归属已经贯通到以下对象：

- `Invoice`
- `BankTransaction`
- `ReconciliationCase`
- `FollowUpLedger`

解析逻辑：

- `Invoice`
  - 手动指定
  - `oa_form_id` 对应 OA 单据项目
  - `invoice.project_id`
- `BankTransaction`
  - 手动指定
  - `transaction.project_id`
- `ReconciliationCase`
  - 手动指定
  - `approval_form_id / related_oa_ids` 对应 OA 单据项目
  - `case.project_id`
  - 若关联对象只归属于唯一项目，则回落到该项目
- `FollowUpLedger`
  - 手动指定
  - `ledger.project_id`
  - 来源核销单项目
  - 来源发票项目

当人工把核销单归属到项目时，系统也会同步把同源台账补上项目，避免后续项目视角下出现孤儿台账。

## 4. 项目汇总指标

`GET /projects` 当前返回最小可用项目汇总，不抢占主核销链路，只提供后续成本测算需要的底座口径。

当前汇总字段：

- `income_amount`
- `expense_amount`
- `reconciled_amount`
- `open_ledger_amount`
- `invoice_count`
- `transaction_count`
- `case_count`
- `ledger_count`

当前计算口径：

- 销项票计入 `income_amount`
- 进项票计入 `expense_amount`
- 已核销金额基于核销单汇总
- 未闭环金额基于未解决台账汇总

这套口径不是正式成本口径，只是项目归集底座。

## 5. 接口说明

### `GET /projects`

返回：

- 项目汇总列表
- 全局汇总卡片数据
- 可归属对象列表

可归属对象当前来自：

- 发票
- 银行流水
- 核销单
- 台账

### `GET /projects/{project_id}`

返回单项目详情：

- 项目主数据
- 该项目汇总指标
- 已归属对象清单

### `POST /projects`

用于手工创建项目主数据，适合：

- OA 还没同步到该项目
- 需要先做试运行或手工归集

### `POST /projects/assign`

用于人工把对象归属到项目。动作会：

- 写入 `ProjectAssignmentRecord`
- 更新目标对象的 `project_id`
- 写审计日志

## 6. 原型页口径

`/workbench/prototype` 已新增 `项目归集` 入口。

当前页面支持：

- 查看项目数量、收入、支出、未闭环金额汇总卡片
- 查看项目汇总表
- 查看单项目详情
- 手工创建项目
- 对发票、流水、核销单、台账执行项目归属

它的定位是“项目维度底座验证页”，不是正式项目经营看板。

## 7. 后续扩展路径

从当前底座往正式项目成本测算继续演进，推荐顺序是：

1. 先把更多业务对象稳定挂到项目
2. 再补成本分摊和多项目拆分
3. 再补项目毛利、回款率、税负等经营指标
4. 最后再做独立项目经营看板

这样可以避免在底座还不稳时，过早把分摊算法和 BI 口径写死。

## 8. 验证方式

后端测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

前端原型脚本校验：

```bash
awk '/<script>/{flag=1;next}/<\\/script>/{flag=0}flag' web/prototypes/reconciliation-workbench-v2.html > /tmp/reconciliation_workbench_v2.js
node --check /tmp/reconciliation_workbench_v2.js
```

## 9. 与成本统计页面的关系

Prompt 08 的定位仍然是**项目归属底座**，不是正式成本统计页。

两者关系如下：

- Prompt 08 解决：
  - 项目主数据
  - 项目归属优先级
  - 项目汇总底座
  - 手动归属与审计
- 成本统计页面解决：
  - 基于已确认 OA 字段的支出流水统计
  - 按月份、按项目查看成本
  - 层层下钻到具体流水
  - 导出当前统计视图

因此，成本统计应视为 Prompt 08 之后的新一层页面能力，而不是把 Prompt 08 的“项目归集页”直接改名。
