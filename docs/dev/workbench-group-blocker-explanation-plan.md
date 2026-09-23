# 关联组未配对原因解释闭环实施计划

日期：2026-09-23。状态：已实施、已部署，生产功能与性能验收完成。不使用 GSD。

## 1. 已确认事实与目标

生产只读分析定位关系 `CASE-BATCH-txn_imported_1393`：5 张 OA、1 条银行流水、14 张正式发票。搜索值 470.40 是其中一张 OA 的金额，不是整组总额。

| 事实 | 金额 |
| --- | ---: |
| OA 合计 | 1273.06 |
| 银行流水 | 1273.06 |
| 正式发票 | 1139.63 |
| 胡瑢五份补充凭证 | 140.00 |
| 发票与凭证合计 | 1279.63 |
| 整组票据超额 | 6.57 |

五份凭证54、8、25、23、30元已生效。唯一阻塞为 `anomaly_review_required`，当前审阅为 pending；差异在莫永洪 `oa-exp-2008:item:1:0dfe75f5b6b2`：报销182.44，发票28.25+126.16+14.02+20.58=189.01。未发现凭证计额失效。

目标：让用户看见整组阻塞原因、知道凭证已计入、定位差异子项，并通过现有异常流程完成处理和回读。没有接受或消除6.57差异前，该组仍未配对是正确验收结果。

不改变业务金额、成员归属、配对规则或真实审阅决定，不把凭证创建成正式发票，不借本任务优化无关后端查询。

## 2. 边界与 I/O

实施前复读 [关联台边界](../modules/reconciliation-workbench/boundary-io.md)、[正式关系边界](../modules/workbench-relations/boundary-io.md) 和 [业务规格](../product-specs/reconciliation-and-workbench.md)。

| owner | 输入 | 输出/责任 |
| --- | --- | --- |
| 后端金额、分区、审阅服务 | canonical facts、凭证、当前审阅事实 | 继续输出权威金额、异常、分区；本次无计划中的生产代码改动 |
| Workbench API mapper | 现有 amount_check、异常、expense_item_differences、group rows | 沿用现有DTO；不新增response字段 |
| RelationGroupGrid | 当前组DTO、权限 | 组级提示、精确子项上下文；不重算是否配对 |
| WorkbenchAnomalyIndicator | 既有异常、明确的当前组展示上下文 | 解释金额及差异；无网络、数据库或业务写入 |
| WorkbenchExceptionDrawer | 同一异常合同及已有详情 | 共用解释内容和原审阅入口 |
| WorkbenchSupportingDocumentFiles | 当前子项凭证、金额、hasInvoice | 标明本项差额；保留混合发票与凭证的现有正确行为 |

直接模块为 reconciliation-workbench，验证下游为 workbench-relations。其他页面只做必要冒烟验证，不修改其DTO、财务事实或公共样式。无新表、迁移、API、worker、缓存、全局状态层。

## 3. 执行步骤与交付物

### A. 建立精确回归，固定语义

在现有测试fixture中构造与本例同形的多OA批量关系，使用合成姓名/ID和金额布局，不依赖生产文件/网络。验证140元凭证有效，另一个182.44元子项有189.01元票据，只有6.57元金额异常阻塞。

补充全额一致对照：所有金额一致且原有其他条件满足时，凭证可以满足对应材料要求并进入paired。不能只测试保持unpaired的场景。

### B. 改进原组级入口

修改 `web/src/components/workbench/RelationGroupGrid.tsx`、`WorkbenchAnomalyIndicator.tsx` 和 Workbench 专属样式。

- 原组级入口增加简短文本，例如“本组票据凭证多6.57元”；点击仍打开原Popover。
- 长组滚动到凭证区域时仍能发现原因。优先现有布局与CSS组内定位；提示不能跨组停留、遮挡文件/金额/操作或改变三栏对齐。不新增滚动监听、DOM测量循环或浮层管理器。
- 多异常显示数量，详情列出全部已返回异常，不只取第一项；行级异常保持精确位置，不在每个正常子项复制整组提示。
- 依据现有完成/审阅状态区分“待处理异常”与“已接受异常”，不能把已配对组的已接受差额仍称为阻塞。
- summary/full、分段/非分段、折叠/展开均验证；缺失详情时不能预取所有关系。

