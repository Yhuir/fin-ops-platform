# Prompt 06 Advanced Exceptions Design

## Goal

在现有核销系统中补齐三类高阶异常能力：

- 差额核销
- 红字发票与反向流水核销
- 跨应收 / 应付的内部抵扣

要求不破坏 Prompt 01-05 已有的标准核销、台账与提醒流程。

## Scope

本次只覆盖以下业务对象与动作：

- 结构化差额原因：手续费、抹零、汇率差、税差、其他
- `ReconciliationCase` 中的差额核销记录
- `OffsetNote` 内部抵扣单
- 工作台右侧操作区新增 `差额核销` 与 `内部抵扣`

本次不做：

- 独立的高级异常页面
- 差额原因配置中心
- 内部抵扣审批流
- 取消核销 / 撤销内部抵扣

## Design

### 1. Difference Reconciliation

新增结构化差额原因枚举 `DifferenceReason`，并在核销单上同时保留：

- `difference_amount`
- `difference_reason`
- `difference_note`

差额核销动作只在已选发票和银行流水时开放。后端根据双方剩余金额自动计算差额，允许用户用结构化原因把尾差闭环，不再把尾差落为普通未闭环台账。

### 2. Negative Invoice And Reverse Transaction

红字发票不新增独立导入模型，继续沿用 `Invoice`：

- 允许负数金额导入
- 允许负数发票进入工作台未配对区
- 人工核销时按符号识别反向场景

规则：

- 正销项票 -> 收款流水
- 红字销项票 -> 退款流水
- 正进项票 -> 付款流水
- 红字进项票 -> 收款退款流水

实现上使用“剩余绝对金额做分配、按对象原始符号回写核销金额”的方式，避免负数发票在 `written_off_amount` 上被错误冲减。

### 3. Offset Note

新增 `OffsetNote` 作为独立业务对象：

- 不伪造银行流水
- 由同一客商的应收发票和应付发票生成
- 形成独立 `ReconciliationCase(case_type=offset)`

内部抵扣动作要求：

- 至少选中一张销项票和一张进项票
- 默认按双方未核销金额最小值抵扣
- 支持备注和原因
- `ReconciliationLine` 中增加 `offset_note` 行

### 4. API

新增工作台动作接口：

- `POST /workbench/actions/difference`
- `POST /workbench/actions/offset`

已有接口继续保留：

- `POST /workbench/actions/confirm`
- `POST /workbench/actions/exception`
- `POST /workbench/actions/offline`

## Impact

### Backend

- `domain/enums.py`：增加 `DifferenceReason`
- `domain/models.py`：增加 `difference_note` 与 `OffsetNote`
- `services/reconciliation.py`：
  - 支持红字发票与反向流水
  - 增加差额核销
  - 增加内部抵扣
- `app/server.py`：新增两个工作台动作路由

### Frontend Prototype

继续沿用现有工作台：

- 右侧操作区增加 `差额核销`
- 右侧操作区增加 `内部抵扣`
- 详情抽屉支持查看 `OffsetNote`

## Testing

至少覆盖：

- 差额核销生成结构化差额原因
- 红字销项票 + 退款流水闭环
- 内部抵扣生成 `OffsetNote + ReconciliationCase`
- 新接口 HTTP round-trip
- 不破坏现有标准核销和台账提醒测试
