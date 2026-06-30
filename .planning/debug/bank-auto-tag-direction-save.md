---
status: resolved
trigger: "银行明细自动标签规则中，将水电费流水类型从不限改为支出后点击保存，页面提示规则已保存、银行明细已刷新，但重开后仍为不限；要求使用 GSD 从模块化边界和 I/O 角度分析并修复。"
created: 2026-06-30
updated: 2026-06-30
---

# Debug Session: bank-auto-tag-direction-save

## Symptoms

- Expected behavior: 自动标签规则保存后，`direction` 等规则字段必须持久化；重载规则 payload 后仍显示用户保存的值，并触发银行明细 read model refresh。
- Actual behavior: direction-only 变更返回成功提示，但后端没有保存，规则重载后仍为 `any`。
- Error messages: 页面无错误；HTTP 成功响应让前端显示“规则已保存，银行明细已刷新。”
- Timeline: 2026-06-30 用户截图反馈。
- Reproduction: 打开银行明细自动标签规则抽屉，将“水电费”流水类型从“不限”改为“支出”，保存后重新打开规则。

## Current Focus

- hypothesis: resolved.
- test: `tests.test_bank_transaction_category_service`、`tests.test_bank_auto_tag_rules_api`、`web/src/test/AutoTagRulesDrawer.test.tsx`。
- expecting: direction/account scope-only 变更会被自动标签规则 owner 判定为真实 payload 变更，版本递增、状态持久化、审计记录、bank detail refresh enqueue。
- next_action: 发布后执行生产页面写入/重载/刷新验证。
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-30: 前端 `AutoTagRulesDrawer.serializeRule(...)` 和 `web/src/features/bankDetails/api.ts` 均会发送 `direction`，前端不是漏传根因。
- 2026-06-30: `PUT /api/bank-details/auto-tag-rules` 进入 `BankDetailsApplicationService.update_auto_tag_rules(...)`，再进入 `AppSettingsService.update_bank_auto_tag_rules(...)`，模块写入边界正确。
- 2026-06-30: 本地复现显示 `BankTransactionCategoryService.normalize_auto_tag_rules_update(...)` 能生成 direction=expense 的 next tag dictionary，但 `changes.changed` 为 false，导致 `AppSettingsService` 直接返回当前 payload，不保存 state store。
- 2026-06-30: 根因定位到 `BankTransactionCategoryService._auto_tag_rule_changes(...)` 的旧字段白名单只覆盖 label/output/turnover/rules/priority/archive/reenable，遗漏 `direction`、`account_scope` 以及未来可能新增的持久化规则字段。
- 2026-06-30: 生产只读 SSH 检查显示 active release `main-123a2596-20260630092451`、commit `123a2596551c2c2d94bdb4214d75946b69005bb2`，API `/health/ready` 为 ready，worker 矩阵 active；该 release 仍包含旧的 `changed = bool(added or renamed or archived or reenabled or priority_changes or rule_changes)`，因此本次修复尚未部署，不能执行或声明生产写入验证已通过。

## Eliminated

- 前端漏传 direction：已排除，请求序列化包含 `direction`。
- API route owner 丢字段：已排除，route 只传递 JSON body，未裁剪字段。
- read model/worker 单纯延迟：不是根因；settings 本身没有保存成功，worker 刷新也无法产生正确规则事实。
- bank-flow-rule-batches 模块污染：已排除；该模块只读取 active bank detail tags，不拥有银行明细自动标签规则写入。

## Resolution

- root_cause: 自动标签规则 canonical owner 的变更判定仍使用旧的字段白名单，direction-only/account-scope-only 等真实规则 payload 变更被误判为 no-op，`AppSettingsService` 因此不持久化却让 HTTP 成功返回。
- fix: 将 `_auto_tag_rule_changes(...)` 的 no-op 判定改为比较规范化后的规则 payload 指纹，只忽略 `priority_label`、`rule_summary`、`editable`、`archivable`、`sortable` 等展示字段；新增 `rule_payload_changes` 并进入审计 metadata。
- verification: 本地新增并通过 business core 和 API/service 回归；复跑前端抽屉测试、docs 验证和 diff whitespace 检查。
- files_changed: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`、`backend/src/fin_ops_platform/services/app_settings_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_bank_auto_tag_rules_api.py`、`docs/modules/bank-details/implementation-notes.md`、`docs/modules/bank-details/tests.md`。