### C. 精确定位和解释金额

- 使用既有 `expenseItemDifferences.expenseItemIds` 在当前组OA子项索引中精确定位申请人、费用类型和费用内容，替换“明细1”作为唯一说明的旧输出。
- 多子项共享核对单元展示共同范围，不按第一项或同金额猜归属。
- 未加载详情走现有展开请求；若返回数据仍不能证明具体归属，则明确显示组级差异及无法定位状态，不虚构名称。
- 金额只读取权威字段：OA、银行、正式发票、补充凭证、evidenceTotal、差额。不在前端用展示行重新汇总、截断或分摊金额。
- 当前字段缺失时显示未提供/待核对，不能当作0；金额0与缺失必须区别处理。
- 主表Popover和统一异常抽屉复用同一解释逻辑，不复制两套模板和金额算法。

### D. 明确本项差额

修改 `WorkbenchSupportingDocumentFiles.tsx`：仅凭证分支改为“本项差额（OA − 凭证）”。现有 `hasInvoice` 分支已显示“与同项发票合并核对”，保留，不另写混合金额计算。

不在每份文件旁重复计额，多份凭证仍共享一份金额；未知金额、0金额、删除最后一份凭证、invoice_basis变化后的待确认语义保持。

### E. 验证现有处理闭环

复用原统一异常抽屉和 `accept_paired`/`keep_unpaired`，不新增主表审阅按钮或自动接受流程。

隔离环境验证：保存凭证 → 服务端回读 → 解释剩余差异 → 打开原异常抽屉 → 留在未配对/明确接受异常 → 成功回读 → 主表分区、异常列表和计数一致。接受后保留真实差额与审阅信息；撤回后按原规则回到未配对。

覆盖写失败、异常指纹变化、无权限、进行中OA等其他阻塞、重复点击，以及用户交互期间后台回读。失败不能前端先移动关系，不增加并行reload链。

`ReconciliationWorkbenchPage.tsx`和后端审阅服务为回归范围，默认不改。若发现实际缺陷，记录复现证据后只修必要调用点；若需要改变API/规则/数据模型，则属于范围扩大，须另行说明，不能静默追加。

## 4. 旧逻辑替换与删除

| 旧行为 | 替换/保留决定 |
| --- | --- |
| 组级原因只通过孤立小图标表达 | 替换原组级入口，不另加平行异常系统 |
| 差异子项只有“明细1/2” | 精确子项上下文替换；不猜归属 |
| 仅凭证差额没有本项范围提示 | 原文案内改为本项差额 |
| 调整后无调用的JSX/参数/定位样式 | 扫描全部调用点后删除，不遗留兼容分支 |
| 行级图标、混合计额、鉴权/审计/CAS | 属于有效行为，保留；不是待删旧代码 |

删除前检查主表、异常抽屉、行级/子项级提示及测试。共享符号删除要做全仓引用扫描。禁止为“必须删除旧代码”扩大到正确的后端算法。

## 5. 性能与验证矩阵

新展示首屏、滚动、打开已有原因不增加HTTP/SQL/OCR/worker；只有原有详情展开允许原请求。当前组建立一次子项索引，避免逐异常反复扫描。采用纯组件/现有模式，不预设全局缓存或新性能框架。

用相同长组fixture、相同浏览器和操作比较修改前后请求数量、渲染/滚动耗时及布局。报告样本数、负载与结果，不把已存在的后端慢查询宣称为已解决，不新增性能审批门禁。

