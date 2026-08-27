# 销项发票收款情况 Spec-first E2E Spec

本文件定义 `/output-invoice-collections` 的真实浏览器业务验收合同。

## 模块目标

页面直接展示 canonical 销项发票、收款状态、收入流水和备注精确号码派生的红蓝票关系。页面是只读业务视图，不维护 OA、收据、提醒、手工收款状态或手工红蓝票关系。

## 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `OUT-COLL-E2E-001` | canonical baseline | P0 | 首屏只展示 `销项发票 / 收款状态 / 收入流水` 三组；筛选、排序、分页和 summary 来自 API。 |
| `OUT-COLL-E2E-002` | 精确备注红蓝票关系 | P0 | 红票备注中的 20 位目标号码唯一命中蓝票时，蓝票展示“已被红冲”、红票展示“已冲销蓝票”，两行关系详情互相引用且 mode 为 `output_invoice_reversal`。 |
| `OUT-COLL-E2E-003` | 未匹配红票 | P0 | 歧义或无匹配负票展示“红票待核对”，不得自动选择任一候选。 |
| `OUT-COLL-E2E-008` | canonical 一票一行 | P0 | 同一普通 relation 内的多张销项发票均各占一行；按购买方搜索返回全部 canonical 发票，红票和目标蓝票不得重复累计同一收入流水。 |
| `OUT-COLL-E2E-004` | direct-read error recovery | P0 | rows 暂时失败时显示 error、不伪装 empty、不自动 polling；用户刷新后恢复。 |
| `OUT-COLL-E2E-005` | 只读权限和旧入口删除 | P0 | view/export 用户可读可导出；页面没有状态/提醒、红蓝票手工操作、收据、OA 或 admin 设置入口，零 mutation 请求。 |
| `OUT-COLL-E2E-006` | 详情 | P1 | 发票、银行流水和 `kind=bank|invoice` 关系详情从 canonical GET 返回；404/失败可见。 |
| `OUT-COLL-E2E-007` | 导出 | P1 | download event 成功，字段和当前筛选一致，导出不包含 OA、收据或手工状态列。 |

## 不属于本地 deterministic E2E 的风险

- 生产历史数据中的目标号码缺失、重复和歧义分布。
- 真实 PostgreSQL 查询计划、锁等待和大文件导出耗时。
- Workbench 后台自动正式化及发布后 T+300 队列稳定性；由 release gate/生产 smoke 验证。页面直接 canonical 读取不依赖该任务完成才展示精确关系。
