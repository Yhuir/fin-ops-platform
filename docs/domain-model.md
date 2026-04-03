# 领域模型与状态设计

## 1. 核心设计原则

- 以“核销事件”而不是“导入记录”作为业务闭环中心
- 发票、流水、内部抵扣单、线下支付记录都视为可参与核销的业务对象
- 所有对象都要保留 `原始金额`、`已核销金额`、`未核销金额`
- 所有人工动作都要落审计日志
- 未来接入 OA 和项目成本测算时，只扩展关联关系，不推翻核心核销模型

## 2. 核心实体

## 2.1 Counterparty（客商）

字段建议：

- `id`
- `name`
- `normalized_name`
- `counterparty_type`：客户 / 供应商 / 两者兼有
- `tax_no`
- `oa_external_id`

说明：

- 是匹配规则和台账追踪的中心主数据
- 后续 OA 集成时需要能建立映射关系

## 2.2 Invoice（发票）

字段建议：

- `id`
- `invoice_type`：销项 / 进项
- `invoice_no`
- `invoice_code`
- `source_unique_key`
- `data_fingerprint`
- `counterparty_id`
- `invoice_date`
- `amount`
- `signed_amount`
- `currency`
- `project_id`
- `source_batch_id`
- `status`
- `written_off_amount`
- `outstanding_amount`
- `invoice_status_from_source`

说明：

- `signed_amount` 要支持负数，兼容红字发票
- `status` 不应只分已核销/未核销，至少要支持部分核销、待补录、待抵扣等状态
- `source_unique_key` 是导入幂等的第一优先键
- `data_fingerprint` 用于兜底防重或人工排查

## 2.3 BankTransaction（银行流水）

字段建议：

- `id`
- `account_no`
- `txn_date`
- `txn_direction`：收款 / 付款
- `bank_serial_no`
- `counterparty_name_raw`
- `counterparty_id`
- `amount`
- `signed_amount`
- `source_unique_key`
- `data_fingerprint`
- `summary`
- `source_batch_id`
- `status`
- `written_off_amount`
- `outstanding_amount`

说明：

- 溢收、预收、预付、退款等都依赖流水剩余金额继续流转
- 不应在第一次核销后直接“消失”
- `bank_serial_no` 存在时应优先作为流水唯一业务主键
- `data_fingerprint` 用于缺失官方流水号时的兜底防重

## 2.4 ReconciliationCase（核销单）

字段建议：

- `id`
- `case_type`：自动核销 / 人工核销 / 差额核销 / 内部抵扣 / 线下补录
- `biz_side`：应收 / 应付 / 跨板块
- `status`
- `counterparty_id`
- `total_amount`
- `difference_amount`
- `difference_reason`
- `exception_code`
- `resolution_type`
- `created_by`
- `approved_by`
- `created_at`

说明：

- 核销单是审计和追溯的核心对象
- 每次核销动作都应形成独立核销单
- 当不是直接核销，而是进入结构化异常处理时，也应保留 `exception_code`

## 2.5 ReconciliationLine（核销明细）

字段建议：

- `id`
- `reconciliation_case_id`
- `object_type`：invoice / bank_txn / offline_record / offset_note
- `object_id`
- `applied_amount`
- `side_role`：debit / credit / note

说明：

- 负责表达一对一、多对一、一对多等复杂映射
- 未来可扩展到 OA 单据或项目分摊记录

## 2.5.1 ExceptionHandlingRecord（异常处理记录）

字段建议：

- `id`
- `reconciliation_case_id`
- `biz_side`：销项应收 / 进项应付
- `exception_code`
- `exception_title`
- `source_invoice_ids`
- `source_bank_txn_ids`
- `resolution_action`：人工关联 / 生成台账 / 生成往来登记 / 标记待开票 / 标记待付款 / 标记非税收入
- `follow_up_ledger_type`
- `note`
- `created_by`
- `created_at`

说明：

- 用于把“异常处理”从自由备注提升为结构化业务对象
- UI 上的异常处理面板，最终应落到这个模型或等价模型

## 2.6 FollowUpLedger（后续台账）

字段建议：

- `id`
- `ledger_type`：催款 / 催票 / 退款 / 预收 / 预付 / 待开销项票 / 待付款 / 外部往来 / 非税收入
- `source_object_type`
- `source_object_id`
- `counterparty_id`
- `project_id`
- `open_amount`
- `expected_date`
- `owner_id`
- `status`
- `latest_note`

说明：

- 所有“没真正闭环”的业务都应转成台账，不靠备注埋掉

## 2.7 Reminder（提醒）

字段建议：

- `id`
- `ledger_id`
- `remind_at`
- `channel`
- `status`
- `sent_result`

## 2.8 ImportedBatch（导入批次）

字段建议：

- `id`
- `batch_type`：销项 / 进项 / 流水
- `source_name`
- `imported_by`
- `imported_at`
- `row_count`
- `success_count`
- `error_count`
- `duplicate_count`
- `suspected_duplicate_count`
- `updated_count`
- `status`

说明：

