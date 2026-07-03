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
- `oa_attachment_source_ids(...)` 未把 `source_workbench_row_id` 纳入匹配字段，导致 OA 附件发票无法用 canonical Workbench OA id 证明“已经选中对应 OA”。

## Follow-up Fix

- `oa_attachment_source_ids(...)` 和 `WorkbenchOaAttachmentSourceLinkResolver.source_oa_id_for_attachment_link(...)` 把 `source_workbench_row_id` 作为 canonical OA 回连字段。
- `_confirm_link_context_row_ids_to_preserve(...)` 从全部 selected row_ids 识别 canonical OA，并在已选 canonical OA 能覆盖选中的 OA 附件发票时，不再把同一发票的原始 source OA id 补进 action row_ids。
- `confirm_link_preview` route 将 `KeyError(row_id)` 映射为 `workbench_row_not_found`，避免内部 row id 字符串直接污染前端错误文案。

## Follow-up Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_oa_attachment_source_link_resolver.WorkbenchOaAttachmentSourceLinkResolverTests.test_source_oa_id_for_attachment_link_matches_canonical_workbench_oa_id tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_does_not_expand_raw_oa_source_when_canonical_oa_is_selected tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_maps_missing_row_to_row_not_found_error -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_existing_oa_attachment_context_rows tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_existing_oa_attachment_context_when_bank_and_invoice_selected tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_expands_oa_attachment_context_from_all_scope_read_model_when_month_filter_hides_invoice tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_active_relation_rows_for_selected_oa_context tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_row_detail_boundary_when_read_model_payload_is_lightweight tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_resolves_flat_cached_read_model_before_live_detail tests.test_workbench_oa_attachment_source_link_resolver -v`
