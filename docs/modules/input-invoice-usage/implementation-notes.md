# 进项发票使用情况 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 默认 all scope 查询不得因为月份间嵌套 `workbench_relation_source_versions` 不同而清空基础 `source_versions`；API freshness 只要求服务端期望的基础 source version 字段匹配。
- `以发票反提 OA` 第一版前端只暴露 `创建 OA 草稿`，后端保留 batch 作为内部状态对象；创建草稿使用目标 OA 申请人的已配置凭据/token，OA 提交由用户在 OA 系统手动完成。
- 设置页新增 `OA 申请人凭据管理`，第一版只展示目标 OA 申请人、OA 登录账号和 `已配置`/`未配置` 状态；密码保存/更新成功后不回显，且不能进入普通 app settings payload。
- Phase 1 已落地后端凭据管理：`app.oa_applicant_credentials.encrypted_password` 使用 PostgreSQL `pgcrypto` 加密落库；生产保存/读取密钥来自 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。
- Phase 2 已落地后端一步创建草稿：`POST /api/input-invoice-usage/oa-reverse/oa-draft` 校验 preview hash 后，使用目标 OA 申请人凭据登录 OA 并创建 `isDraft=true` 暂存草稿；当前操作人的 request token 不参与目标申请人草稿创建。
- `已提交 OA` 由用户手动确认后进入本地 `submitted_confirmed` 历史；`未提交 OA` 只清理 FinOps 本地草稿字段并回到可重新创建状态，不调用 OA 删除暂存草稿。
- 目标 OA 申请人登录需要 `FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`、可选 `FIN_OPS_OA_LOGIN_PATH` 和 OpenSSL runtime；密码登录前必须用 OA 公钥 RSA 加密。
- OA reverse evidence detected 后的 OA/发票 relation 写入必须通过 `WorkbenchRelationCommandService.confirm_relation(...)`，relation mode 为 `input_invoice_oa_reverse`；relation read model 不 fresh 或 command service 缺失时 fail fast，不先推进本地 batch。
- 关联台未配对区 open/proposed 候选必须通过 `WorkbenchRelationReadFacade` 进入进项发票使用情况页面展示；页面不能直接读取关联台候选表。candidate 只展示关系证据，不参与支付状态或 confirmed relation 判断。
- `+N` 详情展开优先读取 `read_model.input_invoice_usage_rows` 单行 payload；SQL read model stale/missing 时返回 refreshing 并入队刷新，不在详情接口中触发全量 live rebuild。
- `以发票反提 OA` 的草稿提交确认弹窗可以由用户取消；取消、父页面重渲染和 preview reload 都不能清空当前草稿 batch，状态为 `oa_draft_created` 的 batch 必须出现在 `暂存` 页签。暂存列表不展示 OA 草稿链接，只展示两项处理动作。
- OA reverse preview 中已有 active/linked OA 关系的发票仍然不是可创建候选，但需要作为 rejected display row 返回给前端，展示 `已关联oa` chip、禁用勾选；关联台未配对区 open/proposed OA candidate 也不是可创建候选，展示 `候选oa` chip、禁用勾选。drawer 支持 `全部/已经关联oa/候选oa/未关联oa` 表头筛选。
- 2026-06-11 测试闭环审计确认：本模块 P0/P1 已有测试覆盖 read model all scope、OA 反提、凭据加密、目标申请人 token provider、未提交回滚、已提交历史、设置页 UI 和进项页面 drawer；本轮不新增重复测试，主要补齐测试矩阵并同步长期 API 契约。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-18 - OA reverse 新增暂存 bucket

- 目标：修复创建 OA 草稿后用户关闭确认弹窗时，本地批次缺少可恢复入口的问题。
- 影响范围：`InputInvoiceUsageOaReverseService`、OA reverse API、`OaReverseWorkspaceDrawer`、前端 API mapper、模块/API 文档和测试矩阵。
- 关键决策：不新增数据库状态；复用已有 `oa_draft_created` 作为事实状态，前端展示为 `暂存`。暂存列表只展示批次摘要和两个处理选项，不展示 OA 草稿链接。关闭确认弹窗只关闭 UI 并切到暂存，不调用 manual status，也不清理 batch。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 service/API/frontend 暂存恢复测试，并同步既有确认按钮文案断言。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA 外部草稿仍需 staging 联调；本功能不改变外部 OA 系统草稿生命周期。

