# 关联台异常 icon 恢复记录

日期：2026-09-23。状态：实施完成，发布验证中。不使用 GSD。

## 范围与完成条件

恢复主表及异常抽屉的原圆形 icon，不独立占行。金额 Popover 只显示两方/三方权威金额，不显示解释、分类、差额、项目及人员描述。资料异常保持原状态及处理动作；审阅记录移到已有异常抽屉并保持只读可见。

直接模块为 reconciliation-workbench；输入为既有 anomaly DTO，输出为 UI 与原操作回调，无 HTTP/API/数据库/worker 变更。删除提示条、wrapper、描述索引及无用样式，保留 Escape 焦点修复。边界见[模块合同](../modules/reconciliation-workbench/boundary-io.md)。

## 验证

- `npx vitest run src/test/WorkbenchAnomalyIndicator.test.tsx src/test/WorkbenchExceptionDrawer.test.tsx src/test/RelationGroupGrid.test.tsx src/test/WorkbenchSupportingDocumentFiles.test.tsx`：89 项通过。首次从仓库根目录启动导致一套既有相对路径读文件失败，改从 web 目录执行即通过，未修改断言规避。
- `bash scripts/verify.sh frontend`：110 个文件、1485 项测试全部通过；生产构建通过。保留既有大 chunk 提示，无新增依赖。
- 6 个浏览器 spec 共29个不同场景通过（初跑28通过，新增长组用例修正打开动作后所在spec的3项复跑通过）。覆盖异常接受/撤回、凭证保存/删除、只读权限、长表滚动及申请人布局；悬停打开后首次点击关闭属于原有交互，不修改组件来迎合错误测试。
- 文档检查及 diff whitespace 检查通过。
- 适用测试类别：5 前端交互、6 流程集成、7 回归；1–4 未新增，原因是业务规则、服务、API、read model/cache/worker 均未改变。

## 生产取样

发布前，同一关联组 GET 7 次耗时 979–1084ms，中位数 1030ms（客户端 HTTPS 全耗时，含网络）。OA/银行1273.06，正式发票1139.63，补充凭证140.00，综合1279.63，仍由 anomaly_review_required 阻塞。部署后比较同一组 canonical 内容与 UI，不接受真实异常来制造成功结果。发布前 Popover 7 次打开耗时46–65ms，中位数54ms；旧文字入口330×34px，交互新增工作台请求0，浏览器错误0，写请求0。

## 发布与清理

使用标准 scripts/deploy-oa.sh，经 token wrapper 加载凭据；无需数据库迁移或备份，禁止删除主库。生产核验完成后清理此次私有临时快照、脚本和测试日志。