| 七类测试 | 执行责任 |
| --- | --- |
| 业务核心 | test_workbench_amount_check_service、test_workbench_relation_grouping：本例、全额一致、混合/共享、多个异常、审阅与审批边界 |
| Service | test_workbench_anomaly_review_service及现有凭证保存测试：成功、失败、冲突、权限和幂等；不为未改生产代码机械复制测试 |
| API合同 | WorkbenchApi.test.ts现有映射回归；不新增response字段，保护金额空值和子项ID |
| cache/worker | 本次不涉及缓存/worker改动，无需新增其实现测试；已退役read model重建不适用；写后回读由交互/E2E覆盖 |
| 前端 | WorkbenchAnomalyIndicator、RelationGroupGrid、WorkbenchExceptionDrawer、WorkbenchInvoiceEntryDrawer：精确定位、多异常、长组、键盘、窄屏/横向滚动、只读和错误态 |
| 全流程 | 现有真实PostgreSQL套件保护分区/审阅，再在Playwright合成fixture保护用户完整路径；生产只读不替代隔离写入测试 |
| 既有回归 | 凭证预览/管理、发票录入、审批阻塞、ETC折叠、共享发票、搜索分页、异常审阅、其他页面必要冒烟 |

候选执行命令（实施时记录实际结果）：

```bash
PYTHONPATH=backend/src:tests python3 -m unittest \
  test_workbench_amount_check_service test_workbench_relation_grouping \
  test_workbench_anomaly_review_service -v

# PostgreSQL集成单独运行，显式隔离测试DSN，禁止继承生产连接。
PYTHONPATH=backend/src:tests python3 -m unittest test_workbench_query_postgres_integration -v

cd web
npx vitest run src/test/WorkbenchAnomalyIndicator.test.tsx \
  src/test/RelationGroupGrid.test.tsx src/test/WorkbenchExceptionDrawer.test.tsx \
  src/test/WorkbenchInvoiceEntryDrawer.test.tsx src/test/WorkbenchApi.test.ts
npx playwright test e2e/workbench-supporting-documents-flow.spec.ts \
  e2e/workbench-stale-error-flow.spec.ts --project=chromium
```

定向通过后按发布要求运行 `bash scripts/verify.sh frontend`、`docs`、`git diff --check`。若修改后端生产代码，则加入lint和相应后端发布检查。相关测试失败不跳过、不放宽断言；没有新变化或未解决问题时不重复全量运行。

## 6. 文档、发布验收与清理

- docs impact：实施后更新 reconciliation-workbench 的boundary-io/tests/implementation-notes，明确可见提示取代组级仅图标表达。没有改变后端职责和HTTP合同，不复制更新无关模块文档。
- 后续实施发布沿用正式 `scripts/deploy-oa.sh`，不增加发布入口或门禁，不在服务器手改文件。本轮已获授权提交、推送 remote main 并正式部署。
- 生产只读复核本例的金额、成员、来源、凭证、审阅状态，浏览器确认原因可见及定位准确；保持真实pending，不擅自接受6.57元异常，不用生产财务写操作演示流程。
- 无生产数据库备份或数据迁移需求。任务临时文件/独立测试库完成后精确清理；禁止删除主数据库、原始业务附件或既有备份。
- 失败回退是本次前端代码回退，不需要恢复业务数据。保留已有发布审计证据。

## 7. 二次复审与完成标准

| 要求 | 结论 |
| --- | --- |
| 模块化/清晰I/O | 通过：后端权威判断，前端只解释，原服务负责写入 |
| 简单/完整闭环 | 通过：原组件、Popover和异常抽屉复用，包含成功/失败/回读 |
| 高性能 | 设计满足零新增后端I/O；前端性能待同条件实测，不承诺全部页面变快 |
| 旧代码清理 | 明确替换清单及调用方扫描，不删有效规则 |
| 其他页面不受影响 | 限定组件/样式，保护共享入口；不能承诺未经测试的绝对零bug |
| 不无条件认同 | 局部金额一致不能豁免整组差异；凭证参与核对不等于创建正式发票；完整闭环不等于擅自接受异常 |
| 备份清理 | 无生产备份；任务临时资源精确清理，主库不动 |
| 无兜底 | 不猜归属、不补零、不自动接受、不前端伪造分区 |
| 不用GSD/不过度门禁 | 直接实施、针对性测试、沿用发布检查 |

最终完成需要同时具备：可见原因、精确/诚实的明细解释、正确局部文案、原审阅闭环的测试证据、旧分支删除、性能实测、模块文档和临时资源清理。只改文案、只有happy path测试、或者直接把真实关系改成paired，都不能算完成。


## 8. 实施记录（2026-09-23）