## 2026-06-18 - Browser e2e 覆盖 relation fan-out 与 OA 三态保护

- 目标：为 `进项发票使用情况` 建立 Spec-first E2E 基线，并补真实 Chromium smoke，证明 Workbench relation candidate/linked 语义在进项页和 OA reverse drawer 中不回归。
- 影响范围：Playwright deterministic mock、`web/e2e/input-invoice-relation-fanout.spec.ts`、`npm run e2e:smoke`、本模块 `e2e-spec.md` / `e2e-coverage.md` / `tests.md` / `state-machine.md` 和 `workbench-relations` 覆盖矩阵。
- 关键决策：不新增页面私有匹配规则；mock 表达真实 API contract。candidate OA/流水关系只作为证据显示，支付状态保持 `待处理`；Workbench confirm 后重新进入页面读取 linked rows，显示 `已支付`。OA reverse preview 中 candidate/linked 发票均不可勾选，且不触发草稿 API。
- 文档影响：新增本模块 Spec-first E2E 文档，更新全局 inventory、nightly、testing 和 closure state。
- 测试覆盖：新增 `web/e2e/input-invoice-relation-fanout.spec.ts`，覆盖七类中的前端交互、端到端业务流和既有功能回归。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA、真实 worker drain、真实下载、tax/cost/search 更下游 fan-out 仍需后续轮次或 staging。

## 2026-06-17 - 主列表显示 OA 附件来源 relation 证据

- 目标：修复 `进项发票使用情况` 主列表中正式发票已由 OA 附件来源提升/合并，但 OA 列仍为空的问题；例如 `安徽德易智莱科技有限公司 / 913401003366798893` 在关联事实中有 OA，却因 row id 不一致未展示。
- 影响范围：`InputInvoiceUsageQueryService` rows 构建、relation preload、发票 relation summary、模块 README/状态机/测试矩阵。
- 关键决策：不新增页面私有匹配，不直接从前端或 pending invoice UI 推断 OA；列表仍通过 `WorkbenchRelationReadFacade` 读取统一 relation distribution，只是在查询 key 中加入 `source_links[].source_workbench_row_id`，覆盖正式发票 id 与 OA 附件 row id 不同的生产形态。candidate 证据只展示，不参与支付状态。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md` 和 `tests.md`；API shape 未变化，不更新 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 `InputInvoiceUsageQueryServiceTests.test_oa_attachment_source_relation_displays_for_promoted_formal_invoice`，覆盖 OA 附件来源 row id 的 OA candidate 展示和支付状态不变。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产行仍需部署后通过 read model refresh/只读 smoke 确认；本地测试覆盖 service 和 SQL read model 构建路径，不连接真实 OA/Postgres worker drain。

## 2026-06-17 - OA reverse 候选 OA 三态 chip 修复

- 目标：修复截图中发票在关联台未配对区已经有 OA candidate，但在 `以发票反提 OA` drawer 中显示 `未关联oa` 的问题。
- 影响范围：`InputInvoiceUsageOaReverseService.preview` 的 rejected invoice contract、`OaReverseWorkspaceDrawer` 的 chip/filter/disabled 状态、前端 API mapper/types、样式、API contract 测试和模块文档。
- 关键决策：截图 1 的“有 OA”是关联台未配对区 candidate，不是 active/linked OA 关系；旧实现只有 `linked/unlinked` 二态，导致 candidate 默认落到 `unlinked`。修复后 OA reverse 使用 `linked/candidate/unlinked` 三态：`linked` 显示 `已关联oa`，`candidate` 显示 `候选oa`，两者都不可勾选且不进入创建 OA 草稿 payload。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 service/API candidate OA preview 回归；更新前端 drawer 测试覆盖 `候选oa` chip、禁用勾选和 `全部/已经关联oa/候选oa/未关联oa` 筛选。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产截图行仍需部署后用实际 read model 数据只读 smoke；本地测试已覆盖 relation facade candidate payload 到 preview/API/UI mapper 的路径。

## 2026-06-17 - OA reverse 确认弹窗持久化与 OA 关联状态筛选

- 目标：修复 `以发票反提 OA` 创建草稿后提交确认弹窗自动消失的问题，并让已有 OA 关联的发票在反提清单中可见、不可选、可筛选。
- 影响范围：`OaReverseWorkspaceDrawer`、OA reverse preview rejected invoice contract、前端 API mapper/types、样式、service preview display rows、模块/API 文档和测试矩阵。
- 关键决策：弹窗消失的真实原因是父页面异步刷新导致重渲染，drawer 每次收到新的内联 `selectedInvoiceIds={[]}` 数组都会重建 preview request，preview reload 成功后执行 `setBatch(null)`，从而卸载确认弹窗。修复时稳定 selected invoice ids，并在确认弹窗打开后禁止 preview reload 清空当前 batch。
- 文档影响：更新本实施记录、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增/更新 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` 覆盖确认弹窗跨重渲染/preview reload 保持、linked OA disabled row 和筛选菜单；更新 `tests/test_input_invoice_usage_oa_reverse_service.py` 覆盖 active OA rejected row 保留展示字段。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA 草稿页面人工提交仍需 staging/发布前 smoke；本修复覆盖 FinOps 内部 drawer 状态、preview contract 和 API mapper。

