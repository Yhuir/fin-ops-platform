# 关联台异常 icon 恢复记录

日期：2026-09-23。状态：已部署，生产功能、性能复测及页面只读巡检完成。不使用 GSD。

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

## 发布后验证（2026-09-23 14:41–14:45 CST）

- 代码提交 `c7533f790d00f342d4700d19ca491326ce26e501` 已推送 remote main；生产 release `main-c7533f79-20260923143952`，frontend profile 的 pre/t0 均 PASS，无回滚；本 profile 不执行 T30，不宣称运行过。
- active release、公开 index/assets、发布目录内容、admin session、health ready 及四个 worker exact-set 校验通过。证据目录：`/opt/fin-ops/runtime-smoke/release-gates/main-c7533f79-20260923143952/`。
- 发布前后同一真实关联组完整 DTO 完全相等，包括成员、金额、异常指纹与 completion。该组继续保留6.57差异导致的未配对，未执行真实接受/撤回。
- 浏览器真实搜索470.40：入口恢复28×28px，无旧提示行；Popover内容严格为OA1273.06、银行流水1273.06、票据凭证1279.63。1440px和390px均未溢出；已接受异常的账户/时间记录在既有抽屉可见。
- Popover 7次复测29–40ms，中位数31ms（首轮29–42ms，中位数29ms）；发布前46–65ms，中位数54ms。交互新增工作台请求0、写请求0、浏览器错误0。20个滚动帧间隔16.5–16.8ms，中位数16.7ms，滚动新增请求0。小样本说明本次交互正常，不代表长期或高并发SLO。
- 服务端loopback同一查询：1次预热、20次取样，P50=857.2ms、P95=913.9ms、P99=1010.3ms，满足既有P95≤1000ms/P99≤2000ms。
- 公网客户端独立HTTPS全耗时：发布前7次中位数1030ms；发布后两轮14次1069–1483ms，中位数1176.5ms。服务端指标达标，但公网端到端并未稳定低于1秒；此次前端修复没有改变API/SQL，不宣称公网查询性能提升，也不将公网抖动归因为已证实的网络原因。

- 现有 `production-route-shell.spec.ts` 生产只读巡检通过（16个核心路由，27.9秒）：无登录拦截、页面壳持续加载、浏览器错误或写请求。此项验证页面入口及读取，不替代所有页面写流程的生产测试；写流程由本地确定性测试保护。
- 无主库操作、迁移或数据库备份。本次私有临时快照、脚本与日志清理；生产发布证据保留服务器受控目录，桌面/窄屏已人工检查。桌面截图另保存在 Codex visualization 目录，不入业务仓库。
