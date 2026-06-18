# 银行明细 Spec-first E2E Spec

本文定义 `bank-details` 页面在真实浏览器中的业务验收合同。Playwright 测试必须按用户可见流程、跨页面事实源和导出文件结果来设计；代码实现只用于定位 route、selector 和 deterministic mock。

## 模块目标

银行明细页面展示银行流水、账户余额、自动/人工分类、候选关系和已确认关系，并向导出、往来款、免 OA、待找发票、成本和税金等链路提供上游事实。Browser E2E 必须证明页面不会把 stale/候选/本地事件误当成最终事实，也必须证明导出文件与当前页面筛选和权限一致。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `BANK-E2E-001` | 首屏列表和账户余额 | P0 | 页面加载后展示全部账户、账户余额、当前日期范围、流水表和 relation/category 字段；fresh 空结果才可显示空态。 |
| `BANK-E2E-002` | Workbench candidate/linked relation tags | P0 | 候选阶段只显示 `候选oa` / `候选发票`；关联台 confirm 后重新进入页面显示 `有oa` / `有发票`，且列表重新请求。 |
| `BANK-E2E-003` | 银行流水导入 -> 银行明细列表 | P0 | 银行导入 preview/confirm 后，进入银行明细能看到新流水、账户和原始字段。 |
| `BANK-E2E-004` | 真实浏览器导出下载 | P0 | 点击导出触发 browser download event；请求携带当前账户、日期、关键字和分类筛选；文件名和内容包含当前 relation/category 字段。 |
| `BANK-E2E-005` | 日期、账户、搜索、分类、分页筛选 | P1 | 切换筛选后只刷新交易列表，不用 stale 账户余额覆盖 fresh 余额；导出沿用相同筛选。 |
| `BANK-E2E-006` | 自动标签规则保存/重应用 | P1 | drawer 保存或重应用后等待当前可见月份 fresh，展示成功或后台同步 warning；不能把后置同步 blocked 报成保存失败。 |
| `BANK-E2E-007` | 候选确认和人工补分类 | P1 | 只能确认当前候选，只能人工补分类 unmatched 行；保存后页面刷新并保留 category version contract。 |
| `BANK-E2E-008` | stale/refreshing/error 状态 | P1 | read model 非 fresh 时显示诊断并保留可用旧 rows；不能把 stale 空 rows 当真实空；导出/写入口按状态禁用或报业务错误。 |
| `BANK-E2E-009` | 权限矩阵 | P1 | `read_export_only` 可读和导出但不能写分类/规则；`full_access/admin` 才能执行 mutation；denied/expired 进入 session gate。 |
| `BANK-E2E-010` | 大表格滚动和视觉遮挡 | P2 | 长列表、宽列、分类浮层、导出菜单和表格滚动在桌面/窄屏不遮挡关键操作。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 真实历史银行模板、大文件、生产脏数据和性能。
- 真实 XLSX 内容格式完全解析；本地 Browser smoke 只验证 download event、文件名和关键业务字段。
- 真实 staging/production 导出权限和代理层 headers。