## 2026-06-17 - Browser e2e 覆盖 OA reverse 子集草稿闭环

- 目标：给进项发票使用情况补真实 Chromium 流，覆盖 rows 首屏、`以发票反提 OA` drawer、候选子集重新 preview、创建 OA 草稿、确认 `已提交 OA` 和 submitted history 展示。
- 影响范围：deterministic Playwright API mock、`web/e2e/input-invoice-usage-flow.spec.ts`、`npm run e2e:smoke` 和测试闭环文档；业务实现不变。
- 关键决策：mock 保持后端真实 contract 的 preview/draft/manual-status/history shape；e2e 明确断言子集 preview request 只携带当前勾选发票，并断言已提交历史不展示内部 batch id。
- 文档影响：更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/input-invoice-usage-flow.spec.ts`，并加入 `web/package.json` 的 `e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts`；完整最终命令见本轮最终说明。
- 未测风险：真实 OA 登录、公钥 RSA、草稿页面打开、人工提交、真实 Postgres/RabbitMQ/Redis worker drain 仍需 staging/发布前 smoke。

## 2026-06-17 - OA reverse 子集候选 preview hash 修复

- 目标：修复 `以发票反提 OA` drawer 中只勾选部分候选后点击 `创建 OA 草稿` 报 `OA reverse preview is stale. Refresh preview before creating an OA draft.` 的问题。
- 影响范围：`OaReverseWorkspaceDrawer` 创建草稿交互、OA reverse 前端回归测试和模块测试矩阵；后端 preview hash fail-fast 契约保持不变。
- 关键决策：不放松后端 stale 校验；前端创建草稿前按当前勾选发票和目标申请人重新请求 preview，使用刷新后的 `previewId`/`previewHash` 与有效候选发票创建草稿。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug 回归库；状态机/API contract 未变化。
- 测试覆盖：更新 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`，先验证旧行为会继续使用全量候选 hash，再改为断言子集创建前刷新 preview 并提交刷新后的 hash。
- 验证命令：`npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx`；完整最终命令见本轮最终说明。
- 未测风险：真实 OA 草稿创建仍依赖 staging/生产 OA 登录和草稿接口 smoke；本修复只覆盖 FinOps 前端 preview/hash 提交流程。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止进项发票使用情况首屏请求把超大 page size 透传为全量读取。
- 影响范围：`InputInvoiceUsageQueryService.list_rows` 的分页 contract、`InputInvoiceUsagePage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `InputInvoiceUsageQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/InputInvoiceUsagePage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service.InputInvoiceUsageQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和导出下载性能仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-12 - 统一 relation candidate 展示与 `+N` 详情闭环

