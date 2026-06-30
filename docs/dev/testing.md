# 测试与验证

本文件是开发验证入口。测试闭环的全局状态见 `testing-closure-state.md`，跨页面/API/read model/worker 依赖地图见 `testing-closure-dependency-map.md`，Spec-first Browser e2e 审计规则见 `spec-first-e2e-audit.md`，审计队列见 `spec-first-e2e-inventory.md`，nightly CI 规则见 `nightly-ci.md`。

## 验证层级

- 本地目标验证：修改某个模块时，优先运行 `docs/modules/<module>/tests.md` 中列出的模块命令。
- 统一本地验证：运行 `bash scripts/verify.sh all`，覆盖后端、前端 Vitest/build、deterministic Playwright browser smoke 和文档检查。
- Nightly CI：每天自动运行后端全量 unittest、前端 Vitest、前端 build、Playwright browser smoke 和文档检查。
- 发布前验证：涉及生产数据、read model、worker、OA、Redis/RabbitMQ/PostgreSQL runtime 或部署资产时，按模块文档和运维文档补充 dry-run、staging 或生产只读 smoke。
- 真实基础设施验证：涉及 read model / worker 最新状态时，优先运行 `bash scripts/verify.sh infra-smoke`；默认只做安全 dry-run / preflight。需要真正 enqueue 并等待 worker drain 时，必须显式设置 `FIN_OPS_INFRA_SMOKE_APPLY=1`，并只在 staging 或已批准的生产窗口使用。

## 统一验证入口

```bash
bash scripts/verify.sh all
```

可选目标：

```bash
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
bash scripts/verify.sh infra-smoke
```

`infra-smoke` 是真实基础设施 gate 的统一入口。默认本地没有 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL` 时，它运行 read model SLO、runtime sync closure gate、write-operation SLO、RabbitMQ staging preflight 工具的契约测试，并跳过真实连接；设置真实 staging PostgreSQL 后会追加 `read_model_slo_smoke --critical-only` 的 dry-run scope discovery，不会写入 queue；只有同时设置 `FIN_OPS_INFRA_SMOKE_APPLY=1` 时才追加 `--apply`，真正 enqueue refresh events 并等待 worker drain。设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed` 等 operation profile 后，会对最近真实业务写入产生的 durable outbox events 运行只读 `write_operation_slo_audit`；设置 `FIN_OPS_TEST_DATABASE_URL` + `RABBITMQ_TEST_URL` 时还会运行 RabbitMQ staging preflight。它不会被 `verify.sh all` 默认执行。

生产外部 gate 前先运行只读输入预检；`bash scripts/verify.sh infra-smoke` 默认也会输出这份预检报告：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json
```

该工具只报告 `FIN_OPS_E2E_OA_TOKEN`、`FIN_OPS_E2E_ADMIN_TOKEN`、HTTP SLO token/cookie、PostgreSQL URL、write scenario 和审批 ticket 是否配置，不输出 secret 值。若需要 CI/脚本在缺少外部输入时失败，可加 `--require-ready`，缺输入时退出码为 `2`。admin Browser/AppHealth、authenticated HTTP/SSE 和 write-operation apply 缺 token、cookie、scenario 或 approval 时，应归类为 `external_input_required`，不是产品代码或 deterministic E2E 失败。

对真实写入链路，不要只用直接 enqueue 的 `read_model_slo_smoke` 证明闭环；还要在 staging/发布前窗口运行 `write_operation_slo_audit` 检查真实业务操作产生的 durable refresh events。导入类页面可分别运行 `--operation bank_import_confirmed`、`--operation invoice_import_confirmed`、`--operation etc_import_confirmed`，或者通过统一入口设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`。其中 `bank_import_confirmed` 同时审计通用 `*.read_model.refresh` 事件、银行账户余额 `bank_account_balance.read_model.refresh` 和银行明细 `import.fact.changed` dirty scope drain；发布前仍要通过 `/api/bank-details/accounts` 或页面 smoke 确认账户余额 API freshness gate 返回 fresh。

## 后端

基础检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

全量单元测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 前端

```bash
cd web
npm test
npm run build
npm run e2e:smoke
```

## Browser e2e / Playwright

