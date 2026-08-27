# 销项发票收款情况模块维护入口

- Module key：`output-invoice-collections`
- Route：`/output-invoice-collections`
- Page key：`output-invoice-collections`
- 当前架构：canonical PostgreSQL API 直读、只读页面

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/modules/output-invoice-collections/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 代码入口

- `web/src/pages/OutputInvoiceCollectionsPage.tsx`
- `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`
- `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx`
- `web/src/features/outputInvoiceCollections/api.ts`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_reversal.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py`
- `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py`

## 当前事实边界

- 浏览器只调用 `/api/output-invoice-collections/*` 的七个 GET API；页面没有收款状态、提醒、收据编号、正式收据或手工红蓝票写入口。
- rows、summary、statistics、facets、筛选、排序、分页、详情和导出直接读取 PostgreSQL canonical facts，不读取页面 read model，也不访问 OA、MongoDB、MySQL 或对象存储。
- 收款流水归属只来自 `app.workbench_pair_relations status='active'`；红蓝票指向关系只来源于红票原始备注中的精确号码合同。
- 每个 canonical 销项发票 ID 固定输出一条表格行。普通 Workbench relation、红蓝票关系和相同金额均不得把多张发票折叠成一条净额行。
- 收款状态只由发票正负、有效红蓝票关系和已关联收入流水计算，不接受页面手工覆盖。
- 红字发票原始备注中精确标记的被冲红蓝字发票号同时驱动第四列、详情、搜索、导出和红蓝票状态。页面不使用金额、税额、购销方或日期猜测冲红对象。
- 页面只展示三组：`销项发票`、`收款状态`、`收入流水`。OA 和收据不属于本页 DTO。
- 页面请求失败时结构化报错，不回退旧 projection；前端只维护 loading、empty、error 和用户主动刷新状态。
- 页面使用共享紧凑时间范围选择器，搜索与范围控件互不重叠；HeroUI 分页位于同一有界 `FinanceTable` footer，不保留表格外的旧分页外壳。

## 红蓝票确定性规则

只有同时满足以下条件时才建立确定性红蓝票指向：

1. 当前发票价税合计为负。
2. 原始备注精确包含 `被红冲蓝字数电发票号码：<20 位数字>`，且只能提取出一个目标号码。
3. canonical 发票池中该号码恰好命中一张价税合计为正的销项发票。

页面直接按上述证据派生 `invoiceRelations` 和红蓝票状态；不要求另建一条可能与现有 OA/流水 relation 冲突的 active owner。Workbench 自动匹配复用同一精确号码 key；缺备注、目标不存在或目标不唯一时保持 `unmatched_red`，不执行金额兜底。

## 权限与审计

- 页面读取、详情和导出沿用现有 view/export 权限。
- 本模块没有页面写权限或 admin-only 设置入口。
- route 只做 session、权限、参数和 HTTP 映射；service 不读取 header/cookie，repository 不做权限判断。
- 自动红蓝票关系沿用 Workbench 正式关系的审计、幂等和撤回边界，不建立第二套关系表。

## 旧链路删除合同

以下运行时代码不得恢复：

- output collection lifecycle/status/reminder service 和 repository。
- 正式收据 preview/create/void/reissue/history/settings。
- 手工红蓝票确认/撤销 drawer 和 API。
- 页面 OA/收据列、状态/提醒按钮及对应 DTO。
- output collection 页面 read model、worker、freshness/polling/fallback。

历史 migration/表可以作为回滚证据保留，但不得有运行时 reader、writer、route 或页面入口。

## 本目录文件

- `boundary-io.md`：当前输入、输出、文件和依赖边界。
- `tests.md`：七类测试适用性、命令和剩余风险。
- `state-machine.md`：六个只读收款/红蓝票状态。
- `e2e-spec.md`、`e2e-coverage.md`：浏览器业务合同与覆盖。
- `implementation-notes.md`：历史记录；历史 read-model/lifecycle 描述不覆盖本 README。
