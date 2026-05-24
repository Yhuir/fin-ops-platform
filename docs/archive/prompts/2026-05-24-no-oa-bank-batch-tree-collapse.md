# /goal 免 OA 流水批量处理三栏树状页与关联台折叠收口

/goal 按 A+ 方案生产级收口免 OA 流水批量处理：页面改为左分类、中批次、右流水三栏树状结构；批次按分类、月份、银行名称和账号后四位分组；批次卡片仅展示时间、银行+后四位、流水条数、分类和“提交批次/撤回批次”操作；流水明细把收支改成金额前 tag，并在金额下方显示银行+后四位 tag；关联台复用现有 `collapsed_summary` 代码，修复已提交免 OA 批次在 SQL read model 路径没有按 `row_count >= 2` 折叠的 bug；单条不折叠但必须保留免 OA tag、批次元数据和撤回批次动作；禁止重复写折叠逻辑。

## 串行主线

1. 先补文档和测试，锁定口径：
   - 单边免 OA 批次按 `batch_type + scope_month + account_key`，其中 `account_key = 银行名称 + 账号后四位`。
   - 内部往来款继续走现有跨账户配对逻辑。
   - 已提交免 OA 批次 `row_count >= 2` 才在关联台折叠；`row_count = 1` 保持普通银行流水行，但保留免 OA tag 和撤回动作。
2. 后端补齐明细 DTO：
   - `/api/no-oa-bank-batches/{batch_id}` 的流水行输出 `bank_name`、`account_last4`、`account_key`。
   - 继续保留 `expected_version`、审计、pair relation、read model 失效。
3. 修复关联台折叠 bug：
   - 在 SQL projection 应用 `no_oa_bank_batch` relation 时，把 relation `special_metadata`、`display_tags` 带入银行行。
   - 不新增折叠实现，只让现有 `WorkbenchCandidateGroupingService` 的 `collapsed_summary` 条件生效。
4. 前端改三栏：
   - 左栏保持现状。
   - 中栏宽度与左栏一致，只显示批次节点最小信息。
   - 右栏显示流水表，移除“收/支”列，金额前显示收支 tag，金额下方显示银行+后四位 tag。
5. 跑后端、前端和构建验证；如本地后端不可用，明确说明浏览器端到端限制。

## 可并行任务

- 后端任务：`NoOaBankBatchService` 测试、API 明细字段、SQL projection relation metadata、关联台折叠测试。
- 前端任务：`NoOaBankBatchPage` 三栏 UI、no-OA API/type 映射、页面测试。
- 文档任务：产品规格、开发契约和本 prompt/plan 对齐。

## 验收

- 同月同分类不同银行后四位生成不同批次。
- 中栏不会显示冗余说明文字，按钮文案为“提交批次”。
- 右栏金额列同时显示收/支 tag、金额、银行+后四位 tag。
- SQL read model 路径下已提交免 OA 批次 2 条及以上折叠为摘要行，原始流水保留在 `collapsed_rows.bank`。
- 单条免 OA 批次不折叠。
- 不复制或旁路现有折叠代码。