- 实际修改限于四个既有 Workbench 组件及对应 Workbench 专用样式；未修改后端业务、DTO、数据库、配对/审阅规则。分段/普通布局共用一次组级渲染，替换两处旧图标 JSX 和绝对定位。
- 真实浏览器发现并修正 Escape 关闭后焦点恢复重开的问题；继续使用既有四态交互，关闭进入 dismissed，离开 trigger 后恢复，无新事件监听链。
- 新增金额回归验证五张 OA、140元有效凭证、另一182.44元子项票据189.01元；修正超额后金额全部一致。前端解释覆盖多异常/共享子项/缺归属、0与未知、已接受；浏览器覆盖相同五张OA/14张发票布局、桌面与390px窄屏、凭证保存删除和整组接受撤回。
- 已完成：核心金额/分组/审阅82项、真实独立PostgreSQL查询43项、全量前端110文件1483项及生产构建；最终四组件定向87项。浏览器9项凭证/异常链路与25项权限/大数据/过期状态/跨页面链路均最终通过（大数据筛选滚动有一次瞬态失败，原测试不改断言复跑通过）。
- 部署前同一真实关联组5次查询耗时823–1020ms，中位数924ms；5次打开详情9–89ms；20帧滚动无额外请求，无浏览器异常、无写请求。样本小且测试期间有并发本地检查，不能据此推导容量SLO或宣称后端查询优化。
- 无生产数据库备份、迁移或财务写入。隔离测试资源与临时测量文件结束后精确清理。发布及部署后只读验收执行正式发布工具，最终版本与生产性能结果记录于发布证据和本任务交付报告。

- 发布前正式检查：`bash scripts/verify.sh lint`、`frontend`、`docs`、`git diff --check`通过；`FIN_OPS_TEST_DATABASE_URL=<独立测试库> bash scripts/verify.sh backend`运行4528项，原55项现金专用DSN测试跳过；随后用另一个独立现金测试库设置`FIN_OPS_CASH_TEST_DATABASE_URL`运行`test_cash_core test_cash_http_integration test_cash_runtime`，62项全部通过，覆盖上述环境限定测试。两次隔离库均与生产主库无关。


### 生产发布与验收完成

- 功能代码提交：`ff6992d3f3e48b9c67ecdd9e422114a964db7b9e`，已推送 remote main。正式 release：`main-ff6992d3-20260923131714`，frontend profile 的 pre/t0 均 PASS，public index/asset、发布目录、active release、API ready及四个worker检查通过，未回滚。该profile不要求T+30队列检查，不能将未执行项记作通过。
- 首次直接调用发布入口完成候选上传和校验，因没有通过本地凭据包装器而在激活前停止；随后使用 `scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh --activate-existing --release-name main-ff6992d3-20260923131714` 激活同一已验证候选，无重复上传。
- 生产浏览器核实：本组可见“OA 流水一致，票多 · 差额6.57元”；Popover列出正式发票1139.63、补充凭证140.00、合计1279.63，准确定位莫永洪交通费182.44与票据189.01；五份凭证各自“本项差额0.00”。新旧DTO的OA/流水/发票成员集合、amount_check、completion、workbench_anomaly逐项一致，仍为`anomaly_review_required`，没有擅自接受真实差额。
- 同一查询各5次：部署前823–1020ms/中位924ms，部署后852–1114ms/中位919ms。部署后5次说明打开30–90ms/中位40ms；20次滚动帧间隔中位16.7ms、滚动新增请求0；浏览器JS异常0、财务写请求0。小样本且本地并发测试负载不同，只证明本次交互可用与没有新增后端I/O，不能宣称查询提速或整体容量SLO已达标。
- 生产银行明细、待找发票页面打开且数据GET返回200；异常接受/撤回、写失败、权限、过期状态依赖隔离测试证据，不在生产做财务写入演示。
- 根证据保留于服务器 `/opt/fin-ops/runtime-smoke/release-gates/main-ff6992d3-20260923131714/`。隔离PostgreSQL实例已停止并精确删除；任务发布tar包、临时截图/数据/日志在交付前删除，保留一张用户可读的生产界面截图。没有创建或删除生产数据库备份，未删除主数据库。
