# 流水规则批量处理测试矩阵

状态：covered-close。页面列表、summary、分页、详情和写后回读已切到 PostgreSQL canonical query boundary；页面 API 不再返回 read-model status/version、refresh enqueue 或 operation-barrier targets，前端不再轮询 freshness。

## 2026-09-01 三栏流水表与选择控件回归

- `web/src/test/BankFlowRuleBatchPage.test.tsx` 保护固定三栏比例、右栏单一纵向滚动、对方户名/交易时间/金额/关联/摘要列职责、旧行内银行账户与分类标签删除、可见 checkbox control/indicator，以及单选 -> 半选 -> 全选 -> 顶部清空选择闭环。
- `web/src/test/BankFlowRuleBatchPolicy.test.ts` 保护关联展示只输出“已关联”和 OA/发票计数，不泄露内部 case id。
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` 在真实 Chromium 中校验列顺序、旧重复信息消失、逐行 checkbox 可见且 control 宽度至少 18px；既有普通批次矩阵继续覆盖所有可选批次类型。
- 适用第 5 类 frontend component/interaction 和第 7 类 existing regression；第 1–4 类不适用，因为业务规则、service/API、数据库、read model、cache 和 worker 均未改变；第 6 类复跑既有提交 -> 关联台 -> 撤回 E2E，不新增跨模块链路。

## 2026-08-31 银行身份标量与 canonical account key 回归

- `tests/test_bank_details_canonical_query.py` 保护 `defer_full_payload=True` 只延迟完整 JSON，仍从 canonical 银行行投影 `imported_bank_name` 与 `imported_bank_last4` 两个轻量标量。
- `tests/test_bank_flow_rule_batch_canonical_query_repository.py` 保护 live candidate 直接使用 canonical `candidate.account_key`，禁止恢复 `bank_name:last4` 身份拼接；同时验证银行名称、尾号和固定查询数。
- 同一 repository 回归验证已提交历史只修正 API 银行显示名称，不改写旧 `account_key`、成员、金额或数据库记录。
- 第 1、2、3、7 类适用；第 4 类仅做负向边界确认，因为没有新增 read model、cache 或 worker；第 5 类无需修改运行时代码，既有页面测试负责 DTO 直出展示；第 6 类复跑现有提交/撤回 E2E。

## 2026-08-10 “全部”范围完整性回归

- `tests/test_bank_flow_rule_batch_canonical_query_repository.py` 保护省略月份时不再拼接旧 `and false`，一次 canonical snapshot 读取完整 non-deleted 候选输入，查询数不随月份增长。
- `tests/test_bank_flow_rule_batch_application_service.py` 覆盖同一全部范围同时包含跨月 live candidate 与 active relation 支撑的 submitted 批次，summary、rows 和分页使用同一完整集合。
- `web/src/test/BankFlowRuleBatchApi.test.ts` 与 `web/src/test/BankFlowRuleBatchPage.test.tsx` 保护“全部”通过省略 `month` 表达，不新增 `month=all`、月份循环或第二套前端协议。
- 第 1、2、3、5、6、7 类适用；第 4 类仅做负向边界回归，因为页面保持 PostgreSQL canonical direct-read，不引入 read model、cache 或 worker。

## 2026-08-10 撤回后自然归并重提回归

- `tests/test_postgres_state_store.py` 保护 active relation 窄查询把 `row_ids` 与可选 `case_ids` 一起转发到 PostgreSQL repository。
- `tests/test_workbench_relation_command_repository_adapter.py` 使用真实 `adapter -> PostgresStateStore -> repository` 组合，防止包装层签名再次偏离 relation command I/O。
- `tests/test_no_oa_bank_batch_tag_selection_api.py` 覆盖同月、同账户、同标签的三个批次分别提交、全部撤回、自动形成一个候选并重新提交；断言旧批次保持 withdrawn，全部流水只属于新的单一 active relation。
- `web/src/test/BankFlowRuleBatchApi.test.ts` 删除无后端 route、无生产调用的旧 `/api/bank-flow-rule-batches/submit` client 合同；普通流水只使用 `submit-selection`，内部往来继续使用 `/{batch_id}/submit`。
- 第 1、2、3、6、7 类适用并覆盖；第 4 类不适用，因为本页保持 PostgreSQL canonical direct-read；第 5 类行为未改，复跑既有页面交互与 Browser E2E 回归。

## 2026-07-31 标签管理抽屉回归

- `web/src/test/BankFlowRuleBatchPage.test.tsx` 保护共享 `AppDrawer`、`min(960px, 92vw)`、busy dismiss、权限、dirty/form/table/save/nested dialog 行为，并阻止旧 backdrop/aside/header/close/footer shell 回归。
- `web/e2e/drawer-motion.spec.ts` 保护共享 HeroUI right drawer 的进入/退出中间帧、方向、reduced-motion、页面 CLS 严格阈值和关闭零新增业务请求；页面既有 Browser spec 继续保护规则到 canonical batch 的业务链路。
- 适用第 5 类 frontend interaction 与第 7 类 existing regression；本次展示壳迁移没有改变第 1–4 类合同，也没有新增第 6 类跨模块业务链。

## 七类测试适用性

| 类别 | 是否适用 | 当前覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | OA/发票只有双 false 合格；未知、停用、重复标签 fail fast；提交冻结 requirement/category metadata；auto-only 188500 元一收一支可识别为内部往来且金额只计单边；5 月 31 日/6 月 1 日配对只由最早成员月份拥有且重复查询 identity 稳定；重复选择、占用和版本冲突保持原领域错误。 |
| 2. Service-layer tests | 适用 | canonical query repository 在一个 `REPEATABLE READ / READ ONLY` snapshot 中读取月份窗口内全部流水、分类事实和正式历史，不按 manual/confirmation category 预筛；所有 bucket 都保留 candidate rows/active relation 输入，避免 submitted summary 有数而列表为空；selected-row submit 即使 import/category/settings 启动时快照过期，仍只使用 canonical 流水、分类、标签 requirement 与 active relation，且关联 metadata 来自同一 rule proof；selected-row guard 接受同一时刻的空格时间/ISO offset 序列化，但真实秒级漂移或规则漂移仍冲突；写事务锁定 app settings 规则行；single submit、selected-row submit、withdraw、reset 在 relation 已暂存后注入 batch/event 失败，均断言 relation/history/batch/events 零半写；本地原子替换失败保留旧快照。 |
| 3. API contract tests | 适用 | 权限、非法参数、空集、筛选、排序、分页、summary、详情、提交/撤回/reset、规则 CAS；live 详情与 `submit-selection` 均透传并校验 `scope_month`，列表 batch id 能从同月 canonical facts 重算出明细；明确断言响应不含 `read_model_*`、refresh 或 operation-barrier 字段。 |
| 4. Read model, cache, and background job tests | 适用 | 页面 SQL 禁止读取 persisted draft、`read_model.bank_flow_rule_batch_rows` 和 no-OA 表；规则 settings/job/outbox 原子写，settings-maintenance worker 只扫描变化 tag proof、先全量预验证、通过正式 command 更新 canonical relation/matching，并仅对真实共享消费者 enqueue 精确 `workbench_relation` 月份；不得恢复 page `workbench` event。语义 no-op、结果 no-op 和幂等重放零额外写。 |
| 5. Frontend component and interaction tests | 适用 | loading/empty/error、筛选、分页、详情、规则抽屉、权限、提交/撤回/reset；ISO offset 时间统一显示为 `YYYY-MM-DD HH:mm:ss`；自动选中 live batch 时详情请求携带列表项月份；每次成功写命令只触发一次当前列表 GET；candidate conflict 清空旧选择、只刷新一次且不自动重提。 |
| 6. End-to-end business-flow integration tests | 适用 | 规则保存 -> settings/job/outbox 原子提交 -> settings-maintenance -> relation/history -> exact read-model refresh -> 关联台分区；批次选择 -> relation command -> canonical batch/event 保存 -> 当前页 GET -> 关联台 active relation 展示。 |
| 7. Existing feature regression tests | 适用 | 188500 元一收一支内部往来、no-OA legacy API/worker、Workbench 正式关系、bank-details 标签、成本/外部往来款、权限与审计不受迁移影响。 |

## 主要测试入口

- `tests/test_bank_flow_rule_batch_canonical_query_repository.py`
- `tests/test_bank_flow_rule_batch_application_service.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_bank_relation_requirement_recalculation.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/test_bank_flow_rule_batch_backend_boundary.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`
- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_relation_repository.py`
- `web/src/test/BankFlowRuleBatchApi.test.ts`
- `web/src/test/BankFlowRuleBatchPage.test.tsx`
- `web/src/test/BankFlowRuleBatchPolicy.test.ts`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/e2e/bank-flow-rule-batches-flow.spec.ts`

## 必测失败路径

- 无读取权限；规则保存无写权限。
- 非法月份、bucket、status、页码或 page size。
- 规则 CAS 冲突、未知/停用/重复 tag code。
- 规则变化任务缺 case、精确月份、tag proof 或当前 tag rule 时整批零 relation write；重复 job 不新增 history/refresh；未变化关系不写。
- 空选择、重复 row、跨月、跨账户、混合标签、active relation 已占用、规则版本过期。
- Relation command、batch 或 event writer 失败时不得留下半关系或半批次；single submit、selected-row submit、withdraw、reset 四类 mutation 都必须验证 relation/history/batch/events 一起 rollback。
- 5 月 31 日与 6 月 1 日的 ±2 天跨月内部转账只由最早成员月份返回一个稳定 candidate；相邻月份不得重复返回。
- 缺少 `scope_month`、规则漂移、成员漂移或 active relation 新占用必须返回 candidate conflict；遗留 persisted draft 不得被恢复提交。
- selected-row guard 必须接受 `2026-08-01 15:24:03` 与 `2026-08-01T15:24:03+08:00` 的等价时刻，并继续拒绝真实秒级时间漂移；前端冲突恢复只允许一次 GET、零自动重提。
- 后端 5xx 只显示一个错误弹窗并携带 `requestId`，不得同时出现底部重复错误提示。
- 可逆生产 scenario 必须是 `test_owned`，严格执行 submit -> withdraw -> resubmit，且声明 withdraw recovery；缺任一 checkpoint、跨 checkpoint 换流水或缺少受影响/隔离 consumer 必须拒绝加载。
- 列表生成的 live candidate 必须能用相同 `scope_month` 读取详情；submitted bucket 的 summary、列表 batch count 和 row count 必须来自同一完整 canonical 集合。
- Audit 必须调用共享 builder；故意过滤 188500 候选时 expected-set gate 必须失败。
- 空列表必须来自已完成的 canonical snapshot，不能由 missing/stale 投影伪造。
- submitted/withdrawn 历史使用冻结标签和 requirement metadata；当前标签改名或归档不得改写历史。
- canonical relation 查询只接受 `app.workbench_pair_relations.status='active'`，不得读取 Workbench page projection。
- 页面和 feature 源码不得重新出现 freshness polling、202 reconcile 或 no-OA fallback。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m pytest -q \
  tests/test_bank_flow_rule_batch_canonical_query_repository.py \
  tests/test_bank_flow_rule_batch_application_service.py \
  tests/test_bank_flow_rule_batch_routes.py
npm --prefix web test -- --run \
  src/test/BankFlowRuleBatchApi.test.ts \
  src/test/BankFlowRuleBatchPage.test.tsx
bash scripts/verify.sh lint
npm --prefix web run build
git diff --check
```
