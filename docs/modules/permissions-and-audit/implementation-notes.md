# 权限与审计 实施记录

## 2026-09-02 - 页面级访问账户替代旧权限层级

- 权限事实改为 `page_access_accounts[{username, page_keys}]`；普通账号只有“页面可访问/不可访问”，被授权页面内不再按账户拆分查看、导出和操作能力。
- 固定 `YNSYLP005` 拥有全部页面和访问账户控制面；其他账号即使拥有 OA 角色或 permission marker，也只能得到 Settings 中明确勾选的页面。
- 后端统一 route policy 同时保护读取与写入，未知 protected route fail closed；前端页面过滤、重定向和控件状态只是体验层，不替代后端校验。
- OA 只保留 `finops_app_user` 与 `finops_admin` 两个菜单投影角色；旧分层字段/角色只在 `0165` 一次性迁移和部署切换预检中识别，不能回到运行时链路。
- 历史记录中关于旧账户层级、只读写控件矩阵和三 OA 角色的内容只说明当时状态，均已被本节取代。

## 2026-08-20 - 批量账务 ETC summary Page Audit 事实对齐

- Page Audit 的 `batch_accounting` proof 复用共享 canonical ETC summary SQL；只有 relation external batch 标识、规范化 `etc-summary-*` 行 ID 与已提交 ETC batch 事实精确一致时，虚拟 invoice 成员才视为存在。
- 旧的 `app.invoices` 单源判断已移除；普通发票和错误 summary ID 仍 fail closed。Audit 保持只读、caller-owned snapshot，不新增 repair、read model、worker 或写能力。
- `tests/test_audit_page_canonical_data_tool.py` 覆盖 SQL 合同与真实 PostgreSQL 正反例。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 权限事实源在后端 OA session + `AccessControlService`。前端权限 hook 只负责用户体验，不能作为安全边界。
- 普通账号的唯一授权维度是页面集合；页面命中后，读取、导出和业务操作按该页面既有业务规则执行。`YNSYLP005` 固定拥有全部页面及管理控制面。
- 后端 route policy 必须覆盖所有 protected route；访问账户、数据重置、OA 凭据等管理入口额外检查 `can_admin_access`。
- 审计是 command/service 边界的一部分。重要业务写入应在同一事务或等价原子边界内提交业务事实、audit、dirty scope/outbox。
- `tests/test_permissions_write_entry_inventory.py` 只保留四项高价值机械约束：前后端 page registry 一致、canonical snapshot 唯一、旧层级不回流运行时、ACL 不新增 cache/queue/worker I/O。页面/API 行为由 service、API、component 与 Browser tests 直接证明，避免维护第二套庞大门禁清单。

## 2026-06-20 - admin 数据重置确认弹窗权限 smoke

- 目标：补强 `PERM-E2E-005` 的 admin 高风险 settings 覆盖，证明 admin 在真实 Chromium 中能进入数据重置影响确认和 OA 密码复核步骤。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 `tests.md`、`e2e-coverage.md`、`write-entry-inventory.md` 和全局 testing closure state。
- 关键决策：不改产品逻辑，也不在权限矩阵里真正提交数据重置 job；role matrix 只打开影响确认和密码复核，断言未填密码时 `确认清理` 禁用、填入密码后启用，然后取消并确认 `POST /api/workbench/settings/data-reset/jobs` 零新增。真正提交 job、polling、settings reload 和下游 fresh 行为仍由 `web/e2e/settings-data-reset-flow.spec.ts` 覆盖。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts::admin users can open admin settings and AppHealth operations`。
- 未测风险：真实 admin 凭据、真实 OA 密码复核、生产备份/restore、worker drain 和全页面最终 fresh 仍归 data-safety-reset staging/production smoke。

## 2026-06-20 - 关联台现金处理行级菜单权限 opener

- 目标：继续收敛 `PERM-E2E-003`，把关联台已配对银行行的现金过账、现金买票和取消现金处理行级菜单纳入 read-export Browser 权限矩阵。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、`e2e-coverage.md`、`tests.md` 和全局 testing 文档。
- 关键决策：不改产品逻辑；deterministic mock 新增 `workbenchCashSpecialActions` 开关，只在指定场景给已配对银行行暴露 `confirm_cash_pass_through`、`confirm_cash_ticket_purchase`、`cancel_cash_special`。role matrix 在 `read_export_only` 下证明更多菜单、现金处理 menuitem 和确认买票成本弹窗都不可见，并显式断言三个现金处理 durable mutation endpoint 零调用。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts::read-export users cannot trigger submitted-state write controls`；`tests.test_permissions_write_entry_inventory` 会双向校验新增 opener id 与 source sentinel。
- 未测风险：本轮证明只读角色无法暴露或触发现金处理行级菜单；full-access 现金买票成本填写/校验/worker fan-out 主流程仍应由 Workbench 业务流或后续专项 E2E 覆盖。

## 2026-06-20 - 关联台列拖拽权限 opener 补强

