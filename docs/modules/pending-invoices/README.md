# 流水待找发票

入口：`/pending-invoices`。

按银行收支用途核对发票取得状态，提供候选选择、已有发票关联、收入状态维护和规则设置。

## 边界与 I/O

输入：direction/filter/date/keyword/field filters/sort/page/include_statistics；写操作输入精确流水/发票集合、版本与受信 actor。输出：rows、summary、statistics、acquisition_summary、候选、详情和导出。

## 当前业务约定

- 流水身份栏在标签下显示交易时间 chip；拆分用途沿用原流水时间，多笔原始流水展示完整成员的最早至最晚时间。缺失成员时间时明确显示不完整，不使用 OA、发票或入账日期补齐。日期时间沿用上海时区显示，窄列自然换行。

- 头部搜索位于统计右侧，年月按流水交易日期过滤，使用包含首末日的 `date_from/date_to`；默认全部，选择月份清除交易日期列筛选，应用交易日期列筛选清除月份。导出继承关键词、日期与当前分类。规则入口在窄头部收进“更多”，读取失败可重试。

- 流水、发票、OA 数量入口分别在当前原表格展开成员，数量包含原始成员，仅追加 N−1 行；成员复用相同九列渲染。详情 icon 只读取对应原始单据；其它来源仅按正式关系提供上下文，不按数组位置配对。公共来源详情保留同票全部商品行、全部 OA 费用行，拆分流水归并原始父交易。原始行和展开行复用[公共分组提示](../../ui.md#oa流水与发票来源详情)，使用同一淡蓝灰背景与左侧边线；每个列表仅一个活动父行，列表替换后清理展开状态，不新增请求。

- 银行分类复用银行 owner；关系读取 active typed members，跨月关系不按当前月份截断，排除 turnover_manual_closure。
- OA completed/in-progress 与 ETC 正式发票成员都来自 PostgreSQL 当前事实；银行用途与父流水金额区分，原始流水计数按父身份去重。
- 分类切换采用连续三层区域：全部流水 → 支出/收入 → 各自发票状态，无外框和嵌套卡片。`acquisition_summary.scope_status_counts` 排除方向与状态自身条件，保留其他筛选，供两个方向同时展示；原 `status_counts` 保留当前方向口径。统计按原始流水身份去重，包含真实零值，不从当前页推导。
- 分类点击与列多选使用同一查询状态；只有方向和状态与单一分类精确对应时打勾，组合条件由列多选菜单表达，不同时点亮多个子分类。导出继承方向、状态、已生效搜索、列条件、日期与排序，覆盖全部命中结果，不受分页影响。抽屉只显示按原始流水身份去重的笔数和一个导出操作，不提供二次筛选或明细预览；数量与文件使用同一查询。
- 分组标题按流水、发票获取状态、发票、OA 的完整列宽居中；发票金额列只显示金额并居中，不附已付或待付行，支付计算、状态分类和详情不变。
- 发票价税合计只读取原字段。关联发票缺少价税合计时，整组发票金额显示缺失，支付计算保留缺失语义；状态为“已开票·金额缺失”，归入“金额待核对”。候选票仍显示，但不能执行依赖价税合计的关联确认。有价税合计而缺不含税金额的票不受此限制。
- 首屏不聚合高基数候选，filter-options 后续有界读取，每字段最多 50 项；发票候选使用服务端过滤排序分页。
- 关联命令由正式关系 owner 提交；失败保留用户选择，成功才回读。合法空集、加载和错误分开显示。
- 详情只返回公开来源字段；导出复用业务查询，最大 20,000 行，超限明确报错。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[发票导入](../imports-invoices/README.md)、[OA 待付款核对](../oa-pending-payments/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/PendingInvoicesPage.tsx](../../../web/src/pages/PendingInvoicesPage.tsx)
- [web/src/features/pendingInvoices/api.ts](../../../web/src/features/pendingInvoices/api.ts)
- [backend/src/fin_ops_platform/app/routes_pending_invoices.py](../../../backend/src/fin_ops_platform/app/routes_pending_invoices.py)
- [backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py](../../../backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py)
- [backend/src/fin_ops_platform/services/pending_invoice_service.py](../../../backend/src/fin_ops_platform/services/pending_invoice_service.py)
- [backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py](../../../backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [tests/test_pending_invoice_canonical_query.py](../../../tests/test_pending_invoice_canonical_query.py)
- [tests/test_pending_invoice_api.py](../../../tests/test_pending_invoice_api.py)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_consumers_postgres.py](../../../tests/test_bank_split_consumers_postgres.py)
- [tests/test_pending_invoice_service.py](../../../tests/test_pending_invoice_service.py)
- [tests/test_pending_invoice_relation_identity.py](../../../tests/test_pending_invoice_relation_identity.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