- 目标：让进项发票使用情况页面和关联台使用同一 relation 读事实源，展示 linked 与未配对 candidate 关系，并修复点击 `+N` 详情后长期 loading。
- 影响范围：`workbench_relation` SQL projection、distribution mapper、`InputInvoiceUsageQueryService`、input usage relation detail API、SQL read model repository、模块/API/架构文档。
- 关键决策：open/proposed unmatched decision 通过 `WorkbenchRelationReadFacade` 分发为 `relationStatus=candidate`；candidate 不写入 confirmed relation，不参与支付状态；`relationStatus=linked` 才能证明已支付/已确认。详情接口新增 read-model detail service，优先按 row id 读取单行 payload。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`docs/dev/api-contracts.md` 和 `docs/architecture/persistence-and-read-models.md`。
- 测试覆盖：新增/更新 projection、facade mapper、input usage service、API 和 repository runtime tests；前端沿用 `InputInvoiceUsagePage` 的多关系 `+N` 覆盖。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产数据量下的 worker drain 与浏览器手工 smoke 仍需 staging/发布前验证。

## 2026-06-12 - OA reverse relation command boundary Phase 7C

- 目标：把 OA reverse 检测到 OA evidence 后建立 OA/发票关系的写入口迁入统一 workbench relation command boundary，避免直接写 pair relation 事实源。
- 影响范围：`WorkbenchInputInvoiceUsageOaReverseRelationWriter`、Application OA reverse service wiring、OA reverse status refresh API error mapping、workbench relation/input invoice usage 测试矩阵。
- 关键决策：writer 写 `input_invoice_oa_reverse`，并把 `case_id`、row identity、actor、month scope、metadata、evidence、idempotency key 和 history operation 交给 `WorkbenchRelationCommandService.confirm_relation(...)`；缺 command service 或 read model non-fresh 时返回结构化错误，不保存本地 detected batch。
- 文档影响：更新本实施记录、`tests.md`，并同步 `docs/modules/workbench-relations/`。
- 测试覆盖：新增 service 测试覆盖 writer command delegation 和缺 command fail-fast；新增 API 测试覆盖 command stale/conflict 409 且无半写入；新增 runtime boundary guard 防止重新注入 pair service 或 direct pair mutation。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_oa_reverse_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q`。
- 未测风险：真实 OA evidence 来源仍使用本地 fake projection 测试；完整跨页面 read model smoke 和真实 worker drain 仍需后续闭环。
- 后续事项：继续收口 no-OA/turnover/batch accounting legacy repair/fallback，以及 relation command service 的生产级并发占用约束。

## 2026-06-11 - 测试闭环矩阵与 API 契约同步

- 目标：执行测试闭环 master goal 的 input-invoice-usage 模块轮次，审计进项发票使用页面/API/read model、OA 反提、目标申请人凭据、设置页 UI 和相关测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；同步 `docs/dev/api-contracts.md` 中反提 OA 当前一键创建、目标申请人 token、`submitted_confirmed` 历史和 `not_submitted` 本地回滚语义。
- 关键决策：现有 P0/P1 测试已经覆盖 all scope freshness、rows/filter/detail/export、OA reverse preview/one-step draft/manual status/submitted history、credential service/API/PG encryption、target token provider、Settings UI 和 InputInvoiceUsage drawer；本轮不新增重复代码测试。
- 文档影响：将 `tests.md` 迁入闭环标准结构，补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令和未测风险。
- 测试覆盖：沿用现有 input invoice usage、invoice usage collection、OA reverse、credential、settings 前后端测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_input_invoice_usage_api tests.test_read_model_freshness -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_postgres_migrations -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/WorkbenchSelection.test.tsx`。
- 未测风险：真实 OA 登录、公钥 RSA 加密、OA 草稿 URL 打开和人工提交仍需 staging/发布前联调；真实 Postgres/RabbitMQ/Redis 多 worker drain 仍由夜间或 staging smoke 覆盖。
- 后续事项：下一模块继续处理 `cost-statistics`。