默认 browser e2e 使用 Playwright Chromium、Vite dev server 和 deterministic API mocks，目标是用真实浏览器保护 shell、导航、会话 gate、权限 gate、App Status/AppHealth，以及高 fan-out 页面之间的核心业务链路。目前 smoke 覆盖 app shell / AppHealth 权限门禁、compact/mobile drawer、embedded OA shell、`finance table system -> AppHealth 共享宽表窄屏横向滚动、右侧列可见、read model/worker 表格可读和刷新控件无遮挡`、`read_export_only/full_access/admin` 全页面角色矩阵和高风险写入口权限门禁，并覆盖 `bank details initial current-year view -> balances/default columns/relation fields/fresh empty state`、`关联台 confirm -> bank details relation tags`、`bank details relation fields -> real browser download`、`bank details account/custom date/keyword/category filtered export and pagination -> download content and read_export_only zero mutation`、`bank details denied/expired session gate -> zero protected API and admin category write`、`bank details large table/narrow overlays -> scroll and controls uncovered`、`bank details category confirmation/manual assignment -> refetch and revoke/clear recovery`、`bank details auto tag rules save/reapply -> freshness feedback and blocked sync warning`、`bank details account/transaction read model non-fresh and network recovery -> 诊断、retry、false-empty 防护和导出业务错误`、`关联台未正式化 decision / 历史 candidate 兼容值 -> 银行明细/待找发票/OA 待付款不驱动 linked-only 状态`、`关联台 relation-backed pending invoice read model refreshing/stale -> 诊断、导出禁用和 canonical-safe 选择发票入口`、`关联台 withdraw preview/submit -> relation barrier -> open recovery`、`关联台 split_candidate preview/submit -> relation barrier -> suppress 自动建议`、`关联台 stale/refreshing/false-empty/OA dirty/OA refreshing/refresh failed/write failure/barrier timeout/refetch failure -> 状态提示和写入口 gate`、`关联台 transient network retry/409 stale preview/duplicate submit -> 单次 mutation 或重新预览`、`关联台 exception apply/cancel/ignore/unignore -> barrier/fresh refetch -> processed/ignored/open recovery`、`关联台 cash special pass-through/ticket purchase/cancel -> operation barrier and no hidden browser/UI errors`、`关联台 large dataset pagination/search/detail/tri-pane scroll -> selection preserved and controls uncovered`、`关联台 read_export_only/full_access/admin write-safety blocked -> open/paired/processed/ignored read-side visible and write entries hidden/disabled with zero mutation APIs`、`关联台 confirm -> pending invoices invoice status`、`pending invoices filter/sort -> 默认状态过滤、列筛选和金额排序 query/可见行一致`、`pending invoices rules save -> PUT contract、pending_invoice barrier 和 rows refresh、暂时失败时抽屉内错误/草稿保持/不全局阻塞并可重试`、`pending invoices attach existing -> 多选流水/发票、候选流水关联 chip、preview/confirm、confirm 暂时失败后错误可见且不半写并可重试、conflict 禁用确认和 rows refresh`、`pending invoices income status -> 收入多选、单次批量写入、rows refresh、拒绝/暂时失败错误可见且零半写、暂时失败可重试`、`pending invoices confirmed relation export -> 当前筛选/排序、不带分页、download content 包含 OA/发票/relation 字段`、`pending invoices row-limit export -> 后端错误可见且不生成下载文件`、`OA pending relation confirm -> rows refresh -> 支付少了变已支付`、`OA pending in-progress confirm-paid -> 单次 mutation、防重、rows refresh 后已写回、失败零半写`、`OA pending in-progress bank-link -> 抽屉禁选/筛选、rows refresh 后仍未写回、confirm-paid 零调用、失败零半写`、`output invoice collection search/filter/sort/page-size -> rows URL contract and visible rows synchronized`、`output invoice read_export_only -> read-only rules/receipt history/export visible and status/red relation/receipt/settings zero mutation`、`output invoice red relation confirm -> rows refresh -> manual evidence -> relation fields export -> tax/cost downstream fresh read models visible`、`input invoice usage filter/sort/page-size -> rows URL contract and visible rows synchronized`、`input invoice read_export_only -> export preview enabled, payment rules read-only, OA reverse preview cannot create drafts, durable write endpoints zero-called`、`input invoice rows read model non-fresh -> refreshing diagnostics without stale rows or true empty state`、`input invoice relation detail non-fresh -> detail unavailable diagnosis without stale rows/loading leak`、`input invoice fresh +N relation detail -> drawer summaries from row read model`、`input invoice export current filters -> download without pagination, row-limit/non-fresh blocked`、`input invoice relation linked/unlinked -> OA reverse 二态筛选和 linked rows evidence`、`cost statistics excludes non-active relation -> confirmed cost project/detail visible`、`tax offset permission matrix -> read-export 可读无保存/导入入口、forbidden/expired 零 protected API、admin 写入口可见`、`tax offset read model non-fresh -> refreshing/stale/missing/failed 防 false-empty、禁用保存、stale 自动恢复`、`tax offset plan save conflict -> 409 错误可见、不显示保存成功、不刷新伪成功`、`tax offset large/narrow tables -> 390px 搜索/排序/筛选/共享横向滚动和按钮无遮挡`、`tax offset relation fan-out -> fresh tax read model and input plan row visible`、`batch accounting submit/withdraw -> workbench_relation barrier -> bucket recovery`、`turnover ledger manual closure confirm/withdraw -> turnover/workbench barriers -> closure recovery`、`bank import preview/confirm -> workbench refresh -> bank details imported row`、`invoice import input/output preview/confirm -> workbench refresh`、`ETC invoice ready task zip preview/confirm -> background import job`、`tax offset recalculate/save -> certified import preview/confirm -> tax page refresh`、`settings data reset impact/password/job polling -> settings reload`、`output invoice collection status/reminder save -> rows refresh -> formal receipt create/void/reissue/history`、`input invoice OA reverse selected subset -> OA draft -> submitted history`、`ETC ticket imported business batch -> OA draft -> manual submitted bucket`、`OA pending payments rows/filter/sort -> OA/bank/invoice/rules drawers`、`no-OA tag scope save -> all-scope freshness barrier -> list reload`、`no-OA selected row submit -> freshness barrier -> submitted withdraw -> history`、`cost statistics project drilldown -> transaction detail -> export download/row-limit feedback` 的跨页面/跨读模型同步。

`tests/test_nightly_ci.py` 会校验每个非生产 `web/e2e/*.spec.ts` 都列入 `npm run e2e:smoke`，并且默认 smoke 不包含生产 opt-in specs。新增 deterministic Browser spec 后，必须同步更新 `web/package.json` 的 `e2e:smoke`；新增生产 smoke 则应放在单独 `e2e:production-*` 脚本中。

生产 route-shell browser smoke 的测试文件不进入默认 deterministic smoke，也不随正常 app release 打包。需要准备独立 runner 输入时，只能使用本地 bundle 工具生成脱敏 manifest 和批准文件集：

```bash
python3 scripts/package_production_browser_smoke.py \
  --release-name <active-release-name> \
  --output /tmp/fin-ops-production-browser-smoke.tar.gz
```

该 bundle 只包含 `production-route-shell.spec.ts`、`strictTest.ts`、Playwright 配置和 package metadata/lockfile；不包含 `node_modules`、浏览器二进制、`web/dist`、admin production spec、截图、trace、video、HTML report、token、cookie 或环境 secret。生成 bundle 不会运行浏览器，不会登录 OA，也不会访问生产。实际生产 browser evidence 仍需要单独批准的 runner runtime、内存 token broker、pre/post health/read-model aggregate checks 和脱敏 artifact contract。

