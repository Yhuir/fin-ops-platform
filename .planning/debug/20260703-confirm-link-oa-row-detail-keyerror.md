# 2026-07-03 - Confirm Link OA Row Detail KeyError

## Symptom

确认关联选中 `OA + 银行流水 + 进项发票` 后，提交失败并把 `oa-exp-*` row id 作为错误消息透给前端。

## Hypothesis

确认写入前的 row 解析边界没有完整消费 Workbench read model。`row_ids` 是 Workbench row id，但旧 row-detail 路径仍优先读取 live detail；同时 cached resolver 只索引 `paired/open.groups[*]`，遗漏平铺 `paired/open.{oa,bank,invoice}` 行。

## Evidence

- 新增回归 `test_row_detail_resolves_flat_cached_read_model_before_live_detail` 在当前实现下失败：row-detail 先调用 live detail。
- 新增回归 `test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail` 在当前实现下失败：confirm-link 金额校验解析 `oa-exp-*` 时触发 live detail。

## Fix

- `WorkbenchRowDetailApiRoutes.get_payload(...)` 改为 cache/query-facade first；legacy/live fallback 只保留在非 SQL read model runtime 兼容尾部。
- `Application._grouped_rows_by_id(...)` 统一索引平铺行和 group 成员行；group 成员保留覆盖同 id 平铺行的优先级。

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_resolves_flat_cached_read_model_before_live_detail tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail -v`

## Follow-up Symptom

同日生产复测仍失败：确认关联显式选中 canonical OA `oa-exp-2156`、银行流水 `txn_imported_0405` 和 OA 附件进项发票时，preview 弹窗前返回 `"'oa-exp-69fab21659b12d7d42a50a45'"`。

## Follow-up Evidence

- 浏览器 DOM 证据显示用户选中的 OA 行是 `oa-exp-2156`，失败消息里的 `oa-exp-69fab21659b12d7d42a50a45` 不是选中行，而是 OA 附件发票 row id / source metadata 中的原始来源 OA id。
- `WorkbenchWriteFacade.preview_confirm_link(...)` 在金额校验前会调用 `_expand_confirm_link_row_ids_for_existing_context(...)`。旧 `_confirm_link_context_row_ids_to_preserve(...)` 只从当前 source group 的 `oa_rows` 判断已选 OA；当 source group 的 OA 是原始来源 id、用户选中的是 canonical Workbench OA id 时，逻辑会把原始来源 id 当成“缺失 OA”补进 action row_ids。
- 生产 row-detail 进一步证明：附件发票的 `source_workbench_row_id` 指向发票 Workbench row id；发票回连 OA 的事实是 `derived_from_oa_id/source_expense_item_id=oa-exp-69...:item:...`，而 canonical OA 行 `oa-exp-2156` 在 `detail_fields.Mongo文档ID` 中持有 `69...`。旧逻辑没有把已选 OA 行 payload 转成 source aliases。

## Follow-up Fix

- `oa_row_source_ids(...)` 把 OA 行的 canonical row id、`detail_fields.Mongo文档ID`、`OA单号/流程请求ID` 等转换为可用于附件发票 source 匹配的 aliases。
- `_expand_confirm_link_row_ids_for_existing_context(...)` 只从 cached read model 读取已选 OA 行 payload 生成 aliases；`_confirm_link_context_row_ids_to_preserve(...)` 使用 aliases 判断已选 canonical OA 是否已经覆盖选中的 OA 附件发票，并在覆盖时不再把同一发票的原始 source OA id 补进 action row_ids。
- `confirm_link_preview` route 将 `KeyError(row_id)` 映射为 `workbench_row_not_found`，避免内部 row id 字符串直接污染前端错误文案。

## Follow-up Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_oa_attachment_source_link_resolver.WorkbenchOaAttachmentSourceLinkResolverTests.test_source_oa_id_for_attachment_link_matches_canonical_workbench_oa_id tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_does_not_expand_raw_oa_source_when_canonical_oa_is_selected tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_maps_missing_row_to_row_not_found_error -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_existing_oa_attachment_context_rows tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_existing_oa_attachment_context_when_bank_and_invoice_selected tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_expands_oa_attachment_context_from_all_scope_read_model_when_month_filter_hides_invoice tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_active_relation_rows_for_selected_oa_context tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_row_detail_boundary_when_read_model_payload_is_lightweight tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_resolves_flat_cached_read_model_before_live_detail tests.test_workbench_oa_attachment_source_link_resolver -v`

## Final Production Evidence

第二轮生产复测仍返回 `workbench_row_not_found`，row id 仍为 `oa-exp-69fab21659b12d7d42a50a45`。进一步检查确认：

- 用户选中的是 canonical OA `oa-exp-2156`。
- 生产 active relation `CASE-AUTO-0025` 保存了历史 raw OA source id `oa-exp-69fab21659b12d7d42a50a45`。
- `_expand_confirm_link_row_ids_for_existing_context(...)` 在读取 existing source groups 前，先从 active relation 中把全部 `row_ids` 补回 action row ids，导致 raw source id 绕过了 source group alias 判断并进入 row-detail/写入链路。

## Final Fix

- active relation expansion 也必须遵守 confirm-link action I/O：输出只能是 canonical Workbench row id。
- 对选中的 canonical OA 先建立 source alias 集合；active relation 中命中这些 aliases 的历史 raw OA source id 被视为已由选中 OA 覆盖，不再扩进 action row ids。
- 当 active relation 存在且 cached read model payload 过轻时，允许通过 row-detail 边界补齐选中 OA 的 alias；无 active relation 的普通 preview 不触发额外 row-detail I/O，避免破坏轻量 read model 路径。

## Final Production Verification

- 部署 release：`main-a27446ac-20260704001651`。
- API preview：选中 `oa-exp-2156`、`txn_imported_0405`、`oa-att-inv-oa-exp-69fab21659b12d7d42a50a45:item:0:fb2a9c9fab23-b515bf77d490fdfe` 返回 HTTP 200，`can_submit=true`。
- 浏览器复测：重新选中三条记录后点击选择区 `确认关联`，预览页正常打开，显示 `金额一致`，无 `操作失败`，无 raw id 暴露；点击预览页底部 `确认关联` 后弹窗关闭，未出现失败弹窗。
- row-detail 复核：三条记录均为 `case_id=CASE-AUTO-0025`、`relation_mode=manual_confirmed`；银行流水发票关系为 `完全关联`。
