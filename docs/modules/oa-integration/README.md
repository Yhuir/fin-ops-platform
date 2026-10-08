# OA 集成

入口：`外部系统适配边界`。

提供身份、Mongo 来源同步、支付状态及角色适配、附件识别和申请人凭据能力。

## 边界与 I/O

输入：受信 token、Settings ACL/预填、同步 scope、精确 OA IDs 和来源附件。输出：身份、PostgreSQL OA/准入/附件事实、支付状态同步结果、非敏感申请人及窄项目目录。

## 当前业务约定

- 页面及配对的历史身份读取只使用当前 OA ID、已声明别名和 indexed active alias，不从附件/子项字段反向推测身份或重复扫描附件。
- 同一份源文档的 App OA 身份不随 `processId`、`flowRequestId` 或审批状态变化。已入库 OA 保留当前 canonical ID；新 OA 使用表单类型与 Mongo `_id` 建立身份，流程编号仅登记为可查找别名。来源别名与 OA/准入事实在同一事务提交，冲突明确失败。
- 附件缓存、报销子项和来源证据在确定 canonical OA 身份后生成；完成审批只迁移 pending/completed 归属，不撤销配对，也不重建附件身份。投影写入不按 ID 后缀猜测或直接改写其他模块的关系。
- OA Mongo 财务源只读；worker 一次读取范围内来源，输出 completed 与 admission 视图。任何必需来源读取失败不提交部分权威集合。
- 设置中的手动 OA 全量搜索独立读取源库，不受自动同步起始日期限制；只读分页发现尚未入库的单据，不触发同步或附件解析。普通业务页面继续读取 PostgreSQL，正式导入仍由现有 import worker 提交。
- 仅完整 all 权威快照能证明源消失；清理 active 成员与本地快照后，通过精确事件复核并删除对应外部支付状态，month/retention 不证明源删除。
- 付款状态复核先将历史事件中的 active 来源别名解析为当前 OA 并去重，未知身份仍明确失败；不按旧 ID 重复写回同一流程。
- 支付状态由当前 active outflow 收敛；MySQL 写回由专用 adapter 执行，不向 Mongo 写业务。
- 附件解析统一调用现行 `parse_file_result`；失效缓存由 worker 重新读取原件，不升级旧识别结果或回退旧解析接口。搜索只读批量缓存，后台预览只产生识别结果，正式导入通过事务建立 OA 与发票事实；API 不运行全量同步/OCR。
- 日常报销附件保持原子项来源；支付申请附件使用整单 `source_oa_id`，不伪造报销子项。两者的反向入池均要求正式 OA 和精确附件登记；预览缓存自身不能成为正式来源。整单统计对发票身份去重，单文件多票与多文件同票独立计数。
- 原件修复同时读取已完成 OA 的附件登记和当前在途准入付款项的 `attachment_artifacts`。在途登记必须与同一付款项的 `attachment_files` 精确匹配文件名、路径与唯一 owner；重复或冲突拒绝，不以识别缓存替代登记。
- 发票财务字段只读取原件标签、版式表格或真实明细行；PDF/OFD 文字层优先，图片经现有 OCR 按坐标还原行。税率不读取手机电量、备注中的首个百分比，不用金额比例补算或调换金额/税额。
- `source_line_items` 逐条保存真实明细及各条税率、金额、税额；折扣/红字保留负号，未打印的逐行价税合计保持空。无明细来源不生成整票汇总明细。`*`、免税、不征税保持来源文字，非数字税额用 `tax_amount_text`，数值 `tax_amount` 为空。
- Mongo 附件适配、识别缓存与正式发票写入保留明细对象数组和空值，不把结构化证据转换为字符串；缓存 schema 隔离旧字符串明细，失效后由 worker 按原件重新解析。
- 已有正式发票的 OA 附件关联只更新来源关联、标签及 OA 关系，不补填或覆盖原始财务字段与明细。新发票创建时整组采用原件数据；同一张票再次同步保持原件追溯信息与真实空值。
- 铁路客票、机打通行费票和非税缴款书只提供票价/缴款额时，只记来源总额；不生成未税金额、税额零或推算税率。解析器版本变更隔离旧附件识别缓存。OFD 与 DOCX 共用受限 ZIP 验证，按声明页及模板读取文字。
- OA 角色同步只消费当前 page ACL：有页面的普通用户对应 finops_app_user，固定管理员对应 finops_admin；菜单不是权限事实源。
- ETC/反提外部创建使用冻结配置、持久请求身份与显式未知结果恢复；凭据只经 owner 使用，不返回密码。
- 现金项目与成本项目目录通过各自窄只读端口，不能把外部元数据通道扩张为页面财务源。

## 依赖方向

[设置](../settings/README.md)、[权限与审计](../permissions-and-audit/README.md)、[后台任务](../runtime-workers/README.md)、[进项发票使用](../input-invoice-usage/README.md)、[ETC 票据](../etc-tickets/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/app/auth.py](../../../backend/src/fin_ops_platform/app/auth.py)
- [backend/src/fin_ops_platform/services/oa_identity_service.py](../../../backend/src/fin_ops_platform/services/oa_identity_service.py)
- [web/src/features/session/api.ts](../../../web/src/features/session/api.ts)
- [backend/src/fin_ops_platform/services/oa_role_sync_service.py](../../../backend/src/fin_ops_platform/services/oa_role_sync_service.py)
- [backend/src/fin_ops_platform/tools/settings_access_control_preflight.py](../../../backend/src/fin_ops_platform/tools/settings_access_control_preflight.py)
- [backend/src/fin_ops_platform/services/mongo_oa_adapter.py](../../../backend/src/fin_ops_platform/services/mongo_oa_adapter.py)
- [backend/src/fin_ops_platform/services/cash_oa_projects.py](../../../backend/src/fin_ops_platform/services/cash_oa_projects.py)
- [backend/src/fin_ops_platform/services/oa_projection_sync.py](../../../backend/src/fin_ops_platform/services/oa_projection_sync.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py)
- [backend/src/fin_ops_platform/app/worker.py](../../../backend/src/fin_ops_platform/app/worker.py)
- [tests/test_mongo_oa_adapter.py](../../../tests/test_mongo_oa_adapter.py)
- [tests/test_session_api.py](../../../tests/test_session_api.py)
- [tests/test_oa_projection_sync_service.py](../../../tests/test_oa_projection_sync_service.py)
- [tests/test_oa_attachment_invoice_service.py](../../../tests/test_oa_attachment_invoice_service.py)
- [tests/test_oa_attachment_invoice_promotion_service.py](../../../tests/test_oa_attachment_invoice_promotion_service.py)
- [tests/test_oa_attachment_invoice_promotion_tool.py](../../../tests/test_oa_attachment_invoice_promotion_tool.py)
- [tests/test_original_invoice_attachment_sources.py](../../../tests/test_original_invoice_attachment_sources.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
