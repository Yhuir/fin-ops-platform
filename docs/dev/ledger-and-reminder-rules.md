# 台账与提醒规则

## 范围

Prompt 05 把未闭环的核销事项转成可持续跟进的业务台账，并提供最小可运行的提醒调度骨架。

当前实现入口：

- 接口：`GET /ledgers`、`GET /ledgers/{ledger_id}`、`POST /ledgers/{ledger_id}/status`
- 接口：`GET /reminders`、`POST /reminders/run`
- UI：`GET /workbench/prototype` 中的 `台账提醒` 页面

## 台账生成来源

台账不支持孤立手工录入，只能由真实核销动作自动生成：

- `POST /workbench/actions/confirm`
- `POST /workbench/actions/exception`
- `POST /workbench/actions/offline`

上述动作完成后，服务会调用 `LedgerReminderService.sync_from_case(...)`，基于 `ReconciliationCase` 及异常编码生成或更新 `FollowUpLedger`。

## 台账类型映射

### 常规核销差额

- 应收场景：
  - 发票未完全收回：生成 `payment_collection` 催款台账
  - 银行收款大于票面未冲抵部分：生成 `advance_receipt` 预收台账
- 应付场景：
  - 发票已到但未付清：生成 `payment_reminder` 待付款提醒台账
  - 付款超出票面：
    - 已有关联发票：生成 `invoice_collection` 催票台账
    - 无关联发票：生成 `prepayment` 预付台账

### 异常编码

- `SO-A`：`payment_collection`
- `SO-B`：`output_invoice_issue`
- `SO-C`、`SO-D`：`advance_receipt`
- `SO-E`、`SO-F`、`SO-H`、`PI-E`、`PI-F`：`external_receivable_payable`
- `SO-G`：`non_tax_income`
- `PI-A`、`PI-B`、`PI-D`：`invoice_collection`
- `PI-C`：`refund`
- `PI-G`、`PI-H`：`payment_reminder`

## 预计处理日期规则

预计处理日期以核销单里的首个业务日期为基准：

- 优先取发票日期
- 否则取银行流水日期
- 再否则回落到核销单创建日期

偏移规则：

- `payment_collection`、`payment_reminder`、`external_receivable_payable`：`+7` 天
- `invoice_collection`、`advance_receipt`、`prepayment`：`+5` 天
- `refund`、`output_invoice_issue`：`+3` 天
- `non_tax_income`：`+2` 天

## 台账状态与审计

状态枚举：

- `open`
- `in_progress`
- `waiting_external_feedback`
- `resolved`
- `cancelled`

当前支持：

- 创建台账时自动写审计日志
- 台账金额或预计日期更新时写审计日志
- 通过 `POST /ledgers/{ledger_id}/status` 更新状态、备注、预计日期时写审计日志

## 提醒策略

提醒模型为 `Reminder`，当前提供最小调度骨架：

- `schedule_reminders(as_of, days_ahead=7)`：
  - 仅处理未解决、未取消台账
  - 仅处理预计日期在 `as_of + 7` 天内的台账
  - 默认渠道为 `in_app`
- `run_reminders(as_of)`：
  - 先补齐待发送提醒
  - 再把 `as_of` 当天及之前的 `pending` 提醒标记为 `sent`
  - 同时回填台账的 `last_reminded_at`

去重规则：

- 同一台账、同一渠道，只允许存在一条活跃提醒
- 已存在未取消提醒时，不重复创建
- 因此提醒任务可重复执行，但不会重复轰炸

## 页面交互口径

`台账提醒` 页当前支持：

- 按 `待处理 / 七日内到期 / 已逾期 / 全部` 视角切换
- 按状态筛选
- 行内查看台账详情
- 行内把台账标记为 `跟进中` 或 `已解决`
- 一键执行提醒任务
- 查看待发送与已发送提醒列表

## 验证方式

后端测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

前端原型脚本校验：

```bash
awk '/<script>/{flag=1;next}/<\\/script>/{flag=0}flag' web/prototypes/reconciliation-workbench-v2.html > /tmp/reconciliation_workbench_v2.js
node --check /tmp/reconciliation_workbench_v2.js
```