- 目标：继续收敛 `PERM-E2E-003`，把关联台列顺序拖拽这个隐式 `POST /api/workbench/settings` 写入口纳入 read-export Browser 权限矩阵。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、`e2e-coverage.md`、`tests.md` 和全局 testing closure state。
- 关键决策：不改产品逻辑；`CandidateGroupGrid` 已在 `canMutateData=false` 时禁用列拖拽 handle。本轮只在 role matrix 的 `reconciliation-workbench:open-candidate-actions` opener 中断言所有 `拖动 ... 列` handle disabled，模拟一次 mouse drag，确认 body 不进入 `column-layout-dragging`，并在高风险写入口测试末尾显式断言 `POST /api/workbench/settings` 零调用。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`；`tests.test_permissions_write_entry_inventory` 的关键词双向 gate 新增 `拖动 .* 列`，防止列拖拽写入口从 DOM 候选扫描中消失。
- 未测风险：这只证明 read-export 角色不能通过浏览器列拖拽保存 settings；真实代理、生产审计和未来新增的其它隐式写入口仍需继续 opener 或 staging smoke。

## 2026-06-19 - Browser 证据路径解析 gate

- 目标：继续收敛 `PERM-E2E-003`，防止 `write-entry-inventory.md` 引用已删除、重命名或拼错的 Playwright spec 后仍把页面写入口标成 Browser covered。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、本模块 tests/coverage/implementation notes 和全局 testing closure state。
- 关键决策：不改产品逻辑，不禁止少量 glob 证据；普通 `web/e2e/...` 路径必须是当前文件，包含 `*` 的证据必须至少匹配一个真实文件。
- 文档影响：更新本模块测试矩阵、coverage、本文件和全局闭环状态；`PERM-E2E-003` 仍保持 partial。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 13 个测试扩展到 14 个测试，新增 `test_documented_browser_evidence_paths_resolve_to_current_files`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`。
- 未测风险：该 gate 只证明文档证据路径未失效，不能自动打开所有未来页面抽屉；真实 OA/代理/生产审计仍需 staging/production smoke。

## 2026-06-19 - 源码写控件文案 sentinel gate

- 目标：继续收敛 `PERM-E2E-003`，防止高风险按钮文案在源码中改名后，`write-entry-inventory.md` 和 `permissions-role-matrix` 的关键词扫描仍保留旧词而形成假覆盖。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes 和全局 testing closure state。
- 关键决策：不做全源码自然语言自动分类，避免把筛选菜单“清空”等非写入口误报；先维护一组高风险 sentinel，把稳定的源码文件和动作关键词绑定起来。单测要求 sentinel 文案仍在源码中，且已登记到关键词 registry。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 10 个测试扩展到 11 个测试。
- 未测风险：该 gate 能保护已登记 sentinel 的改名/漏同步，不能自动证明所有未来新增按钮都已覆盖；未来新增高风险写控件仍需补 sentinel 或 Browser opener。

## 2026-06-19 - admin OA 申请人凭据 Browser smoke

- 目标：把 settings 的 admin-only OA 申请人凭据维护从组件/API 证据补强为真实 Chromium Browser smoke，同时把 `保存凭据`、`清空密码` 纳入 read-export 写控件关键词 registry。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes 和全局 testing closure state。
- 关键决策：不改产品逻辑；只补 deterministic mock 的 `PUT/DELETE /api/workbench/settings/oa-applicant-credentials/:code`，admin role matrix 中完成一次凭据保存和一次清空密码，断言 PUT body、两个 response 均为 200、密码输入清空、页面不回显密码、清空后显示未配置，且后续普通 settings 保存 body 不包含密码或凭据字段。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` admin 场景；`tests.test_permissions_write_entry_inventory` 的关键词双向 gate 会锁住 `保存凭据` 和 `清空密码`。
- 未测风险：真实 OA 凭据能否登录目标 OA、真实加密密钥和生产审计查询/导出仍归 staging/production smoke。

## 2026-06-19 - admin 访问账户管理 Browser smoke

- 目标：把 settings 的 admin-only 访问账户管理从“入口可见”补成真实 Chromium 保存 payload 证据，覆盖权限事实源自身的高风险写入口。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes 和全局 testing closure state。
- 退休说明（2026-08-02）：本段旧 generic ACL 保存方案已删除。当前 admin role matrix 通过 dedicated versioned access-control PUT 保存账户；普通 settings body 含任一 ACL key 都必须失败。OA 凭据仍保持独立且不进入普通 settings payload。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` admin 场景；`tests.test_permissions_write_entry_inventory` 的关键词双向 gate 会锁住 `新增账户`。
- 未测风险：真实 OA 角色同步、真实生产访问账户配置生效和审计查询/导出仍归 staging/production smoke。

## 2026-06-19 - role matrix opener 双向 inventory gate

- 目标：防止 `write-entry-inventory.md` 声明了不存在的 Browser opener 覆盖，或 Playwright 新增 opener 后漏登记，继续收敛 `PERM-E2E-003` 的文档与测试证据一致性。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、`e2e-coverage.md`、`tests.md`、本文件和全局 testing closure state。
- 关键决策：只加强机械 guard 和文档事实，不改变产品逻辑，也不把 `PERM-E2E-003` 从 partial 升级为 covered；深层 drawer/dialog 自动打开和真实环境权限 smoke 仍是剩余风险。
- 测试覆盖：新增 inventory -> Playwright 的反向 opener id 校验；现有 Playwright -> inventory 校验保持不变。

## 2026-06-19 - admin 销项收据编号设置保存 smoke

