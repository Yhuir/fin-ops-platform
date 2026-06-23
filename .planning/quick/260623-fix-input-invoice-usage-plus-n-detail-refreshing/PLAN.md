# 260623 Fix Input Invoice Usage +N Detail Refreshing

## Symptom

- Page: `/input-invoice-usage`.
- User clicks the `+N` relation count in the invoice usage table.
- Drawer opens with title `发票关联明细`, but shows `详情暂不可用` and `进项发票使用情况关联明细正在刷新，完成后请重新打开详情。`.
- The list itself is already fresh and displays rows.

## Closed-loop Hypothesis

1. Frontend `+N` target must pass `kind=relationList`, `rowId=row.id`, and `relationKind=invoice|oa|bank`.
2. Backend `/api/input-invoice-usage/rows/{row_id}/relation-details` must read the existing `read_model.input_invoice_usage_rows` row by `row_id`.
3. Detail freshness must compare source versions using the row's `read_model_scope_key`, not an implicit all/no-scope provider call.

The frontend target is already correct. The likely defect is in `InputInvoiceUsageReadModelDetailService`: it reads `scope_key` from the row but calls `source_versions_provider()` without passing that scope. When monthly `workbench_relation_source_versions` differ from the all/common view, a fresh row can be incorrectly treated as stale and returned as refreshing.

## Acceptance Criteria

- Relation detail for a fresh monthly read model row returns `read_model_status=fresh`.
- The detail service calls source version provider with the row scope.
- Existing stale/missing detail behavior still returns refreshing and enqueues refresh.
- No live rebuild is introduced for `+N` details.

## Verification

- Add a service/API regression for scoped relation detail source version matching.
- Run focused backend tests for input invoice usage relation detail/read model.
- Run focused frontend tests for the `+N` relation detail path.

## Result

- Root cause confirmed: `InputInvoiceUsageReadModelDetailService` read the row scope but called `source_versions_provider()` without passing it.
- Fix: detail freshness now calls the provider with `scope_key=read_model_scope_key`, with fallback support for legacy no-arg providers.
- Regression: `test_relation_details_compare_source_versions_with_row_scope` locks the fresh monthly row behavior.