所有 `web/e2e/*.spec.ts` 必须从 `web/e2e/fixtures/strictTest.ts` 导入 `test` / `expect`。该 fixture 默认捕获 app 主动打印的 `console.error`、`pageerror`、非预期 `requestfailed` 和原生 `dialog`，因此“业务操作成功但浏览器报错、弹窗报错或请求异常”的场景会让 E2E 失败。浏览器自动生成的 HTTP status resource log 属于 API response 结果，不作为隐藏 JS 错误；对应 spec 必须用页面 alert、禁用下载、零 mutation、零半写等业务断言证明 400/401/403/409/500/503 等响应已被正确消费。SPA 路由切换导致的 `net::ERR_ABORTED` 生命周期中断也不作为隐藏错误。Playwright 配置在 CI 下启用 `forbidOnly`，且 `tests/test_playwright_e2e_strict_diagnostics.py` 会阻止后续 spec 绕过 strict fixture 或提交 `test.only` / `describe.only`。

本轮新增 OA pending rows/detail non-fresh Browser 覆盖：rows `read_model_status=refreshing` 时显示刷新诊断而不显示真实空态，detail 202 时 drawer 显示“详情暂不可用”。

本轮新增 OA 待付款 rows 临时失败恢复 Browser 覆盖：首屏 `/api/oa-pending-payments/rows` 暂时 503 时显示错误 alert 和错误态空行，不显示普通空态；点击刷新后等待 rows 200/fresh，业务行和分页恢复。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 OA Mongo/MySQL、PostgreSQL/RabbitMQ/Redis/systemd worker drain。

本轮新增成本统计 explorer 临时失败恢复 Browser 覆盖：首屏 `/api/cost-statistics/explorer?month=2026-03&project_scope=active` 暂时 503 时显示“成本统计数据加载暂时失败，请刷新后重试。”，不显示普通空态、不渲染按时间表、不允许打开导出中心；点击刷新后等待 explorer 200/fresh，按时间成本流水和导出入口恢复。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty / export 防伪成功风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 或真实网络中断恢复。

本轮新增批量账务 GET 临时失败恢复 Browser 覆盖：首屏 `/api/batch-accounting` 暂时 503 时显示“批量账务数据加载暂时失败，请刷新后重试。”，不显示普通“当前年份暂无批量账务流水”空态；点击刷新后等待列表 200/fresh，批量账务银行行、可关联 OA 表和未选择时禁用的提交按钮恢复，失败文案清除。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 或真实网络中断恢复。

本轮新增外部往来 grouped ledger 临时失败恢复 Browser 覆盖：首屏 `/api/turnover-ledger` 暂时 503 时显示“往来款台账加载暂时失败，请刷新后重试。”，不显示普通“暂无往来款台账”空态；点击 `刷新台账` 后等待列表 200/fresh，外部往来 grouped table、云南建设有限公司行和未选择时禁用的确认闭环按钮恢复，失败文案清除。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 或真实网络中断恢复。

本轮新增免 OA 流水批次 list 临时失败恢复 Browser 覆盖：首屏 `/api/no-oa-bank-batches` 暂时 503 时显示“免OA流水批次加载暂时失败，请刷新后重试。”，不显示普通“当前标签下暂无流水”空态；点击 `刷新` 后等待列表 200/fresh，主/子标签、建设银行流水表和未选择时禁用的提交按钮恢复，失败文案清除。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实网络中断恢复或 mutation 级失败恢复。

本轮新增 ETC 票据 business-batches 临时失败恢复 Browser 覆盖：首屏 `/api/etc/business-batches` 暂时 503 时显示“ETC业务批次加载暂时失败，请刷新后重试。”，不显示普通“无匹配批次。”空态；点击 `刷新` 后等待列表 200，未提交业务批次、ETC 发票明细和提交 OA 入口恢复，失败文案清除。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险；submitted reset/delete 已由后续 Browser 覆盖，不替代真实对象存储/Nginx 上传中断、真实 OA、真实 worker drain 或 import confirm 等后续 Browser/staging 风险。

本轮新增 ETC 票据 OA draft mutation 临时失败恢复 Browser 覆盖：创建 OA 草稿第一次 `POST /api/etc/business-batches/{id}/oa-draft` 暂时 503 时显示“OA 草稿创建暂时失败，请重试。”，不进入 `OA提交确认` 伪成功，创建草稿 dialog 保持可重试；第二次点击成功后进入提交确认并清除失败文案。该证据覆盖 ETC 本地 mutation 级 `NETWORK-RECOVERY` 的 OA draft 子链路，不替代真实 OA 页面、对象存储/Nginx、大 ZIP、真实 worker drain 或其它 mutation 级失败恢复。

本轮新增 ETC 票据 manual OA status mutation 临时失败恢复 Browser 覆盖：人工确认已提交第一次 `POST /api/etc/business-batches/{id}/manual-oa-status` 暂时 503 时显示“人工确认暂时失败，请重试。”，不切到 `已提交` bucket，`OA提交确认` 保持可重试；第二次点击成功后才进入已提交 bucket 并清除失败文案。该证据覆盖 ETC 本地 mutation 级 `NETWORK-RECOVERY` 的 manual status 子链路；submitted reset/delete 已由后续 Browser 覆盖，不替代真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP、真实 worker drain 或 import confirm。

本轮新增 ETC 票据 business batch delete mutation 临时失败恢复 Browser 覆盖：删除业务批次第一次 `DELETE /api/etc/business-batches/{id}` 暂时 503 时显示“ETC业务批次删除暂时失败，请重试。”，不移除原批次行、不关闭删除确认弹窗；第二次点击成功后才关闭弹窗、刷新列表为空并清除失败文案。该证据覆盖 ETC 本地 destructive mutation 级 `NETWORK-RECOVERY` 的 delete 子链路；已提交 reset/delete 子链路已由后续 Browser 覆盖，不替代 import confirm、真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP 或真实 worker drain。

