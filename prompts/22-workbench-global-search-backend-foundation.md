# Prompt 22: 关联台强搜索后端底座

## 目标

为关联台强搜索建立统一后端底座，支持跨 `OA / 银行流水 / 发票` 的分组检索，并返回可直接用于前端跳转定位的结果模型。

## 你要做的事

- 新增统一搜索服务，建议命名为 `SearchService`
- 新增 `GET /api/search`
- 支持以下查询参数：
  - `q`
  - `scope=all|oa|bank|invoice`
  - `month=YYYY-MM|all`
  - `project_name`
  - `status`
  - `limit`
- 搜索结果按 `OA / 银行流水 / 发票` 三组返回
- 每条结果返回：
  - `row_id`
  - `record_type`
  - `month`
  - `zone_hint`
  - `matched_field`
  - `title`
  - `primary_meta`
  - `secondary_meta`
  - `status_label`
  - `jump_target`
- 为服务层和 API 层补测试

## 约束

- 第一版不要引入 Elasticsearch
- 不要做拼音搜索
- 不要做搜索历史
- 不要做导入记录搜索
- 要复用现有 OA Mongo 读取路径和 app Mongo 明细数据
- 结果需要支持前端直接跳回关联台，不让前端自己猜逻辑

## 推荐匹配能力

- 项目名称
- 申请人
- 公司名 / 对方户名
- 发票号 / 数电发票号
- 流水号 / 核心流水号
- 金额
- 银行卡后四位
- 费用类型
- 费用内容
- 状态

## 验收标准

- `GET /api/search` 可用
- 可以按关键词搜索 OA / 银行流水 / 发票
- 可以按月份 / 项目 / 状态筛选
- 返回结果按三组分类
- 每条结果都带 `zone_hint` 和 `jump_target`
- 后端测试通过

## 可直接使用的 Prompt

```md
请为当前系统实现“关联台强搜索”的后端底座。

背景：
- 关联台需要一个强搜索能力
- 搜索不是简单筛当前表格，而是要跨 OA / 银行流水 / 发票 统一检索
- 结果会按 OA / 流水 / 发票 分组展示
- 前端点击“跳转至”后要能直接回到关联台并定位记录

实现要求：

1. 新增统一搜索服务，建议命名为 `SearchService`
2. 新增 `GET /api/search`
3. 支持参数：
   - `q`
   - `scope=all|oa|bank|invoice`
   - `month=YYYY-MM|all`
   - `project_name`
   - `status`
   - `limit`
4. 结果必须按三组返回：
   - `oa_results`
   - `bank_results`
   - `invoice_results`
5. 每条结果至少包含：
   - `row_id`
   - `record_type`
   - `month`
   - `zone_hint`
   - `matched_field`
   - `title`
   - `primary_meta`
   - `secondary_meta`
   - `status_label`
   - `jump_target`
6. 复用现有 OA Mongo 读取路径和 app Mongo 明细集合
7. 补服务测试和 API 测试

注意：
- 第一版不要引入全文搜索引擎。
- 不要做拼音搜索和搜索历史。
- 不要做导入记录搜索。
```

