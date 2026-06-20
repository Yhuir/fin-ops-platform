# 免OA流水批量处理 Spec-first E2E Spec

本文件定义 `/no-oa-bank-batches` 页面在真实浏览器中的业务验收合同。测试必须保护免 OA 标签准入、批次提交、freshness barrier、撤回、历史只读、权限门禁和下游 read model fan-out，而不是保护当前组件实现细节。

## 模块目标

免 OA 流水批量处理负责把没有 OA 单据但仍需闭环的银行流水提交成 no-OA 批次，并通过统一 Workbench relation command 形成 `relation_mode=no_oa_bank_batch` 的事实。页面只能消费后端 no-OA read model 和 operation barrier，不能用本地状态伪造已提交、已撤回或下游成本 fresh。

## 用户角色

- `admin`：可读取和执行写操作，并可进入管理员设置/运维入口。
- `full_access`：可读取、保存标签准入、提交和撤回 no-OA 批次。
- `read_export_only`：可读取批次和标签范围，但不能提交、撤回、勾选批量写操作或保存标签准入。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `NO-OA-E2E-001` | 页面 ready、fresh list 和 bucket summary | P0 | 进入 `/no-oa-bank-batches` 后页面显示免 OA 标题、未提交/已提交/历史 bucket、分类 summary 和银行流水表；首屏请求必须有界，不把 missing/stale read model 伪装成最终空结果。 |
| `NO-OA-E2E-002` | 标签准入保存 freshness closure | P0 | 用户在标签管理中修改 selected tag codes 后，页面必须 `PUT /api/no-oa-bank-batches/tag-selection`，带 `expected_version` 和 `selected_tag_codes`，等待 `no_oa_bank_batch:all` operation barrier fresh，再重读列表并显示成功反馈。 |
| `NO-OA-E2E-003` | selected-row submit freshness closure | P0 | 用户选择同账户、同月份、同分类的未提交流水后提交；请求体只包含当前选择的 `transaction_ids`，成功后等待 no-OA barrier fresh，再显示已提交结果，不允许重复提交或半写。 |
| `NO-OA-E2E-004` | 成本统计 downstream fan-out | P0 | no-OA 提交后进入成本统计，成本统计必须通过自己的 fresh read model 展示免 OA 成本项目、费用类型、金额和银行流水证据。 |
| `NO-OA-E2E-005` | withdraw 和 history 只读 | P0 | 已提交 bucket 可撤回；撤回 dialog 必须要求原因并提交 `expected_version`；撤回成功后历史 bucket 展示已撤回批次，且不再显示提交/撤回写入口。 |
| `NO-OA-E2E-006` | 权限 gate | P0 | `read_export_only` 用户可查看 no-OA 页面和标签范围，但不能看到/触发提交、撤回或保存标签准入；权限矩阵不得产生 durable mutation API。 |
| `NO-OA-E2E-007` | internal transfer / Workbench relation boundary | P0 | 关联台确认 internal transfer 必须收敛到 no-OA submitted batch 和 `relation_mode=no_oa_bank_batch`；no-OA 页面和 Workbench 不能为同一 row set 生成两条 active relation；混合 internal transfer 必须拒绝。 |
| `NO-OA-E2E-008` | read model stale/missing/refreshing | P0 | no-OA list/detail 在 SQL read model missing/stale/source mismatch 时只 enqueue refresh，不同步 rebuild；页面保留可用 rows 或展示刷新语义，不把旧空结果当真实 fresh。 |
| `NO-OA-E2E-009` | 大数据、长列表和分页稳定性 | P1 | 首屏分页使用 `page=1&page_size=200`，切换页码、月份或 bucket 时清理选择/详情缓存；真实大月份和长标签树不应遮挡或卡死。 |
| `NO-OA-E2E-010` | 真实基础设施 worker drain | P1 | no-OA submit/withdraw/tag selection 后，真实 PostgreSQL/RabbitMQ/Redis/systemd no-oa-bank-batch、workbench relation、search 和 cost worker 最终 drain 到 fresh；该项必须在 staging/runtime smoke 验证。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放。
- 真实 RabbitMQ/Redis/systemd no-oa-bank-batch worker drain、worker 重启和网络抖动恢复。
- 真实大月份、长标签树、长银行流水列表的浏览器滚动、视觉遮挡和交互延迟。
- 真实 search 外层 UI 和生产级 App Status/worker 指标。