本轮新增 ETC 票据 submitted reset/delete mutation 临时失败恢复 Browser 覆盖：已提交 bucket 下删除业务批次第一次 `DELETE /api/etc/business-batches/{id}` 暂时 503 时，请求体必须携带 submitted `expectedVersion` 和“释放发票”原因，页面显示“ETC业务批次删除暂时失败，请重试。”，不移除已提交批次行、不改变 `已提交 1` 计数、不关闭删除确认弹窗；第二次点击成功后才关闭弹窗、刷新已提交列表为空并清除失败文案。该证据覆盖 ETC 本地 destructive mutation 级 `NETWORK-RECOVERY` 的 submitted reset/delete 子链路，不替代真实 relation command service 内部异常、真实 OA 页面、真实对象存储/Nginx 上传中断、大 ZIP、import confirm 或真实 worker drain。

本轮新增 ETC 票据 source file delete mutation 临时失败恢复 Browser 覆盖：删除源文件第一次 `DELETE /api/etc/reconciliation-tasks/{taskId}/source-files/{fileId}` 暂时 503 时显示“ETC源文件删除暂时失败，请重试。”，不移除文件行、不关闭删除确认弹窗；第二次点击成功后才关闭弹窗、刷新文件列表为空并清除失败文案。该证据覆盖 ETC 本地 destructive mutation 级 `NETWORK-RECOVERY` 的 source file delete 子链路，不替代真实对象存储/Nginx、大 ZIP、import confirm 或真实 worker drain。

本轮新增 ETC 票据 ticket-root source upload mutation 临时失败恢复 Browser 覆盖：上传票根网 TXT 第一次 `POST /api/etc/reconciliation-tasks/{taskId}/ticket-root-files` 暂时 503 时显示“ETC票根网文件上传暂时失败，请重试。”，不追加 `ticket-root-upload.txt`，上传入口保持可用；第二次选择同一文件成功后才追加 TXT source file 并清除失败文案。该证据覆盖 ETC 本地 source upload mutation 级 `NETWORK-RECOVERY` 的 ticket-root 子链路，不替代真实对象存储写入失败/权限、Nginx 上传中断、大 ZIP、import confirm 或真实 worker drain。

本轮新增银行流水导入 Browser 负面覆盖：慢预览期间预览/清空/确认动作锁定且只提交一次 preview、重复项明细、损坏文件混合上传 file-level error、未导入项明细、confirm 只提交正常文件 ID、账户冲突取消零提交、`preview_stale` 不创建 job/不刷新 Workbench、confirm 失败不显示成功。confirm 成功后进入银行明细和成本统计的成功节点也会检查页面没有导入失败、后台导入失败、read model 失败等可见错误残留。

本轮新增发票导入 Browser 覆盖：慢预览期间预览/清空/确认动作锁定且只提交一次 preview、重复项明细、损坏文件混合上传 file-level error、未导入项明细、confirm 只提交正常文件 ID、`preview_stale` 不创建 job/不刷新 Workbench、confirm 失败不显示成功；confirm 成功后继续打开销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计，断言六个下游 API 返回 `read_model_status=fresh` 且页面展示导入影响行，并在导入页和各下游成功节点检查没有导入失败、后台导入失败、read model 失败等可见错误残留。

本轮新增 ETC 发票导入 Browser 负面覆盖：`preview_stale` 不展示后台导入成功、`stale_reconciliation_task_preview` 清空旧预览并要求重新预览、confirm 失败不展示后台导入成功，且全部不走通用 `/imports/files/*`。confirm job 成功和下游 ETC 票据、税金抵扣、成本统计 fresh 成功节点也会检查没有导入失败、后台导入失败、read model 失败等可见错误残留。

