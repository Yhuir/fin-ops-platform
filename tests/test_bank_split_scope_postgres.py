import json
from decimal import Decimal

import pytest

from fin_ops_platform.services.bank_split_relation_scope import bank_split_comparison_rows
from fin_ops_platform.services.postgres_repositories.bank_split_relation_scope import bank_split_scope_ctes
from fin_ops_platform.services.postgres_repositories.workbench_page_query import PostgresWorkbenchPageQueryRepository


@pytest.fixture
def split_case():
    from tests.test_bank_split_consumers_postgres import BankSplitConsumersPostgresTests
    BankSplitConsumersPostgresTests.setUpClass()
    fixture = BankSplitConsumersPostgresTests()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()
        fixture.connection.close()


@pytest.mark.parametrize("target", ["1497.22", "1000000.00", "1001497.22", "100.00"])
def test_sql_and_domain_purpose_scopes_agree(split_case, target):
    ctes = bank_split_scope_ctes(
        bank_rows_sql="""select 'case' as group_key, id::text as bank_id, amount, txn_direction as direction,
            is_split, case when split_category_code='principal-custom' then 'external_turnover' else '' end as turnover_role
            from app.bank_transaction_units""",
        targets_sql="select 'case' as group_key, %s::numeric as target_amount",
    )
    selected = split_case.connection.fetch_all(f"with {ctes} select bank_id from scope_bank_members", (target,))
    rows = [{"id": split_case.principal, "amount": "1000000.00", "txn_direction": "outflow", "is_split": True, "turnover_role": "external_turnover"},
            {"id": split_case.interest, "amount": "1497.22", "txn_direction": "outflow", "is_split": True}]
    assert {row['bank_id'] for row in selected} == {row['id'] for row in bank_split_comparison_rows(rows, target=Decimal(target))}


def test_interest_relation_is_matched_in_sql_partition_and_hydrated_detail(split_case):
    connection = split_case.connection
    connection.execute("""insert into app.invoices
        (legacy_mongo_id,invoice_type,invoice_no,amount,signed_amount,total_with_tax,status,workbench_visibility,invoice_date,invoice_month)
        values ('invoice-interest','input','test-interest-1497',1497.22,1497.22,1497.22,'active','visible','2026-04-29','2026-04-01')""")
    connection.execute("""update app.workbench_pair_relations set row_ids=row_ids||array['invoice-interest'],
        row_types=row_types||array['invoice'], special_metadata=%s::jsonb where case_id='split-case'""",
        (json.dumps({"requires_oa": True, "requires_invoice": True, "bank_split_requires_cost_confirmation": True}),))
    query = PostgresWorkbenchPageQueryRepository(connection, tenant_id="default")
    for level in ("summary", "full"):
        page = query.get_workbench_groups_page(scope_key="all", zone="paired", page_size=1, detail_level=level)
        group = next(group for group in page['groups'] if group.get('case_id') == 'split-case')
        assert group['amount_check']['bank_total'] == '1497.22'
        assert group['amount_check']['status'] == 'matched'
        assert group['completion']['is_complete'] is True
        assert len(group['bank_rows']) == 2  # Both original purpose facts remain visible.
    unmatched = query.get_workbench_groups_page(scope_key="all", zone="unpaired", page_size=100)
    assert not any(group.get('case_id') == 'split-case' for group in unmatched['groups'])


def test_retire_flag_preserves_relation_version_members_and_rolls_back(split_case):
    from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
    c = split_case.connection
    # Store the ordinary normalized domain snapshot required by the relation owner.
    original = {"case_id": "split-case", "status": "active", "version": 3, "relation_mode": "manual_confirmed",
                "row_ids": ["oa-interest", split_case.principal, split_case.interest], "row_types": ["oa", "bank", "bank"],
                "month_scope": "2026-04", "special_metadata": {"bank_split_requires_cost_confirmation": True, "keep": "value"}}
    PostgresWorkbenchRelationRepository(c).save_workbench_pair_relation_delta({"pair_relations": {"split-case": original}}, changed_case_ids=["split-case"], emit_payment_status_reconcile=False)
    with pytest.raises(RuntimeError, match="rollback"):
        with c.transaction() as tx:
            assert PostgresWorkbenchRelationRepository(tx).retire_bank_split_confirmation_flags(actor_id="test", apply=True) == ["split-case"]
            raise RuntimeError("rollback")
    with c.transaction() as tx:
        owner = PostgresWorkbenchRelationRepository(tx)
        assert owner.retire_bank_split_confirmation_flags(actor_id="", apply=False) == ["split-case"]
        assert owner.retire_bank_split_confirmation_flags(actor_id="test", apply=True) == ["split-case"]
        current = owner.load_active_workbench_pair_relation_by_case_id("split-case")
        assert current['version'] == original['version']
        assert current['row_ids'] == original['row_ids']
        assert current['special_metadata'] == {"keep": "value"}
        assert owner.retire_bank_split_confirmation_flags(actor_id="test", apply=True) == []