## 2026-06-10 - 反提 OA 全链路回归与文档收口 Phase 5

- 目标：补齐跨模块 API 集成、未提交回滚重建测试、敏感信息检查和文档收口，确认 `以发票反提 OA` 从凭据维护到已提交历史的闭环。
- 影响范围：增强 `tests/test_input_invoice_usage_api.py`，新增管理员保存凭据后 full-access 用户创建 OA 草稿的 API 集成测试，以及 `未提交 OA` 后用新 idempotency key 重新创建草稿的 API 测试；更新测试矩阵和实现计划。
- 关键决策：API 层允许 `未提交 OA` 返回内部 `not_submitted` 状态，但业务可重建契约以 `canCreateDraft=true`、`oaDraftId=null`、`oaDraftUrl=null` 和再次创建成功为准；前端仍不展示该内部状态。
- 文档影响：更新本实施记录、测试矩阵和实现计划；状态机主规则保持不变，继续把 `未提交 OA` 视为不展示长期历史的本地回滚路径。
- 测试覆盖：新增 API 集成测试覆盖凭据 API -> target applicant login provider -> OA draft client -> 用户确认 -> 已提交历史；新增 API 回滚测试覆盖未提交后重新创建。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；完整目标回归命令见本次最终说明。
- 未测风险：真实 OA 登录接口、真实 RSA 公钥和真实 OA 草稿页面仍需生产发布前联调。
- 后续事项：发布前配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`、`FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`，并在目标申请人测试账号上做一次草稿创建联调。

## 2026-06-10 - 进项发票使用页反提 OA UI 闭环 Phase 4

- 目标：把 `以发票反提 OA` 前端主路径收敛为单一 `创建 OA 草稿` 操作，并提供 `待处理 | 已提交` 视图、OA 草稿提交确认弹窗和未提交本地回滚。
- 影响范围：更新 `OaReverseWorkspaceDrawer`、进项发票使用页 API 接线、input invoice usage API/types、页面测试 mock 和前端样式；不改变后端 batch 的内部状态对象语义。
- 关键决策：前端不再暴露 `创建本地批次`、`刷新 OA 状态`、撤销草稿绑定或人工检测 fallback；创建草稿成功后只显示 OA 草稿链接与 `已提交 OA`/`未提交 OA` 确认；`未提交 OA` 清空当前前端 batch 并回到可重新创建状态；已提交历史只展示申请人、时间、金额、张数和发票摘要，不展示内部 id 或英文状态。
- 文档影响：更新本实施记录、实现计划、状态机和测试矩阵。
- 测试覆盖：`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` 覆盖 API mapper、一键创建草稿、确认弹窗、未提交回滚、已提交历史和隐藏旧控件；`web/src/test/InputInvoiceUsagePage.test.tsx` 覆盖页面入口接线到一键草稿 API 和已提交 tab。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地前端测试使用 mock API；真实浏览器连接生产后端和 OA 草稿页面打开行为仍需联调验证。
- 后续事项：Phase 5 运行完整后端/前端回归、做 secret 泄漏检查并收口文档。

## 2026-06-10 - 设置页 OA 申请人凭据管理 UI Phase 3

- 目标：让管理员 `YNSYLP005` 可在设置页维护目标 OA 申请人的 OA 登录账号密码，支撑后续 `创建 OA 草稿` 使用目标申请人身份登录。
- 影响范围：新增 `SettingsOaApplicantCredentialsSection`；扩展设置页导航、页面状态、workbench API client/types 和前端 mock；不改变普通 settings payload。
- 关键决策：`OA申请人凭据` section 仅 admin 可见；全操作非 admin 不展示入口；保存/清空凭据走 `/api/workbench/settings/oa-applicant-credentials` 独立接口；密码只存在于表单输入中，保存成功后清空，不回显到列表，不进入 `saveWorkbenchSettings(...)`。
- 文档影响：更新本实施记录、实现计划、设置模块状态机和测试矩阵。
- 测试覆盖：`web/src/test/SettingsPage.test.tsx` 覆盖管理员维护凭据、非 admin 隐藏、保存密码走独立 endpoint、普通 settings save 不含密码；`web/src/test/WorkbenchSelection.test.tsx` 覆盖既有关联台设置入口回归。
- 验证命令：`cd web && npm test -- --run src/test/SettingsPage.test.tsx`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx`。
- 未测风险：尚未在真实浏览器连接生产后端验证凭据保存；完整 `待处理 | 已提交` drawer UI 和创建草稿确认流仍待 Phase 4。
- 后续事项：Phase 4 实现进项发票使用页面 `创建 OA 草稿`、确认弹窗和已提交历史。

