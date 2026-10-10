# 专票认证情况

入口：`/tax-offset`，页面权限标识仍为 `tax-offset`。

查询发票池中未删除的进项专票，导入认证证据，查看认证状态、筛选汇总并导出专票清单。

## 边界与 I/O

- 查询输入：认证状态、开票期间、勾选期间、搜索、排序和分页。输出：rows、total、summary、inventory_statistics 和导出字段目录。待核对数量由导入抽屉的管理查询提供。
- 两个期间独立支持全部、年、年月。`issue_year` / `issue_month` 及 `selection_year` / `selection_month` 在同一维度互斥，冲突返回 400；年使用四位数字字符串。全部不发送该维度参数，年度条件按当年首日至次年首日的左闭右开范围查询。
- 发票池拥有发票身份、购销双方及原始金额、税额；认证模块拥有来源批次、所属期、勾选时间、有效抵扣税额和认证版本。认证导入不能新建发票或改写发票原始事实。
- `GET /api/tax-offset` 在 PostgreSQL 只读快照中查询跨月进项专票，数据库分页和汇总；筛选条件共同生效，汇总覆盖全部匹配结果。
- `inventory_statistics` 在同一快照中独立聚合全部未删除进项发票，不随认证状态、搜索、期间、排序或分页变化。必填非负整数为 `input_invoice_count`、`special_invoice_count`、`general_invoice_count`、`toll_invoice_count`、`other_invoice_count`、`unclassified_invoice_count`；总数等于后五项之和。每张 canonical 发票计一次，红字单独计数，来源、明细和关联不重复计数。票种沿用 canonical code，其他仅含已识别的其余票种，缺失或未知 code 单列未识别，ETC 导入渠道不代替票种。导出不读取标题统计。
- `POST /api/tax-offset/export` 接收 filters 和 fields，沿用列表筛选与排序导出全部匹配记录。默认八列，其余字段可选；最多 20000 张。号码和税号作为文本写入，缺失字段不补算。

## 当前业务约定

- 专票按 canonical `invoice_kind_code=vat_special` 明确识别；列表、汇总、导出、认证匹配与审计使用同一字段，不按税率、金额或是否已导入认证反推票种。
- 开票日期、勾选时间、税款所属期分别保存；默认跨所有月份。未认证且筛选某个勾选年或月时返回空集，不忽略条件。
- 默认开票日期倒序，日期排序追加稳定 ID，空勾选日期排最后。金额使用原始精确值，零与缺失分开；汇总包含缺失计数。
- 认证 XLSX 最多读取 20000 条业务记录，读取时限制行列规模；非专票计为忽略，不计为错误。认证 Excel 读取“发票”工作表及来源元数据，保留十九列来源证据。来源状态与票种决定可处理范围，不能以有效抵扣税额大于零替代认证判断。
- 发票关联只使用数电票号或发票代码与号码，并核对购买方身份。未匹配和歧义记录单独显示，不按姓名、日期或金额猜测。来源与已匹配发票的金额、税额或身份存在冲突时阻止确认，不能借更正操作覆盖发票事实。
- 预览保存独立 session；确认沿用共享 import worker。任务归属、当前权限及记录版本在提交时重新验证，认证变更、批次、审计和任务成功状态同事务提交。
- 重复导入不累计；冲突须明确提交对应 unique_key 与 expected_version。批次撤销只恢复自己的有效贡献；撤销更正批次会恢复前一记录及批次归属并递增版本，不能删除重复引用的原认证或覆盖后续更正。
- 待核对记录与批次历史独立分页，默认每页 20 条、最多 100 条；历史列表不返回撤销所用内部恢复内容。失败任务重新识别文件后生成新 session，再次提交。
- 历史无法准确关联的证据保留并报告待核对数量，审计不把它们当作已匹配。发票正常删除后保留认证证据，列表排除该发票。发票晚于认证文件入库时，重新导入认证文件触发补关联，并保留原批次归属。
- 页面只读 canonical facts，不依赖抵扣计划、试算缓存或页面刷新任务。写入成功重新查询列表与汇总，请求乱序不覆盖当前筛选。

## 界面

标题右侧展示全部进项发票及专票、普票、通行费、其他的轻量数量统计；有未识别票种时通过公共统计展开明细显示。搜索位于统计右侧，导出和导入位于标题行右端。下一行依次为状态切换、已认证／未认证汇总、两个紧凑公共年月选择器；窄屏换行。统计以静态状态 chip 配合张数、右对齐金额，两个组始终展示当前筛选结果；切换条件加载时不显示上一条件的数字。金额按千分位、两位小数显示，来源精度及导出不变；原票税额与有效抵扣税额分别显示，缺失值不补算。

表格占用剩余高度并在内部滚动，表头固定、分页常驻。导入、导出分别使用 HeroUI 右侧抽屉；导出只选择字段。界面保留必要错误和结果反馈，不放解释段落。

## 依赖方向

[发票导入](../imports-invoices/README.md)、[后台任务](../runtime-workers/README.md)、[权限与审计](../permissions-and-audit/README.md)。认证模块不写 OA、付款关系或发票用途，不读取其他页面 payload 作为事实。

## 代码与验证入口

- [TaxOffsetPage](../../../web/src/pages/TaxOffsetPage.tsx)
- [HTTP 路由](../../../backend/src/fin_ops_platform/app/routes_tax.py)
- [查询合同](../../../backend/src/fin_ops_platform/services/tax_offset_query_service.py)
- [查询仓库](../../../backend/src/fin_ops_platform/services/postgres_repositories/tax_offset.py)
- [导出](../../../backend/src/fin_ops_platform/services/tax_offset_export_service.py)
- [认证解析](../../../backend/src/fin_ops_platform/services/tax_certified_import_service.py)
- [认证持久化](../../../backend/src/fin_ops_platform/services/postgres_repositories/tax_certified_imports.py)
- [页面审计](../../../backend/src/fin_ops_platform/services/postgres_repositories/tax_offset_page_audit.py)
- [API 测试](../../../tests/test_tax_offset_api.py)
- [查询与导出测试](../../../tests/test_tax_offset_query_service.py)
- [解析测试](../../../tests/test_tax_certified_import_service.py)
- [页面测试](../../../web/src/test/TaxOffsetPage.test.tsx)
- [浏览器链路](../../../web/e2e/tax-offset-flow.spec.ts)

通用事务、错误和性能约定见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。