- 目标：把 `PERM-E2E-005` 从 admin 高风险入口可见补强为 admin 能在真实浏览器中打开销项收款的 admin-only 收据编号设置 drawer，并完成一次保存。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 coverage/tests/write-entry inventory/implementation notes 和全局 testing closure state。
- 关键决策：不改产品逻辑；只补 deterministic API mock 的 `GET/PUT /api/output-invoice-collections/receipt-settings`，并在 admin role matrix 中断言保存 PUT/200、drawer 关闭和无隐藏浏览器错误。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` admin 场景。
- 未测风险：真实 admin 凭据、真实代理层和生产审计查询/导出仍归 staging/production smoke。

## 2026-06-19 - mutating feature API inventory gate

- 目标：继续收敛 `PERM-E2E-003`，把“新增前端 mutating API client 但忘记进入权限写入口 inventory”的风险变成自动测试失败。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、本模块 coverage/tests/implementation notes 和全局 testing closure state。
- 关键决策：不改产品逻辑；只扫描 `web/src/features/*/api.ts` 里的 POST/PUT/PATCH/DELETE，并用 `MUTATING_API_MODULE_COVERAGE` 显式映射到已有模块 inventory row。shared API 如 `backgroundJobs`、`operationBarrier` 映射到其消费的运维/settings 模块。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 6 个测试扩展到 7 个测试。
- 未测风险：该 guard 只能发现新增 mutating API 文件或映射缺失，不能替代具体 Browser opener 对每个 drawer/dialog 按钮的行为证明。

## 2026-06-19 - 写控件关键词 registry 双向文档事实源

- 目标：继续收敛 `PERM-E2E-003`，把 `permissions-role-matrix` DOM 扫描使用的高风险写动作关键词从测试硬编码清单提升为 `write-entry-inventory.md` 可审计事实源，并防止 Playwright pattern 出现未登记关键词。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes。
- 关键决策：不改 Browser 行为；`enabledWriteControlPattern` 仍留在 Playwright spec 中实际执行，inventory 单测改为读取 `Write control keyword registry` 并双向校验文档关键词与 Playwright pattern 字面关键词一致。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 7 个测试扩展到 8 个测试。
- 未测风险：关键词 registry 只能保证扫描 pattern 包含已知写动作短语；尚未由 role matrix 打开的 drawer/dialog 仍需要继续补 opener。

## 2026-06-19 - pageRegistry 与 write-entry inventory 双向一致性 gate

- 目标：继续收敛 `PERM-E2E-003`，防止删除或重命名页面后 `write-entry-inventory.md` 保留陈旧模块 row，误导后续审计。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes。
- 关键决策：不添加白名单；当前 inventory 的每一行都对应 `pageRegistry.tsx` 当前页面模块。若未来出现 shared-only 权限域，需要先在文档中说明并显式调整测试。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 8 个测试扩展到 9 个测试。
- 未测风险：该 guard 只保证页面模块集合一致，不证明每个页面内部所有 drawer/dialog 已被 role matrix 打开。

## 2026-06-19 - pageRegistry 与 role matrix route 双向一致性 gate

- 目标：继续收敛 `PERM-E2E-003`，防止 `permissions-role-matrix.spec.ts` 保留已删除或改名的页面路径，造成 Browser role matrix 对真实页面集合的覆盖声明失真。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests/implementation notes。
- 关键决策：`/operations/app-health` 是 admin-only route，仍作为显式例外；其他 readable route 必须与 `pageRegistry.tsx` 当前路径集合一致。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 9 个测试扩展到 10 个测试。
- 未测风险：该 guard 只保证 route 集合一致，不证明每个 route 内部所有 drawer/dialog 已被 role matrix 打开。

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

## 2026-06-19 - covered-browser dynamic/static proof gate

- 目标：继续收敛 `PERM-E2E-003`，防止页面写入口矩阵把某个模块标记为 `covered-browser`，但既没有 role matrix dynamic opener，也没有说明为什么首屏/专门 Browser flow 已足够证明 read-export 零 mutation。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 tests/implementation notes 和全局 testing closure state。
- 关键决策：不把导入页、成本统计、settings、AppHealth 等无额外动态 opener 的页面硬塞进 opener registry；新增 `Role matrix 页面级静态覆盖 registry` 作为显式证明表。单测要求每个 `covered-browser` row 要么属于 opener module，要么登记在静态覆盖 registry。
- 文档影响：更新写入口 inventory、权限测试矩阵、本文件和全局闭环状态。
- 测试覆盖：`tests.test_permissions_write_entry_inventory` 从 11 个测试扩展到 13 个测试，新增 `test_covered_browser_rows_have_dynamic_opener_or_documented_static_role_matrix_proof` 和 `test_role_matrix_opener_and_static_coverage_modules_are_current_covered_browser_rows`；后者会防止 dynamic/static registry 引用非 `covered-browser` 模块，或同一模块同时放进 dynamic 与 static registry。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`。
- 未测风险：该 gate 证明 coverage 声明有 opener 或静态理由，不自动打开所有未来页面抽屉；`PERM-E2E-003` 仍保持 partial。

## 2026-06-19 - 权限写控件关键词机械 guard

- 目标：把 role matrix 的 visible enabled 写控件关键词从人工维护推进到可测试合同，避免后续误删深层动作关键词后仍显示测试通过。
- 影响范围：`tests/test_permissions_write_entry_inventory.py`、本模块 coverage/tests/implementation notes。
- 关键决策：不改产品逻辑；单测直接读取 `permissions-role-matrix.spec.ts` 的 `enabledWriteControlPattern`，要求保存设置、保存计划、保存规则、保存补充信息、确认买票、确认为买票、确认为过账、取消现金处理、作废/重开收据、创建正式收据、关联支出流水、选择发票、异常处理等关键写动作保持在扫描关键词里。
- 文档影响：更新本模块测试矩阵和 coverage；`PERM-E2E-003` 仍保持 partial，因为关键词 guard 不能替代尚未自动打开的深层 drawer/dialog。
- 测试覆盖：新增 `tests.test_permissions_write_entry_inventory.PermissionsWriteEntryInventoryTests.test_role_matrix_write_control_keywords_cover_known_deep_actions`。
- 验证命令：见本轮最终执行记录。
- 未测风险：关键词 guard 只能防止已知动作标签漏扫，不能证明所有隐藏抽屉都已打开；真实 OA/代理/生产审计仍需 staging/production smoke。
- 后续事项：继续从关键业务页面增加安全 opener，把关键词扫描推进成实际 drawer/dialog 证据。

## 2026-06-19 - 现金特殊处理和补充信息写控件关键词 gate

- 目标：继续收敛 `PERM-E2E-003`，把源码中存在但尚未由 role matrix 自动打开的深层写动作纳入 visible enabled 写控件候选扫描。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests 和全局 testing closure state。
- 关键决策：不改产品逻辑，也不盲目打开未知业务弹窗；先把 `确认买票`、`确认为买票`、`确认为过账`、`取消现金处理`、`保存补充信息` 加入 read-export DOM 候选关键词。若未来这些按钮在 read-export 首屏或已打开动态区域中变为 enabled，权限矩阵会失败。
- 文档影响：更新 `PERM-E2E-003` 覆盖描述；本项仍保持 partial，因为尚未自动打开所有页面特定抽屉/弹窗。
- 测试覆盖：`web/e2e/permissions-role-matrix.spec.ts` visible enabled write-control candidate scan。
- 验证命令：见本轮最终执行记录。
- 未测风险：现金买票成本弹窗、turnover extra 抽屉等仍需后续安全 opener 或页面级专项 E2E 覆盖；真实生产审计和代理层行为仍归 staging/production smoke。
- 后续事项：继续选择可安全打开的深层 drawer/dialog，把关键词扫描升级为实际 opener 证据。

## 2026-06-19 - pending invoices income rules 权限 opener

- 目标：继续收敛 `PERM-E2E-003`，把待找发票“收入待找发票规则设置”从页面级写入口清单补成 read-export role matrix 深层抽屉 Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes。
- 关键决策：不改产品权限逻辑；在 read-export 角色下切到收入方向，打开收入规则抽屉，断言只读提示、保存规则禁用、`PUT /api/pending-invoices/rules` 零调用，并复扫 visible enabled 写控件候选。
- 文档影响：新增 `pending-invoices:income-rules` opener id，更新 `PERM-E2E-003` 覆盖描述；本项仍保持 partial，因为尚未自动打开所有页面特定抽屉/弹窗。
- 测试覆盖：`web/e2e/permissions-role-matrix.spec.ts::read-export users cannot trigger high-risk write controls`。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产规则保存审计、真实大数据筛选和代理层行为仍归 staging/production smoke。
- 后续事项：继续向 role matrix opener registry 增加尚未安全打开的页面特定深层 drawer/dialog。

## 2026-06-19 - full-access settings 保存权限矩阵 smoke

- 目标：把 `PERM-E2E-004` 从“普通业务写入口可见”补强为“普通业务写入口可在真实浏览器中完成一次允许写入且无隐藏错误”。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 `e2e-coverage.md`、`tests.md`、`write-entry-inventory.md` 和全局 `docs/dev/testing-closure-state.md`。
- 关键决策：不改产品权限逻辑；复用 settings 项目状态保存作为最小 full-access 写入 smoke，断言 `POST /api/workbench/settings` body、200 response、成功反馈和严格浏览器错误捕获。admin-only settings 区和 AppHealth dashboard 仍对 full-access 不可见。
- 文档影响：更新本模块 coverage/tests/inventory 和全局 testing closure state；`PERM-E2E-003` 仍保持 partial，因为尚未自动打开所有页面特定抽屉/弹窗和真实 OA/代理/审计 smoke。
- 测试覆盖：`web/e2e/permissions-role-matrix.spec.ts::full-access users can write business pages but cannot open admin operations`。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium` 通过 6 tests。
- 未测风险：真实生产 settings 保存审计、真实 OA admin/full-access 角色同步和代理层行为仍需 staging/production smoke。
- 后续事项：继续向 role matrix opener registry 增加尚未安全打开的页面特定深层 drawer/dialog。

## 2026-06-19 - batch accounting submitted-state 撤回权限 opener

- 目标：继续收敛 `PERM-E2E-003`，把批量账务已提交 bucket 的撤回入口从 full_access 主流程证据补成 read-export role matrix Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 coverage/tests/write-entry inventory/implementation notes、batch-accounting coverage 和全局 testing 文档。
- 关键决策：不改产品逻辑；未提交态 OA 选择和已提交态撤回依赖不同初始数据，所以用独立 submitted-state mock/test 覆盖 `撤回关联` disabled 和 withdraw endpoint 零调用，避免污染主 high-risk opener registry。
- 文档影响：`write-entry-inventory.md` 新增 `batch-accounting:submitted-withdraw` opener id；`PERM-E2E-003` 仍保留 partial。
- 测试覆盖：`permissions-role-matrix` 新增 read-export submitted-state write controls 场景，配合 inventory gate 防止 opener 漏登记。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产历史 relation、大年份和 worker drain 仍归 batch-accounting staging/runtime smoke。
- 后续事项：继续补尚未由 role matrix 自动打开的页面特定抽屉/弹窗。

## 2026-06-19 - ETC 对账流程 opener 补齐

- 目标：继续收敛 `PERM-E2E-003` 和 `ETC-TICKET-E2E-009`，把 ETC source file 上传、确认对账和人工核对处理动作从组件/API 证据补成 role matrix opener registry Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes 和全局 testing 文档。
- 关键决策：不改产品逻辑；read-export 下进入 `/etc-tickets` 后打开/定位 ETC 批次流程区，断言上传信用卡账单、上传票根网、确认对账、接受推荐票根、关联所选记录、排除非 ETC、标记异常、手工确认均禁用，并复扫 visible enabled 写控件候选。
- 文档影响：`write-entry-inventory.md` 新增 `etc-tickets:reconciliation-workflow` opener id；`PERM-E2E-003` 仍保留 partial。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` opener registry 和写控件关键词。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
  - `bash scripts/verify.sh docs`
- 未测风险：尚未由 opener registry 打开的其他页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：继续从已知页面级 E2E 和组件测试中挑选 read-export 下可安全打开的 drawer/dialog 登记为 opener。

## 2026-06-19 - 三类导入页 read-export 写入口显式断言

- 目标：继续收敛 `PERM-E2E-003`，把银行流水导入、发票导入、ETC 发票导入的 read-export 导入控件从首屏扫描提升为显式 Browser 合同。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts` 和权限 testing 文档。
- 关键决策：不改产品逻辑；三类导入页都断言只读提示可见、开始预览禁用、确认导入禁用、file input 禁用，并复扫 visible enabled 写控件候选。
- 文档影响：`PERM-E2E-003` 仍保留 partial；本轮只收敛已知导入页写入口，不宣称所有动态抽屉已覆盖。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` 高风险写入口用例。
- 验证命令：
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
- 未测风险：尚未由 opener registry 打开的其他页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：继续挑选可安全打开的 drawer/dialog 登记为 opener registry。

## 2026-06-19 - 进项 OA reverse opener 补齐

- 目标：继续收敛 `PERM-E2E-003`，把进项发票使用的以发票反提 OA 工作流从页面级 flow 证据补成 role matrix opener registry Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes 和全局 testing 文档。
- 关键决策：不改产品逻辑；`/api/input-invoice-usage/oa-reverse/preview` 是打开工作流所需的 read-like POST，role matrix 只对这一条 preview 做显式例外，同时继续断言 OA draft、batch 和 manual status durable write endpoint 零调用。
- 文档影响：`write-entry-inventory.md` 新增 `input-invoice-usage:oa-reverse` opener id；`PERM-E2E-003` 仍保留 partial。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` opener registry，read-export 下打开 OA reverse 工作流，断言 `canCreateDraft=false`、创建 OA 草稿禁用、候选表可读、visible enabled 写控件候选为空。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
  - `bash scripts/verify.sh docs`
- 未测风险：尚未由 opener registry 打开的其他页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：继续从已知页面级 E2E 和组件测试中挑选 read-export 下可安全打开的 drawer/dialog 登记为 opener。

## 2026-06-19 - OA pending 规则 opener 补齐

- 目标：继续收敛 `PERM-E2E-003`，把 OA pending 的支出流水无需开票规则 drawer 从组件/页面流证据补成 role matrix opener registry Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes 和全局 testing 文档。
- 关键决策：该 drawer 在 read-export 下可安全打开，mock payload `canSave=false`，只断言规则只读、保存规则禁用和 visible enabled 写控件候选为空，不触发保存。
- 文档影响：`write-entry-inventory.md` 新增 `oa-pending-payments:expense-rules` opener id；`PERM-E2E-003` 仍保留 partial。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts` opener registry。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
  - `bash scripts/verify.sh docs`
- 未测风险：尚未由 opener registry 打开的其他页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：继续从已知页面级 E2E 和组件测试中挑选 read-export 下可安全打开的 drawer/dialog 登记为 opener。

## 2026-06-19 - read-export 动态区域 opener registry

- 目标：把 `PERM-E2E-003` 已安全打开的动态区域从单条长测试流程整理为显式 opener registry，并增加 registry 到 inventory 的机械一致性 gate。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_permissions_write_entry_inventory.py`、本模块 write-entry inventory/coverage/tests/implementation notes 和全局 testing 文档。
- 关键决策：`readExportDynamicWriteControlOpeners` 只登记 read-export 下可安全打开、不会触发业务写入的 drawer/dialog/动态区域；每个 opener 自己进入页面、打开区域、断言只读状态并复跑 `expectNoEnabledWriteControlCandidates`。不做通用乱点爬虫。
- 文档影响：`write-entry-inventory.md` 新增 opener registry 表，后续新增 opener 必须登记 id；`PERM-E2E-003` 仍保留 partial。
- 测试覆盖：扩展 `tests/test_permissions_write_entry_inventory.py`，校验每个 opener id 都有 inventory 登记；重构 `web/e2e/permissions-role-matrix.spec.ts` 保持原有 Browser 覆盖。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
  - `bash scripts/verify.sh docs`
- 未测风险：尚未由 opener registry 打开的页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：下一轮按 registry 继续补更多安全 opener，优先覆盖仍只能靠页面级 E2E 或组件/API 证明的深层写入口。

## 2026-06-19 - read-export 动态区域写控件候选扫描

- 目标：继续收敛 `PERM-E2E-003`，把 DOM 写控件候选扫描从首屏扩展到 role matrix 已安全打开的动态抽屉和高风险区域。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes。
- 关键决策：不盲目点击所有页面按钮；只在现有 role matrix 已经打开并验证的银行自动标签抽屉、no-OA 标签抽屉、pending invoice 规则抽屉、收入批量区、进项支付规则抽屉、销项收款状态规则抽屉、销项收据历史抽屉、OA pending 进行中区、batch accounting 选择区、turnover 标签抽屉和明细区复用 `expectNoEnabledWriteControlCandidates`。这能发现新增 enabled 写按钮，同时避免对未知业务按钮做破坏性点击。
- 文档影响：`PERM-E2E-003` 仍保留 partial，但剩余原因收窄为尚未由 role matrix 自动打开的页面特定抽屉/弹窗，以及真实环境权限 smoke。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
- 未测风险：未自动打开的页面特定抽屉/弹窗、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：下一轮可维护一个明确的 drawer opener registry，逐步登记更多页面抽屉/弹窗的安全打开步骤。

## 2026-06-19 - read-export visible DOM 写控件候选扫描

- 目标：继续收敛 `PERM-E2E-003`，让同一页面首屏或当前 visible DOM 中新增的高风险写按钮如果在 `read_export_only` 下仍 enabled，会在 Browser role matrix 中失败。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、本模块 coverage/tests/write-entry inventory/implementation notes 和全局 testing 文档。
- 关键决策：扫描真实 Chromium 页面中 visible enabled 的 button、`role=button`、`role=menuitem` 和 file input；只匹配明确动作短语，例如保存设置、确认导入、确认闭环、写回、撤回、删除、新建批次、关联支出流水、选择发票、提交 OA 等，避免把“已提交”等状态文案误判为写入口。
- 文档影响：`PERM-E2E-003` 仍保留 partial，但剩余原因收窄为隐藏/动态抽屉内未被打开的新增写入口和真实环境权限 smoke。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：
  - `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`
- 未测风险：隐藏/动态抽屉深层爬取、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：下一轮可为 role matrix 增加页面特定的 drawer opener registry，逐步自动打开规则、标签、详情、导入等抽屉后再跑同一候选扫描。

## 2026-06-19 - 权限写入口 inventory 自动一致性 gate

- 目标：继续收敛 `PERM-E2E-003`，把“新增页面漏写权限写入口 inventory / role matrix”的风险从人工约定变成自动测试失败。
- 影响范围：新增 `tests/test_permissions_write_entry_inventory.py`，更新本模块 coverage、tests、write-entry inventory、implementation notes 和全局 Spec-first/testing 文档。
- 关键决策：先建立低成本、稳定的 registry/inventory/role-matrix 一致性 gate；不做脆弱的通用 DOM 文案猜测爬虫。测试校验 `pageRegistry.tsx` 每个页面都有 inventory row、每个非 admin route 都在 `permissions-role-matrix` read-export smoke 中打开、`covered-*` inventory row 必须引用 Browser E2E 证据。
- 文档影响：`PERM-E2E-003` 仍保留 partial，但剩余原因从“新增页面/入口尚无自动发现”收敛为“同一页面内部新增按钮/抽屉/批量动作的 DOM 语义自动发现和真实环境 smoke 尚未闭合”。
- 测试覆盖：新增 `tests/test_permissions_write_entry_inventory.py`。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`
  - `bash scripts/verify.sh docs`
  - `git diff --check -- tests/test_permissions_write_entry_inventory.py docs/modules/permissions-and-audit docs/dev/spec-first-e2e-inventory.md docs/dev/testing.md docs/dev/testing-closure-state.md`
- 未测风险：同一页面内部新增按钮的 DOM 语义自动发现、真实 OA role sync、真实代理下载 header、生产审计查询/导出。
- 后续事项：下一轮可从 `useSessionPermissions()` 调用点和 mutating API client 生成候选写入口，进一步降低同页新增按钮漏登记风险。

## 2026-06-19 - turnover extra 写入口 Browser 证据补齐

- 目标：收敛 `PERM-E2E-003` 中最后一个明确的本地 Browser 缺口，证明 read-export 用户不能进入 turnover extra 写入口且不会触发 mutation。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、本模块 coverage/tests 和全局 Spec-first/testing 文档。
- 关键决策：
  - 不改变产品逻辑；`TurnoverLedgerPage` 已在 read-export 下禁用 flow action，所以 Browser 证据断言 extra 编辑入口 disabled，而不是强行打开抽屉。
  - extra 抽屉内部保存/confirm/withdraw 仍由组件/API/后端 guard 覆盖；只读角色无法进入该写入口时，Browser 层以入口 disabled + 零 mutation 为合同。
  - `PERM-E2E-003` 仍保留 partial；剩余原因改为新增按钮自动发现和真实 OA/代理/生产审计 smoke，而不是当前已知 turnover extra 缺口。
- 文档影响：更新 `write-entry-inventory.md`、`e2e-coverage.md`、`tests.md`、本文件和全局 testing 文档。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`；`git diff --check -- web/e2e/permissions-role-matrix.spec.ts docs/modules/permissions-and-audit docs/dev/spec-first-e2e-inventory.md docs/dev/testing.md docs/dev/testing-closure-state.md`。
- 未测风险：新增/未来写按钮自动发现、真实 OA role sync、真实代理下载 header、生产审计查询/导出。

## 2026-06-19 - 银行明细分类确认 role matrix opener 补强

- 目标：继续收敛 `PERM-E2E-003`，把银行明细行内分类确认入口从页面级权限证据补成 role matrix opener registry Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、`e2e-coverage.md`、`tests.md`、全局 Spec-first inventory 和 closure state。
- 关键决策：
  - 不改产品逻辑；通过 deterministic mock 的 `bankDetailsClassificationMode: "needs_confirmation"` 进入待确认分类状态。
  - 只验证 `read_export_only` 下行内 `待确认` 禁用、分类菜单未打开、category-confirmation durable mutation 零调用，并复用 existing high-risk role matrix test。
  - `PERM-E2E-003` 仍保留 partial；剩余缺口仍是尚未由 role matrix 自动打开的页面特定抽屉/弹窗，以及真实环境权限 smoke。
- 文档影响：`write-entry-inventory.md` 新增 `bank-details:category-confirmation` opener id，并同步本模块和全局状态文档。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`；`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`；`bash scripts/verify.sh docs`；`git diff --check -- web/e2e/permissions-role-matrix.spec.ts docs/modules/permissions-and-audit/write-entry-inventory.md docs/modules/permissions-and-audit/e2e-coverage.md docs/modules/permissions-and-audit/tests.md docs/modules/permissions-and-audit/implementation-notes.md docs/dev/spec-first-e2e-inventory.md docs/dev/testing-closure-state.md`。
- 未测风险：真实 OA role sync、真实代理下载 header、生产审计查询/导出，以及未来新增深层 drawer/dialog 写入口。

## 2026-06-19 - 关联台已配对撤回 role matrix opener 补强

- 目标：继续收敛 `PERM-E2E-003`，把关联台已配对候选的撤回入口从页面级权限证据补成 role matrix opener registry Browser 证据。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、`e2e-coverage.md`、`tests.md`、全局 Spec-first inventory 和 closure state。
- 关键决策：
  - 不改产品逻辑；已配对状态通过 deterministic mock 的 `workbenchInitialRelationConfirmed` 进入，只验证 `read_export_only` 下撤回关联 disabled、更多/取消关联/异常处理入口隐藏、withdraw preview/submit 零调用。
  - 复用现有 submitted-state role matrix test，避免额外增加慢测试数量。
  - `PERM-E2E-003` 仍保留 partial；剩余缺口仍是尚未由 role matrix 自动打开的页面特定抽屉/弹窗，以及真实环境权限 smoke。
- 文档影响：`write-entry-inventory.md` 新增 `reconciliation-workbench:paired-withdraw-actions` opener id，并同步本模块和全局状态文档。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v`；`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`；`bash scripts/verify.sh docs`；`git diff --check -- web/e2e/permissions-role-matrix.spec.ts docs/modules/permissions-and-audit/write-entry-inventory.md docs/modules/permissions-and-audit/e2e-coverage.md docs/modules/permissions-and-audit/tests.md docs/modules/permissions-and-audit/implementation-notes.md docs/dev/spec-first-e2e-inventory.md docs/dev/testing-closure-state.md`。
- 未测风险：真实 OA role sync、真实代理下载 header、生产审计查询/导出，以及未来新增深层 drawer/dialog 写入口。

## 2026-06-19 - 权限写入口 inventory 与 read-export gate 补强

- 目标：继续收敛 `PERM-E2E-003`，把权限按钮矩阵从笼统 partial 推进到可逐页面追踪，并修复 role matrix 发现的前端 gate 缺口。
- 影响范围：`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/pages/BatchAccountingPage.tsx`、`web/src/pages/TurnoverLedgerPage.tsx`、`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/write-entry-inventory.md`、全局 Spec-first inventory 和 testing closure state。
- 关键决策：
  - 后端 guard 仍是安全边界；前端只补 UI gate，避免只读用户看到或触发明显写入口。
  - OA pending read-export 下隐藏 confirm-paid 和 OA 选择、禁用 link-bank；batch accounting read-export 下 submit/withdraw disabled；turnover read-export 下标签抽屉保存/全选/清空和 flow selection disabled。
  - pending invoices read-export 下选择已有发票、收入状态和规则保存禁用，且 full-access 选择已有发票、收入状态、规则保存主流程回归通过。
  - ETC read-export 下提交 OA、新建批次和删除入口禁用，full-access OA 草稿创建和人工提交主流程回归通过。
  - `PERM-E2E-003` 仍保留 partial；后续需要继续补写入口 inventory 的自动发现和真实环境权限 smoke。
- 文档影响：新增 `write-entry-inventory.md`，更新本模块 README、tests、coverage、implementation notes，以及全局 testing 文档。
- 测试覆盖：扩展 `web/e2e/permissions-role-matrix.spec.ts`，并回归受影响页面的 full-access 主流程。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`；`cd web && npx playwright test e2e/oa-pending-payments-confirm-paid-flow.spec.ts e2e/oa-pending-payments-bank-link-flow.spec.ts e2e/batch-accounting-flow.spec.ts e2e/turnover-ledger-flow.spec.ts --project=chromium`；`cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts e2e/pending-invoices-income-status-flow.spec.ts e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`cd web && npx playwright test e2e/etc-tickets-flow.spec.ts --project=chromium`。
- 未测风险：新增/未来写按钮自动发现；真实 OA role sync、真实代理下载 header 和生产审计查询/导出。

## 2026-06-19 - 权限 shared Spec-first 合同与 Browser 错误捕获

- 目标：把权限与审计从旧 `documented-risk` 推进为 shared-level Spec-first 可审计状态，明确哪些权限合同已 covered，哪些仍是 partial/external-risk。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`docs/modules/permissions-and-audit/e2e-spec.md`、`docs/modules/permissions-and-audit/e2e-coverage.md`、本模块测试矩阵和全局 Spec-first inventory。
- 关键决策：
  - 不改权限产品逻辑；现有 Browser/API/component/service tests 已覆盖 session gate、全页面 read-export 可读零 mutation、settings/tax/import/no-OA/AppHealth 高风险入口、admin/full-access gate、API guard、audit 和敏感数据保护。
  - 给 role matrix Browser 流补严格错误捕获，确保全页面 role matrix 中隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog 会失败。
  - 不把“每个页面每个未来/细分写按钮”伪装成已 covered；该项保留为 `PERM-E2E-003` partial，后续需基于按钮 inventory 或页面级补测继续推进。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本文件和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/permissions-role-matrix.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：每页面每写入口全按钮矩阵、真实 OA 菜单/角色同步、生产 token 过期语义、真实导出下载代理 header 和生产审计查询/导出。

## 2026-06-17 - Browser role matrix 权限闭环

- 目标：把权限矩阵从组件/API 层推进到真实 Chromium，覆盖 read_export_only/full_access/admin 在全页面导航和高风险写入口上的可见行为。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`web/src/components/imports/ImportWorkflowPage.tsx`、`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/package.json` smoke。
- 关键决策：不改变后端权限 contract；前端继续使用 `/api/session/me` 的 `can_mutate_data/can_admin_access` 作为 UI 门禁。read_export_only 在浏览器里可打开所有非 admin 页面，但不应触发 mutation API；full_access 可用普通业务写入口但不能进 AppHealth；admin 可进入 settings 高危区和 AppHealth。
- 文档影响：更新权限模块测试矩阵、状态机、全局测试说明、Nightly CI 风险和 closure state。
- 测试覆盖：新增 Playwright role matrix；新增 NoOaBankBatchPage read-only unit regression；相关 Vitest 覆盖 ImportCenter、NoOa、WorkbenchSelection、App、SessionGate、SessionApi。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`；`cd web && npm test -- --run src/test/ImportCenterPage.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/WorkbenchSelection.test.tsx src/test/App.test.tsx src/test/SessionGate.test.tsx src/test/SessionApi.test.ts`。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期语义、真实导出下载与代理层 header、生产审计查询/导出仍需 staging/生产 smoke。
- 后续事项：新增页面或新增写入口时，必须把 read_export_only 行为加入本 role matrix 或对应页面 e2e。

## 2026-06-16 - access tier 聚合矩阵 gate

- 目标：把分散的 readonly/full/admin/denied 权限证据压成一个后端 session contract 聚合测试，降低 17 个页面 P2/P3 推进时权限口径漂移风险。
- 影响范围：`/api/session/me`、settings access control、`AccessControlService` 动态 provider 组装、默认 admin、权限码用户和未授权用户。
- 关键决策：不修改权限逻辑；新增 `test_get_session_me_projects_access_tier_matrix_from_settings` 走真实 app 组装后的 `/api/session/me`，同时校验 `read_export_only`、`full_access`、settings admin、默认 admin、permission-code full access、`denied` 的 `access_tier/can_access_app/can_mutate_data/can_admin_access`。
- 文档影响：更新 `tests.md` 和 P2/P3 closure ledger，把“全角色矩阵缺少单测”收敛为“session contract 已有聚合矩阵；页面级按钮/导出/写入交互仍由各模块和 nightly 覆盖”。
- 测试覆盖：新增后端 API contract / business core 聚合测试；复跑 auth guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_session_api.SessionApiTests.test_get_session_me_projects_access_tier_matrix_from_settings -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard -v`。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期语义、代理层真实导出下载、生产审计查询/导出仍需 staging/生产 smoke。
- 后续事项：发现具体页面权限绕过时，先在对应页面模块补最小 regression，再回链本模块矩阵。

## 2026-06-16 - readonly export 路由聚合 smoke

- 目标：补齐 P2/P3 台账中“导出权限 smoke 分散”的本地聚合证据，保证只读导出用户可读/可导出但不能写入或进入 admin 操作。
- 影响范围：protected API guard、cost statistics export、turnover ledger export、pending invoice export auth pass-through、pending/input invoice rules、turnover tag selection、bank auto-tag reapply、settings data reset。
- 关键决策：不把缺少 SQL read repository 的 pending export 误判为权限失败；测试只断言 readable/export routes 不返回 `401/403` 或 auth/admin 错误，并对可稳定生成 XLSX 的 cost/turnover 下载断言 content type。
- 文档影响：更新 `tests.md` 和 P2/P3 closure ledger。
- 测试覆盖：新增 `test_readonly_export_user_can_export_but_cannot_mutate_or_admin`，覆盖 API contract / existing regression 的 representative smoke。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard.AuthGuardTests.test_readonly_export_user_can_export_but_cannot_mutate_or_admin -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard -v`。
- 未测风险：真实浏览器下载、反向代理 `Content-Disposition`/`Access-Control-Expose-Headers`、生产 OA session 和审计导出查询仍需 staging/production smoke。
- 后续事项：新增页面导出时应加入本聚合 smoke 或对应模块的权限测试。

## 2026-06-11 - permissions-and-audit 测试闭环首轮

- 目标：补齐权限与审计横切边界的影响面、七类测试矩阵、状态机、验证命令和真实环境风险。
- 影响范围：`auth.py`、`AccessControlService`、`AuditTrailService`、`SessionContext`、`SessionGate`、settings access control、各 API mutation/admin guard、导出权限、业务 UoW audit。
- 关键决策：不新增低价值代码测试；已有测试已经覆盖 session、auth guard、access tier、write/admin 403、前端权限 UI、audit 原子性和敏感数据保护。本轮补齐文档闭环。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 auth/session/audit/settings/data reset/OA credential/tax/pending/turnover/bank tag/runtime boundary；前端覆盖 SessionGate、SessionApi、Settings、Workbench、AppHealth、AppStatus、TaxOffset。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期、全页面全角色矩阵、审计查询/导出、代理层导出下载权限。
- 后续事项：发现权限绕过或审计遗漏时，先补最小 regression test，再登记到 `docs/dev/regression-bug-bank.md`。
