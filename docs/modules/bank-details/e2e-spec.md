# 银行明细 Spec-first E2E Spec

本文定义 `bank-details` 页面在真实浏览器中的业务验收合同。Playwright 测试必须按用户可见流程、跨页面事实源和导出文件结果来设计；代码实现只用于定位 route、selector 和 deterministic mock。

## 模块目标

银行明细页面展示银行流水、账户余额、自动/人工分类、自动匹配提示和已确认关系。Browser E2E 必须证明 direct canonical GET 的 loading/empty/error、写后重读、active relation 与导出筛选/权限合同；页面不得轮询或消费 read-model freshness。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `BANK-E2E-001` | 首屏列表和账户余额 | P0 | 页面加载后展示全部账户、账户余额、当前日期范围、流水表和 relation/category 字段；direct GET 空结果显示真实空态。 |
| `BANK-E2E-002` | Workbench linked relation tags | P0 | 未正式化自动匹配 decision 或历史 candidate 兼容值不得显示 `有oa` / `有发票`；关联台 confirm 后重新进入页面显示 `有oa` / `有发票`，且列表重新请求。 |
| `BANK-E2E-003` | 银行流水导入 -> 银行明细列表 | P0 | 银行导入 preview/confirm 后，进入银行明细能看到新流水、账户和原始字段。 |
| `BANK-E2E-004` | 真实浏览器导出下载 | P0 | 点击导出触发 browser download event；请求携带当前账户、日期、关键字和分类筛选；文件名和内容包含当前 relation/category 字段。 |
| `BANK-E2E-005` | 日期、账户、搜索、分类、分页筛选 | P1 | 切换筛选后只重新读取交易列表，不重复请求账户余额；导出沿用相同筛选。 |
| `BANK-E2E-006` | 自动标签规则保存/重应用 | P1 | drawer 保存或重应用成功后只重新 GET 当前 transactions；不请求 operation barrier、不等待 worker。 |
| `BANK-E2E-007` | 候选确认和人工补分类 | P1 | 只能确认当前候选，只能人工补分类 unmatched 行；保存后页面刷新并保留 category version contract。 |
| `BANK-E2E-008` | direct query loading/empty/error | P1 | direct GET 不自动轮询；空响应进入真实空态；网络失败显示错误并允许用户通过查询变化重试恢复。 |
| `BANK-E2E-009` | 权限矩阵 | P1 | `read_export_only` 可读和导出但不能写分类/规则；`full_access/admin` 才能执行 mutation；denied/expired 进入 session gate。 |
| `BANK-E2E-010` | 大表格滚动和视觉遮挡 | P2 | 长列表、宽列、分类浮层、导出菜单和表格滚动在桌面/窄屏不遮挡关键操作。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。
- 真实历史银行模板、大文件、生产脏数据和性能。
- 真实 XLSX 内容格式完全解析；本地 Browser smoke 只验证 download event、文件名和关键业务字段。
- 真实 staging/production 导出权限和代理层 headers。
