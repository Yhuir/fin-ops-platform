# 成本统计验收规格

## 核心合同

`/cost-statistics` 的 explorer、详情、导出预览和导出下载每次请求都从同一个 PostgreSQL
`REPEATABLE READ READ ONLY` snapshot 读取 canonical 银行流水、OA、active 正式关系、标签和设置。

页面不依赖其它页面 payload/read model，也不存在 Cost version、freshness、scope、queue、worker 或后台轮询。

## 验收场景

| ID | 场景 | 验收标准 |
| --- | --- | --- |
| `COST-E2E-001` | 五种视图 | time/project/bank/expense_type/bank_tag 均返回完整、正确数据 |
| `COST-E2E-002` | 关系确认与撤回 | 下一次 Cost 请求读取更新后的 active relation；写后无 Cost fan-out |
| `COST-E2E-003` | 下钻 | explorer 与 bank transaction/allocation detail 使用一致 snapshot 口径；点击行立即打开对应右侧抽屉，详情 loading/error 不污染页面状态 |
| `COST-E2E-004` | 导出 | preview/download 与当前视图、筛选和权限一致 |
| `COST-E2E-005` | 加载失败恢复 | 请求失败显示明确错误；页面刷新发起全新请求并可恢复 |
| `COST-E2E-006` | 隔离 | Cost 请求不读取或触发其它页面 read model，不影响其它页面 API |
| `COST-E2E-007` | 性能 | 候选发布记录各视图多次请求耗时；本任务不设 3 秒硬门槛 |
| `COST-E2E-008` | 日常报销明细 | 每个 `expense_item` 按自身当前金额和项目归集；支付申请按 OA 当前金额；三种 OA 视图、详情和导出不使用报销表头或流水金额 fallback |
| `COST-E2E-009` | N:M 付款关系 | 三 OA/两流水仍逐个按 OA 归集单元金额统计；不按比例/顺序猜测；多账户归入 `混合支付账户`，详情展示付款证据与金额差异 |
| `COST-E2E-010` | OA 完成态与期间 | project/bank/expense_type 按 OA 完成时间筛选并排除进行中/无完成时间 OA；纯银行 time/bank_tag 继续按流水时间和流水金额 |
| `COST-E2E-011` | 完整性 | 无效子付款项被可见质量统计排除；同一 OA/子付款项跨 active relation 重复时整次响应返回 409，不重复计成本 |

## 生产验证

- Audit 通过，关系成员不存在/形状异常必须阻断。
- Cost API 成功响应不含 `read_model_status`、`read_model_version` 或 refresh scope。
- `job.outbox_events`、`job.read_model_dirty_scopes` 和 worker registry 无当前 Cost 任务。
- 同批验证 Workbench、外部往来、银行明细等关键页面只读 API 不受影响。