本轮校准 ETC 导入到成本统计的 Browser fan-out 覆盖：`imports-etc-invoices-flow` 中 confirm 成功后继续进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并验证 `ETC导入通行成本项目`、`ETC高速通行费` 和 `ETC导入通行服务商` 出现在项目/流水视图。该证据覆盖 `COST-E2E-010` 的 ETC import 子链路；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增 no-OA Spec-first Browser 覆盖：`bank-flow-rule-batches-flow` 中 `read_model_status=stale -> fresh` 会保持可见 rows、不显示普通空态并自动重读；标签准入保存会提交 `PUT /api/no-oa-bank-batches/tag-selection`，等待 `no_oa_bank_batch:all` operation barrier fresh 并重读列表；selected-row submit 成功并等待 operation barrier 后继续进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并验证 `免OA手续费成本项目`、`手续费`、`网银手续费` 和 `建设银行` 出现在项目/流水视图；随后回 no-OA 完成撤回和历史只读断言。该 flow 在标签保存、submit、成本统计 fan-out、withdraw 和 history 成功后都会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示。该证据覆盖 `NO-OA-E2E-002..005`、`NO-OA-E2E-008` 和 `COST-E2E-010` 的 no-OA submit 子链路；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增 turnover Spec-first Browser 覆盖：`turnover-ledger-flow` 中 grouped ledger 首屏暂时 503 会显示错误态、防普通空态并通过 `刷新台账` 恢复；`read_model_status=stale` 会显示非最新 warning、保留当前 flow rows、选中两条真实流水后仍禁用确认闭环且零 confirm mutation；标签准入保存会提交 `PUT /api/turnover-ledger/tag-selection`，等待 `turnover_ledger:all` operation barrier fresh 并重读台账；manual closure confirm 成功并等待 operation barrier 后继续进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并验证 `外部往来闭环成本项目`、`外部往来款付款`、`浏览器 e2e 归还借款` 和 `建设银行` 出现在项目/流水视图；随后回外部往来完成撤回和闭环 chip 恢复断言。该 flow 在失败恢复、标签保存、confirm、成本统计 fan-out 和 withdraw 成功后都会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示。该证据覆盖 `TURNOVER-E2E-001..005`、`TURNOVER-E2E-007` 和 `COST-E2E-010` 的 turnover manual closure 子链路；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增 batch accounting Spec-first Browser 校准：`batch-accounting-flow` 在真实 Chromium 中覆盖首屏 GET 临时失败后手动刷新恢复、窄桌面银行 rail 可读性、stale relation read model 诊断下保留当前银行/OA rows、防普通空态且零 mutation，以及未提交 bucket 选择银行/OA、金额归零提交、`workbench_relation` operation barrier、已提交 bucket 展示 OA 明细、撤回原因、撤回后 barrier 和回到未提交 bucket；四个 Browser 流都捕获 pageerror、console.error、requestfailed 和未预期 dialog，submit/withdraw/恢复到未提交成功后还会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示。该证据覆盖 `BATCH-E2E-001`、`BATCH-E2E-002`、`BATCH-E2E-004`、`BATCH-E2E-005`、`BATCH-E2E-009`；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增 settings Spec-first Browser 校准：`settings-data-reset-flow` 中 data reset 用户路径覆盖影响确认、OA 密码复核、job 202、job polling、settings reload、成功反馈和严格浏览器错误捕获；reset 完成后同一真实 Chromium 流继续进入银行明细，断言 `bank_detail` rows 返回 `read_model_status=fresh` 且旧银行流水为空，再进入待找发票断言 `pending_invoice` rows 返回 `fresh` 且业务行可见。同一 spec 还覆盖 admin 在设置页把项目标记完成并保存，断言 `/api/workbench/settings` POST 携带 `completed_project_ids`，随后进入成本统计等待 active/all 两次 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`；active scope 排除已完成项目，切到 all scope 后保留该项目和金额。data reset 完成、settings 保存和成本统计 active/all fan-out 成功后都会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示。该证据覆盖 `SETTINGS-E2E-002..003`、`RESET-E2E-005` 本地 Browser fresh contract 和 `COST-E2E-010` 的 settings/project scope 子链路；真实 worker drain、真实 data reset 备份恢复和真实 OA 仍走 `infra-smoke` / staging gate。

本轮新增 ETC 票据管理 Spec-first Browser 校准：`etc-tickets-flow` 在真实 Chromium 中覆盖未提交业务批次首屏、business-batches 首屏 GET 暂时失败后刷新恢复、ETC 发票明细、未提交 business batch delete 暂时失败后不误删且可重试、已提交 business batch reset/delete 暂时失败后不误删已提交行/不改计数且可重试、source file delete 暂时失败后不误删且可重试、ticket-root source upload 暂时失败后不伪上传且可重试、创建 OA 草稿、单次 `oa-draft` mutation、OA draft 暂时失败后不伪成功并可重试、OA 提交确认、单次 `manual-oa-status` mutation、manual status 暂时失败后不切已提交 bucket 并可重试、已提交 bucket、人工确认已提交状态和严格浏览器错误捕获；delete、source file delete、ticket-root upload、OA 草稿创建和人工确认成功后都会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示。该证据覆盖 `ETC-TICKET-E2E-001..006` 和本地 `NETWORK-RECOVERY` false-empty/delete/submitted reset/source file delete/source upload/OA draft/manual status mutation 子链路；大 ZIP、Workbench summary 和历史 migration 由组件/API/后端覆盖，真实 ZIP/对象存储/OA/worker drain 和其它 mutation 级失败恢复仍走 `infra-smoke` / staging gate。

本轮新增 App Health Spec-first Browser 校准：`app-shell` 在真实 Chromium 中覆盖 admin shell/dashboard、read-export admin-only gate、forbidden session gate、expired session gate、dashboard protected API 零调用和严格浏览器错误捕获；expired session 的 `/api/session/me` 预期 401 resource error 作为认证 gate 例外，其它 console/page/request/dialog error 仍会失败。该证据覆盖 `APP-HEALTH-E2E-001..004`；App Status overview、runtime/readiness/worker/queue/ready/SSE gate 和 registry completeness 由组件/API/service/tool tests 覆盖，真实 PostgreSQL/RabbitMQ/Redis/systemd/Nginx/OA iframe/大库 metrics 仍走 `infra-smoke` / staging gate。

本轮新增权限与审计 shared Spec-first 校准：`permissions-role-matrix` 在真实 Chromium 中覆盖 `read_export_only` 全页面可读零 mutation、settings/tax/三类 import/no-OA 高风险入口禁用或隐藏、关联台列顺序拖拽 settings 保存入口、关联台现金处理行级菜单、银行分类确认、银行人工待分类、银行自动标签、pending invoices 选择已有发票/收入状态/规则保存、进项支付规则、进项 OA reverse、销项收款规则/收据历史、OA pending confirm/link-bank/支出流水无需开票规则、batch accounting submit 与 submitted bucket withdraw、turnover tag/closure/extra 入口、ETC submit/new/delete/source file 上传/确认对账/人工核对处理代表性写入口只读 gate、`full_access` 普通业务入口与 admin-only gate、`admin` 高风险入口和严格浏览器错误捕获，并扫描 read-export 首屏和 opener registry 已打开动态区域的 visible enabled 写控件，若保存/提交/确认导入/撤回/删除/关联/写回/拖动列等高风险动作仍可点会失败。进项 OA reverse 的 preview 是 read-like POST 例外，但 OA draft、batch 和 manual status durable write endpoint 仍断言零调用。该证据覆盖 `PERM-E2E-001..002`、`PERM-E2E-004..005`、`PERM-E2E-009`，并推进 `PERM-E2E-003`；API/audit/secret contract 由后端测试覆盖。`tests/test_permissions_write_entry_inventory.py` 已自动校验新增 page registry route 必须进入写入口 inventory 和 read-export role matrix、`covered-*` inventory row 必须引用 Browser E2E 证据、role matrix opener id 必须在 inventory 登记。`PERM-E2E-003` 仍为 partial，因为尚未由 role matrix 自动打开的所有页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header 和生产审计 smoke 不能写成本地 covered。

本轮新增销项收款状态/收据和红蓝票下游 Browser 覆盖：状态/提醒保存后 rows refresh 显示 `待冲红`，正式收据创建后 rows refresh 并可打开历史，随后在真实 Chromium 中继续作废收据、断言 reason POST body、history/rows refresh，再重开收据并展示新收据号；确认红蓝票关系后，测试先打开筛选内容导出，断言 export-preview 与真实下载文件都包含红蓝票 relation 字段、红字发票号、来源和依据；随后继续导航到税金抵扣和成本统计，断言两个下游页面都重新请求自己的 fresh read model 并展示 relation 影响后的数据；上述成功写节点都会检查页面没有残留操作失败/同步失败/read model 失败等可见错误提示；search 暂无独立前端 route，保留 API/runtime 覆盖。

本轮新增税金抵扣 read model 非 fresh Browser 覆盖：`tax-offset-flow` 中 `refreshing` / `missing` / `failed` 状态不显示真实空态、不泄露 stale reason、不允许保存计划，`stale -> fresh` 自动重试后恢复统计卡和表格；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增税金抵扣计划保存 conflict Browser 覆盖：`tax-offset-flow` 中修改计划后保存返回 409 source/version conflict 时，页面显示“税金抵扣数据已变化，请刷新后重新保存。”，不显示保存成功，不触发 `/api/tax-offset` 伪刷新，保存按钮恢复可用；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮补齐进项发票使用、税金抵扣和待找发票规则保存成功写流的 UI 错误残留 guard：`input-invoice-usage-flow` 在支付规则保存、OA 反提草稿创建和用户确认已提交后检查没有操作失败/保存失败/同步失败/read model 失败残留；`tax-offset-flow` 在保存计划和已认证发票导入刷新后检查没有保存/导入/read model 失败残留；`pending-invoices-rules-save-flow` 在规则保存、barrier 和 rows refresh 后检查没有保存失败/同步失败/read model 失败残留。这些 guard 不替代真实 worker drain，真实基础设施仍走 `infra-smoke` / staging gate。

本轮补齐待找发票选择已有发票 confirm 暂时失败恢复：`pending-invoices-attach-existing-flow` 在真实 Chromium 中让第一次 `POST /api/pending-invoices/attach-existing-invoices` 返回 503，断言后端错误文案可见、抽屉/preview/选择保持、确认按钮可重试、rows 不重读且状态不半写；第二次确认成功后才关闭抽屉、刷新 rows 到 `已支付已开票` 并检查没有操作失败/同步失败/read model 失败残留。该 guard 不替代真实 worker drain，income status、rules save、withdraw 等其它 mutation 的真实网络中断恢复仍走后续 Browser/staging gate。

本轮补齐待找发票收入批量状态保存暂时失败恢复：`pending-invoices-income-status-flow` 在真实 Chromium 中让第一次 `PUT /api/pending-invoices/income-statuses` 返回 503，断言后端错误文案可见、已选两条收入流水保持、状态仍为 `未开票`、rows 不重读且没有逐行 fallback API；第二次点击 `标记现金收入` 成功后才刷新 rows 到 `现金收入`、清空选择并检查没有操作失败/同步失败/read model 失败残留。该 guard 不替代真实 worker drain，rules save、withdraw 等其它 mutation 的真实网络中断恢复仍走后续 Browser/staging gate。

本轮补齐待找发票规则保存暂时失败恢复：`pending-invoices-rules-save-flow` 在真实 Chromium 中让第一次 `PUT /api/pending-invoices/rules` 返回 503，断言规则抽屉内错误文案可见、已勾选草稿保持、没有不可点击的全局操作失败弹窗、没有触发 `operation-barrier/status` 或 rows 刷新；第二次保存成功后才等待 `pending_invoice:expense:requires_invoice` barrier、rows refresh 和刷新中反馈。产品侧修正为 `runOperation` 增加 `blockOnError=false`，规则抽屉保存失败由抽屉本地错误反馈承接，默认全局操作失败阻塞行为不变并由 Vitest 覆盖。该 guard 不替代真实 worker drain，withdraw 等其它 mutation 的真实网络中断恢复仍走后续 Browser/staging gate。

本轮补齐 Workbench relation fan-out 下游成功节点的 UI 错误残留 guard：`workbench-relation-fanout`、`pending-invoices-fanout`、`input-invoice-relation-fanout`、`cost-statistics-relation-fanout`、`workbench-relations-oa-pending-fanout` 和 `workbench-relations-tax-offset-fanout` 在 Workbench confirm、operation barrier、目标页面重新读取 fresh/read-side 数据并显示业务结果后，都会检查没有操作失败、同步失败、read model 失败或 barrier timeout 残留。该 guard 专门防止“关系事实已写入、下游页面也刷新成功，但用户仍看到错误弹窗/错误条”的假成功；真实 worker drain 仍走 `infra-smoke` / staging gate。

本轮补齐 Workbench 自身写流成功节点的 UI 错误残留 guard：`workbench-withdraw-flow`、`workbench-candidate-split-flow`、`workbench-exception-flow` 和 `workbench-network-recovery-flow` 在撤回关联、拆分候选、异常处理 apply/cancel、ignore/unignore、网络失败重试成功和重复提交防护成功后，都会检查没有操作失败、同步失败、read model 失败或 barrier timeout 残留。`workbench-stale-error-flow` 中 409、barrier timeout、fresh refetch failed 等 negative path 继续断言错误可见，不接入成功 guard。

本轮补齐银行明细和待找发票导出/分类成功节点的 UI 错误残留 guard：`bank-details-category-flow` 在候选确认、撤销、人工补分类和清除成功后检查没有保存/撤回/同步/read model 失败残留；`bank-details-export-download`、`bank-details-filtered-export-permissions` 和 `pending-invoices-export-download` 在真实 download event、文件内容断言和成功反馈后检查没有导出失败、同步失败或 read model 失败残留。row-limit、forbidden/expired session 等 negative path 继续断言错误或权限 gate 可见，不接入成功 guard。

本轮新增税金抵扣权限细分 Browser 覆盖：`tax-offset-flow` 中 read-export 用户可读统计卡和表格但无保存/导入入口且零 tax write API；forbidden/expired session 在加载 `/api/tax-offset` 前被 SessionGate 阻断；admin 可见保存和已认证导入入口。后端写权限拒绝仍由 API contract 测试承担。

本轮新增税金抵扣大数据窄屏 Browser 覆盖：`tax-offset-flow` 在 390px Chromium 下启用 81 张销项和 92 张进项长字段数据，验证保存/导入按钮无遮挡、搜索第 89 条进项、清空搜索、时间排序、对方名称筛选、共享横向滚动和右侧金额列可见；同时修复 tax 工作区窄屏 `min-width:auto` 撑宽页面、共享筛选菜单被桌面 sidebar inset 推出 viewport 的 UI 回归。

本轮新增销项收款权限 Browser 覆盖：`read_export_only` 用户可打开只读规则、已出收据历史和导出预览，但状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开均不可触发，全程 mutation API 为 0。

本轮新增销项收款列表 Browser 覆盖：fresh 首屏后依次验证 keyword search、发票号码排序、收款状态 enum 筛选、发票号码 text 筛选和 page-size 切换，每一步都断言 rows URL contract、可见行同步、零 mutation 和无浏览器错误。

本轮新增销项收款 rows 临时失败恢复 Browser 覆盖：首屏 `/api/output-invoice-collections/rows` 暂时 503 时显示错误 alert 和错误态空行，不显示普通空态，`筛选内容导出` 禁用；点击刷新后等待 rows 200/fresh，业务行、分页和导出入口恢复。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。

本轮新增销项收款状态保存暂时失败恢复 Browser 覆盖：第一次 `PUT /api/output-invoice-collections/rows/{id}/collection-status` 返回 503 时，`状态/提醒` drawer 保持打开并显示“收款状态保存暂时失败，请重试。”，手动状态、状态备注和提醒备注草稿保持，`collection-reminder` endpoint 零调用，rows 不提前刷新且不伪装 `待冲红`；第二次保存成功后才刷新 rows 并清除失败文案。该证据覆盖本地 mutation 级 `NETWORK-RECOVERY` 的状态/提醒子链路，不替代 receipt create/void/reissue 暂时失败、真实 worker drain 或真实多用户 expectedVersion 冲突。

本轮新增销项收款提醒保存暂时失败恢复 Browser 覆盖，并修复前端恢复行为：`CollectionStatusReminderDrawer` 现在只有在 status/reminder 整体保存成功后才通知页面刷新 rows；第一次 status 已 200 但 `PUT /api/output-invoice-collections/rows/{id}/collection-reminder` 返回 503 时，`状态/提醒` drawer、提醒时间和提醒备注保持，错误文案可见，rows 不提前刷新且不伪装 `待冲红`；第二次点击保存只重试 reminder，不重复提交已保存且未改变的 status payload，reminder 成功后才关闭 drawer 并刷新 rows。该证据覆盖本地 mutation 级 `NETWORK-RECOVERY` 的 status/reminder 分步失败子链路，不替代真实 worker drain、真实多用户 expectedVersion 竞争或生产网络长时间中断。

本轮新增销项收款正式收据创建暂时失败恢复 Browser 覆盖：第一次 `POST /api/output-invoice-collections/rows/{id}/receipts` 返回 503 时，请求仍携带 `Idempotency-Key`，`待出收据预览` drawer 保持打开并显示“正式收据创建暂时失败，请重试。”，rows 不提前刷新、不显示 `已出收据`、不读取伪历史；第二次点击成功后才刷新 rows 并清除失败文案。该证据覆盖本地 mutation 级 `NETWORK-RECOVERY` 的 receipt create 子链路，不替代 receipt void/reissue 暂时失败、真实 PostgreSQL 锁等待/唯一约束冲突恢复、真实 worker drain 或生产历史样本。

本轮新增销项收款正式收据作废/重开暂时失败恢复 Browser 覆盖，并修复前端恢复行为：`ReceiptHistoryDrawer` 现在只有在作废/重开成功后才关闭原因弹窗；第一次 `POST /api/output-invoice-collections/receipts/{id}/void` 或 `/reissue` 返回 503 时，原因弹窗、输入值和历史抽屉保持，错误文案可见，history/rows 不提前刷新；第二次确认成功后才关闭弹窗并刷新 history/rows。该证据覆盖本地 mutation 级 `NETWORK-RECOVERY` 的 receipt void/reissue 子链路，不替代真实 PostgreSQL 锁等待/唯一约束冲突恢复、真实 worker drain 或生产历史样本。

本轮新增进项发票使用 rows 和 relation detail 非 fresh Browser 覆盖：rows `read_model_status=refreshing/stale` 时显示刷新诊断，不显示普通空态、旧行或空表；relation detail `read_model_status=stale/refreshing` 时 drawer 显示“详情暂不可用”，不长期 loading、不展示旧明细、不泄露 stale reason；全程零 mutation 且无浏览器错误。

本轮新增进项发票使用 rows 临时失败恢复 Browser 覆盖：首屏 `/api/input-invoice-usage/rows` 暂时 503 时显示错误 alert 和错误态空行，不显示普通空态，`筛选内容导出` 禁用；点击刷新后等待 rows 200/fresh，业务行、分页和导出入口恢复。该证据覆盖本地 `NETWORK-RECOVERY` / false-empty 风险，不替代真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。

本轮新增进项发票使用列表 Browser 覆盖：fresh rows 首屏锁定 `page_size=20`，filter-options 包含当前页外供应商证明筛选项不从当前页伪造，销方筛选、开票日期排序和 page-size 切换都断言 rows URL contract、可见行同步、零 mutation 和无浏览器错误。

本轮新增进项发票使用权限 Browser 覆盖：`read_export_only` 用户可读列表、打开导出预览，支付规则 drawer 只读且无保存/编辑控件，OA reverse preview 返回 `canCreateDraft=false` 并禁用创建草稿；除 read-like preview POST 外，payment rules save、OA draft、batch 和 manual status durable write endpoint 全程零调用。

本轮新增进项发票使用 fresh `+N` relation detail Browser 覆盖：点击行内 `+N` 后通过单行 read model relation detail endpoint 返回 200，drawer 展示两条 OA 摘要，不显示 loading 或不可用态，全程零 mutation 且无浏览器错误。

本轮新增进项发票使用当前筛选导出 Browser 覆盖：export-preview 和 export 请求携带当前 keyword/sort/filter、不带 `page`/`page_size`，真实 download event 产生 `input-invoice-usage.xlsx`，下载内容包含发票、供应商、OA、relation case 和 payment 字段；row-limit 返回结构化错误时不生成下载，export read model 非 fresh 时禁用下载。

本轮新增成本统计导出 Browser 覆盖：`read_export_only` 用户可在 time-view 打开导出中心，export-preview 和 export 请求携带 `view=time`、`month=2026-03`、`project_scope=active` 且不带 `page`/`page_size`，真实 download event 产生 `成本统计_全部期间_按时间统计.xlsx`，下载内容包含流水 ID、项目、费用类型、费用内容、对方户名、支付账户和筛选字段；row-limit 错误反馈仍保留。

本轮新增成本统计按银行/按费用类型 Browser baseline：`cost-statistics-flow` 在 fresh explorer 下从按时间切到按银行，选择银行账户和项目后打开银行对应流水详情；随后切到按费用类型，选择费用类型并打开流水详情。该测试覆盖 `COST-E2E-001` 中 bank/expense 真实浏览器基线，并收集 console/pageerror/requestfailed/dialog。

本轮新增成本统计 detail/export non-fresh Browser 覆盖：`cost-statistics-flow` 在 explorer fresh 但 transaction detail、export-preview 和 export 返回 non-fresh 409 时，页面不打开旧流水详情、不展示旧导出预览、不触发 download，并展示刷新错误；预期 409 资源日志被单独允许，其他 console/page/request/dialog 错误仍会失败。该测试覆盖 `COST-E2E-006` 的 detail/export 子链路。

本轮新增成本统计大数据窄屏 Browser 覆盖：`cost-statistics-flow` 在 390px Chromium 下启用 120+ 行长字段成本数据，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh` 后验证按时间表和项目下钻表均可横向/纵向滚动，右侧列在 viewport 内，导出入口、长项目和费用类型选择器未被遮挡，且没有 console/page/request/dialog 错误。该测试覆盖 `COST-E2E-008` 的本地 Browser 布局与交互风险；真实生产超大数据查询/下载耗时和 worker drain 仍走 `infra-smoke` / staging gate。