## 2026-06-10 - 目标 OA 申请人创建草稿后端闭环 Phase 2

- 目标：把 `创建 OA 草稿` 后端路径从“当前操作人 token”切到“目标 OA 申请人凭据/token”，并提供前端后续一键创建和历史展示所需 API。
- 影响范围：新增 `TargetOaApplicantTokenProvider`、`OaLoginClient` 和 OpenSSL RSA 密码加密；扩展 `InputInvoiceUsageOaReverseService` 一步创建草稿、手动确认语义和已提交历史；扩展 PG batch repository 的 status 查询；新增 `/api/input-invoice-usage/oa-reverse/oa-draft` 和 `/submitted-history` API；旧 batch 草稿接口也改为按 batch 目标申请人取 token。
- 关键决策：preview hash 过期、候选失效或凭据缺失时不创建内部 batch；创建 OA draft 仍写内部 batch 作为状态对象但不暴露为用户入口；目标申请人登录失败、RSA 配置缺失或 OA 外部失败返回结构化错误且不包含密码/token；`submitted` 手动确认落为 `submitted_confirmed`，`not_submitted` 清理本地 `oaDraftId`/`oaDraftUrl`/OA row 字段后允许重新创建。
- 文档影响：更新本实施记录、状态机、测试矩阵、实现计划和 OA 部署环境变量说明。
- 测试覆盖：新增 token provider/OA login client 单测、一步创建 service/API 测试、PG repository status 查询测试；更新手动确认、未提交回滚和已提交历史 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`。
- 未测风险：本地测试使用 fake login client 和 fake OA draft client，未真实连通 OA 登录接口；生产发布前必须配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`，确认 runtime 可执行 `openssl`，并做一次目标申请人登录和 OA 暂存草稿联调。
- 后续事项：Phase 3 实现设置页凭据管理 UI；Phase 4 实现进项发票页面 `待处理 | 已提交` 和 `创建 OA 草稿` 用户闭环。

## 2026-06-10 - OA 申请人凭据管理后端闭环 Phase 1

- 目标：先完成设置页后端凭据管理能力，为后续 `创建 OA 草稿` 使用目标 OA 申请人登录态提供事实源。
- 影响范围：新增 `OaApplicantCredentialService`、内存/PG repository、`app.oa_applicant_credentials` 迁移、`/api/workbench/settings/oa-applicant-credentials` API；未改动当前 OA draft 创建路径。
- 关键决策：凭据管理 admin-only；`YNSYLP005` 默认 admin 可维护；全操作非 admin 不能维护；密码只写不读，API 只返回 `已配置`/`未配置`；普通 `/api/workbench/settings` 不包含密码或凭据 payload。
- 文档影响：更新本实施记录、测试矩阵、状态机，以及设置模块状态机/测试矩阵。
- 测试覆盖：新增 service、API、Postgres repository 和迁移契约测试，覆盖权限、非敏感响应、PG 加密 SQL、迁移 schema。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`。
- 未测风险：Phase 1 尚未接入 OA 登录/token provider，也未改前端设置页；生产环境必须配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY` 后才能在 PostgreSQL 模式保存/读取凭据。
- 后续事项：Phase 2 将使用该凭据事实源实现目标 OA 申请人 token provider，并替换当前从操作人请求 header 取 token 的创建草稿路径。

## 2026-06-10 - 以发票反提 OA 实现计划