- ImportedBatch 不只记录批次摘要，还应支持关联逐行解析结果

## 2.8.1 ImportedBatchRowResult（导入行结果）

字段建议：

- `id`
- `batch_id`
- `row_no`
- `source_record_type`
- `source_unique_key`
- `data_fingerprint`
- `decision`：新增 / 更新 / 重复跳过 / 疑似重复 / 异常
- `decision_reason`
- `linked_object_type`
- `linked_object_id`
- `raw_payload`

说明：

- 用于支撑导入预览、确认执行和错误追溯
- 是导入中心 UI 的核心数据来源

## 2.9 OfflineSettlementRecord（线下核销补录）

字段建议：

- `id`
- `counterparty_id`
- `amount`
- `payment_method`
- `note`
- `evidence_url`
- `created_by`

说明：

- 用于覆盖现金支付、个人垫付等不在公账流水中的补充事实

## 2.10 OffsetNote（内部抵扣单）

字段建议：

- `id`
- `counterparty_id`
- `receivable_amount`
- `payable_amount`
- `offset_amount`
- `reason`
- `created_by`

说明：

- 用于跨应收/应付板块的内部平账

## 2.11 Project（项目，未来预留）

字段建议：

- `id`
- `project_code`
- `project_name`
- `project_status`
- `oa_project_id`
- `department_id`

说明：

- 当前阶段可先作为可选关联字段存在
- 后续进入项目成本测算时成为聚合主线

## 3. 关键状态

## 3.1 发票状态建议

- `pending`：待核销
- `partially_reconciled`：部分核销
- `reconciled`：已核销
- `pending_offline_confirmation`：待补录线下核销
- `pending_offset`：待内部抵扣
- `pending_invoice_issue`：待开票
- `pending_invoice_receive`：待补票

## 3.2 流水状态建议

- `pending`
- `partially_reconciled`
- `reconciled`
- `classified_as_prepayment`
- `classified_as_advance_receipt`
- `pending_refund`
- `pending_counterparty_confirmation`

## 3.3 台账状态建议

- `open`
- `in_progress`
- `waiting_external_feedback`
- `resolved`
- `cancelled`

## 3.4 异常处理编码建议

### 销项应收

- `SO-A`：多票对应一个收入
- `SO-B`：待收款
- `SO-C`：退款提醒
- `SO-D`：一票对应多个收入
- `SO-E`：待开销项票
- `SO-F`：外部往来-借入
- `SO-G`：外部往来-还款
- `SO-H`：非税收入

### 进项应付

- `PI-A`：多张进项票合并付款
- `PI-B`：追票
- `PI-C`：无票追票
- `PI-D`：外部往来-借给别人
- `PI-E`：外部往来-归还借入
- `PI-F`：待付款
- `PI-G`：部分现金支付
- `PI-H`：多张支付合并

## 4. 核心规则映射

## 4.0 导入幂等与防重规则

- 发票优先使用 `source_unique_key`
- 银行流水优先使用 `bank_serial_no` 或等价官方交易号
- 缺失官方唯一号时使用 `data_fingerprint` 兜底
- 命中完全重复数据时，默认 `重复跳过`
- 命中同主键但状态或关键字段变化时，允许 `状态更新`
- 命中指纹但无法确定是否真重复时，标记为 `疑似重复待人工确认`

## 4.1 销项逻辑

- 发票金额 = 收款金额：生成已核销核销单
- 发票金额 > 收款金额：发票进入部分核销，并创建催款台账
- 收款金额 > 发票金额：核销已匹配部分，剩余流水进入预收/往来待确认
- 无票收款：直接把流水转为预收、押金或其他待处理事项

## 4.2 进项逻辑

- 发票金额 = 付款金额：已核销
- 付款金额 > 发票金额：剩余付款进入缺票台账
- 发票金额 > 付款金额：允许通过线下补录或组合支付完成平账

## 4.3 高阶异常

- 差额核销：生成带 `difference_reason` 的核销单
- 红字发票：允许负数金额参与核销
- 内部抵扣：通过 `OffsetNote + ReconciliationCase` 建立跨板块平账

## 4.4 结构化异常与后续动作映射

- `SO-B` 应生成 `催款台账`
- `SO-C` 应生成 `退款台账`
- `SO-E` 应生成 `待开销项票台账`
- `SO-F` 应生成 `外部往来` 负债登记
- `SO-G` 应关联历史借出记录进行冲抵
- `SO-H` 应进入 `非税收入` 登记
- `PI-B` / `PI-C` 应生成 `催票台账`
- `PI-D` 应生成 `外部往来` 应收登记
- `PI-E` 应关联历史借入记录进行还款
- `PI-F` 应生成 `待付款提醒台账`
- `PI-G` 应生成 `线下支付补录`

## 5. 对未来 OA 与项目成本测算的预留

- 所有核心对象都建议预留 `project_id`
- 所有外部主数据都建议预留 `external_id`
- 所有核销动作都建议能挂到 `approval_form_id`
- 台账对象后续要能区分 “项目内异常” 和 “纯财务异常”
