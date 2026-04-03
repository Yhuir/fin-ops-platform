# 关联工作台 V2 数据契约

## 1. 工作台总响应

```json
{
  "month": "2026-03",
  "summary": {
    "oa_count": 286,
    "bank_count": 412,
    "invoice_count": 305,
    "paired_count": 198,
    "open_count": 127,
    "exception_count": 21
  },
  "paired": {
    "oa": [],
    "bank": [],
    "invoice": []
  },
  "open": {
    "oa": [],
    "bank": [],
    "invoice": []
  }
}
```

## 2. OA 行 DTO

```json
{
  "id": "oa-o-1",
  "type": "oa",
  "case_id": "MKT-001",
  "applicant": "刘晨",
  "project_name": "品牌广告投放",
  "apply_type": "市场费用",
  "amount": 6000,
  "counterparty_name": "杭州张三广告有限公司",
  "reason": "3月品牌投放尾款",
  "oa_bank_relation": {
    "code": "pending_match",
    "label": "待找流水与发票",
    "tone": "warn"
  },
  "available_actions": ["detail", "confirm_link", "mark_exception"]
}
```

## 3. 银行行 DTO

```json
{
  "id": "bk-o-1",
  "type": "bank",
  "case_id": "MKT-001",
  "trade_time": "2026-03-20 09:15",
  "debit_amount": 6000,
  "credit_amount": null,
  "counterparty_name": "杭州张三广告有限公司",
  "payment_account_label": "招行基本户 8821",
  "invoice_relation": {
    "code": "pending_invoice_match",
    "label": "待关联广告票",
    "tone": "warn"
  },
  "pay_receive_time": "2026-03-20 09:15",
  "remark": "应付6000，候选OA-051",
  "repayment_date": null,
  "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"]
}
```

## 4. 发票行 DTO

```json
{
  "id": "iv-o-1",
  "type": "invoice",
  "case_id": "MKT-001",
  "seller_tax_no": "91330102MA8T32A2X7",
  "seller_name": "杭州张三广告有限公司",
  "buyer_tax_no": "91330106589876543T",
  "buyer_name": "杭州溯源科技有限公司",
  "issue_date": "2026-03-20",
  "amount": 5660.38,
  "tax_rate": "6%",
  "tax_amount": 339.62,
  "total_with_tax": 6000,
  "invoice_type": "进项专票",
  "invoice_bank_relation": {
    "code": "pending_collection",
    "label": "待匹配付款",
    "tone": "warn"
  },
  "available_actions": ["detail", "confirm_link", "mark_exception"]
}
```

## 5. 详情响应 DTO

```json
{
  "id": "bk-o-1",
  "type": "bank",
  "case_id": "MKT-001",
  "summary_fields": {
    "交易时间": "2026-03-20 09:15",
    "借方发生额": "6000.00",
    "对方户名": "杭州张三广告有限公司"
  },
  "detail_fields": {
    "账号": "6214 8350 0000 8821",
    "账户名称": "杭州溯源科技有限公司",
    "余额": "451220.56",
    "币种": "CNY",
    "对方账号": "6222 9033 1200",
    "对方开户机构": "中国银行杭州分行",
    "记账日期": "2026-03-20",
    "摘要": "广告投放尾款",
    "备注": "候选 OA-202603-051",
    "账户明细编号-交易流水号": "B202603200019",
    "企业流水号": "ENT202603200051",
    "凭证种类": "转账支付",
    "凭证号": "VCH-95112"
  }
}
```

## 6. 税金抵扣响应 DTO

```json
{
  "month": "2026-03",
  "output_items": [
    {
      "id": "to-1",
      "buyer_name": "上海辰屹商贸有限公司",
      "issue_date": "2026-03-24",
      "invoice_no": "90342011",
      "tax_amount": 509.43,
      "total_with_tax": 9000,
      "invoice_type": "销项普票"
    }
  ],
  "input_items": [
    {
      "id": "ti-1",
      "seller_name": "杭州张三广告有限公司",
      "issue_date": "2026-03-20",
      "invoice_no": "11203490",
      "tax_amount": 339.62,
      "total_with_tax": 6000,
      "risk_level": "中"
    }
  ],
  "default_selected_output_ids": ["to-1"],
  "default_selected_input_ids": ["ti-1"],
  "summary": {
    "output_tax": "509.43",
    "input_tax": "339.62",
    "deductible_tax": "339.62",
    "result_label": "本月应纳税额",
    "result_amount": "169.81"
  }
}
```

## 7. 动作请求 DTO

### 7.1 确认关联

```json
{
  "month": "2026-03",
  "case_id": "MKT-001",
  "row_ids": ["oa-o-1", "bk-o-1", "iv-o-1"]
}
```

### 7.2 标记异常

```json
{
  "month": "2026-03",
  "row_id": "bk-o-2",
  "exception_code": "bank_fee",
  "comment": "系统自动识别为网银服务费"
}
```

### 7.3 税金抵扣计算

```json
{
  "month": "2026-03",
  "selected_output_ids": ["to-1", "to-2"],
  "selected_input_ids": ["ti-1", "ti-2"]
}
```

## 8. 动作响应 DTO

```json
{
  "success": true,
  "action": "confirm_link",
  "month": "2026-03",
  "affected_row_ids": ["oa-o-1", "bk-o-1", "iv-o-1"],
  "updated_rows": [
    {
      "id": "oa-o-1",
      "type": "oa"
    }
  ],
  "message": "已确认 3 条记录关联。"
}
```

## 9. 契约原则

- 字段名在接口层统一使用英文蛇形
- 状态显示文案由后端产出，前端只做渲染
- `case_id` 是前端做同组联动的唯一依据
- `available_actions` 决定每行显示哪些按钮
- 主表字段与详情字段必须分层返回，避免一个响应既大又难维护
- 所有 V2 动作统一返回 `success / action / month / affected_row_ids / updated_rows / message`