- 目标：为 `以发票反提 OA` 闭环生成可由 Codex 分阶段执行的生产级实现计划。
- 影响范围：计划覆盖后端凭据管理、目标申请人 token provider、一键创建 OA 草稿、设置页凭据 UI、`待处理 | 已提交` 前端闭环、集成测试和文档收口。
- 关键决策：先落后端凭据管理，再落目标申请人 token provider 和一键草稿创建，随后实现设置页与进项发票页面 UI，最后做全链路回归；每个阶段都要求先测试、再实现、再维护文档。
- 文档影响：新增 `oa-reverse-implementation-plan.md`，并在 `README.md` 登记。
- 测试覆盖：计划阶段未改业务代码；计划要求实施阶段覆盖七类测试中的业务核心、service、API、前端交互、集成和既有回归。
- 验证命令：文档计划阶段未运行自动化测试；已通过读取计划文件和 `git diff` 检查内容。
- 未测风险：计划中的加密实现需要实施阶段根据 `backend/requirements.txt` 和运行环境确认是否可复用现有库；如需新增依赖必须先停下确认。
- 后续事项：按 `oa-reverse-implementation-plan.md` 的 Phase 1 prompt 开始实现。

## 2026-06-10 - 以发票反提 OA 闭环设计

- 目标：明确进项发票使用情况页面中 `以发票反提 OA` 的生产级闭环设计。
- 影响范围：设置页目标 OA 申请人凭据管理；输入发票使用页面 OA 反提 drawer；后端 OA reverse service、凭据 service/repository、target applicant token provider、OA draft client 集成；已提交历史展示。
- 关键决策：前端不暴露 `创建本地批次`；batch 仅作为内部状态对象；创建 OA 草稿使用目标 OA 申请人凭据/token；FinOps 只创建 `isDraft=true` 暂存草稿，不自动提交 OA；用户选择 `未提交 OA` 时只回滚本地状态，不删除 OA 暂存草稿。
- 文档影响：新增 `oa-reverse-design.md`，更新 `README.md`、`state-machine.md` 和 `tests.md`。
- 测试覆盖：当前为设计阶段；实施时必须按 `tests.md` 的七类测试矩阵补齐权限、凭据、服务、API、前端交互、集成和回归测试。
- 验证命令：文档设计阶段未运行自动化测试；实施后按具体代码变更运行后端 unittest、前端组件测试和构建。
- 未测风险：OA 外部系统登录、token 缓存和 form draft API 需要在实现阶段用 mock/contract 测试保护，并在生产发布前做联调验证。
- 后续事项：生成分阶段实现 prompt；每个大阶段完成后维护本模块文档和状态机文档。

## 2026-06-10 - all scope source_versions 聚合修复

- 目标：修复“进项发票使用情况”默认不传 `month` 时页面没有加载数据的问题。
- 真实原因：生产 read model 行数据和月 scope 均存在且 fresh，但 repository 在 all scope 聚合时要求所有月份的完整 `source_versions` 字典完全相等；不同月份的 `workbench_relation_source_versions` 嵌套时间戳不同，导致 all scope 返回 `{}`，API 随后以 `api_source_versions_stale` 返回 `202/refreshing` 和空 rows。
- 影响范围：`PostgresReadModelRepository._invoice_relation_scope_row` 的 all scope source_versions 聚合；输入发票使用页面 rows API；同 helper 也服务于 output invoice collection all scope。
- 关键决策：all scope 仍要求各月 cache status 为 fresh；版本聚合改为保留各月份共同一致的顶层 source version 字段，差异字段从 all scope source_versions 中剔除。
- 文档影响：更新 `state-machine.md` 的 read model 状态规则与 `tests.md` 的测试矩阵。
- 测试覆盖：新增 repository 回归测试和 API 正向契约测试；保留 source version 缺失返回 refreshing 的反向测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地验证已完成；生产仍需部署后只读验证默认 rows API 是否返回 `fresh` 与非空分页总数。
- 后续事项：发布必须走 `./scripts/deploy-oa.sh` 或现有运维流程，不直接在服务器热改代码。