本轮新增 Finance Table System Browser 覆盖：AppHealth 代表性共享宽表在 390px 窄屏下必须可以横向滚动到请求性能和 read model 表格右侧列，刷新按钮不被遮挡，read model/worker 表格值可读，且没有 console/page error。该测试证明共享表格浏览器布局回归，不替代真实大数据 worker drain。

新增或重写 Playwright 前先按 `spec-first-e2e-audit.md` 建立或更新模块 `e2e-spec.md` 和 `e2e-coverage.md`。Playwright 的验收标准来自业务 Spec；代码只用于定位 route、selector、API mock 和运行细节。

```bash
cd web
npm run e2e:smoke
```

这类测试应优先覆盖用户可见业务流、导航、弹窗、下载、iframe、焦点、滚动、大表格、网络恢复和跨页面同步。真实 PostgreSQL/RabbitMQ/Redis/systemd worker/OA Mongo/对象存储不属于默认本地 mock e2e，应通过 staging、只读生产 smoke 或显式 runtime gate 补充。

## 文档变更检查

文档结构调整后至少执行：

```bash
find docs -maxdepth 3 -type f -name '*.md' | sort
rg -n "docs/product/|OA 集成当前 app 技术方案" README.md docs backend web deploy -g '*.md'
PYTHONPATH=backend/src python3 -m unittest tests.test_spec_first_e2e_docs -v
bash scripts/verify.sh docs
```

`bash scripts/verify.sh docs` 会检查长期文档入口、Spec-first E2E 全局文档，以及每个 `docs/modules/<module>/README.md` 对应的 `e2e-spec.md` / `e2e-coverage.md` 是否存在。`tests.test_spec_first_e2e_docs` 进一步校验模块索引、全局 inventory、Spec ID 到 coverage 的映射，以及 coverage/inventory 中登记的 `web/e2e/...` Browser 证据路径是否仍指向当前文件或能匹配真实 glob。如果只是文档重排，不要求运行业务测试；但必须检查路径和索引不会继续指向已移动位置。

## 测试闭环维护规则

- 每次修改或新增功能前，先识别目标模块并读取 `docs/modules/<module>/tests.md`。
- 如果改动可能影响旧功能，先补 characterization/regression test，再改实现。
- 如果修复 bug，必须新增或更新一个能复现该 bug 的 regression test，并记录到模块 `tests.md` 的历史 bug 回归库。
- 如果改动涉及 read model、dirty scope、worker、API response shape、权限、导出或跨页刷新，必须在对应模块 `tests.md` 中更新影响面和未测风险。
- 不允许用 skip、删除测试、放松断言或隐藏错误来通过验证。
