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


@pytest.mark.parametrize("ordinary_amount", [0, 100])
@pytest.mark.parametrize("explicit_status", [False, True])
def test_full_principal_interest_payment_has_separate_invoice_requirement(split_case, ordinary_amount, explicit_status):
    c = split_case.connection
    settings = split_case.settings
    if not explicit_status:
        for definition in settings['bank_transaction_tags']['definitions']:
            definition.pop('status')
    settings['bank_flow_rule_batch_tag_rules'] = {'version': 1, 'requirements_by_tag_code': {
        'principal-custom': {'requires_oa': True, 'requires_invoice': False},
        'interest-custom': {'requires_oa': True, 'requires_invoice': True},
    }}
    c.execute("update app.app_settings set settings_payload=%s::jsonb where settings_key='app_settings'", (json.dumps(settings),))
    c.execute("""insert into app.oa_applications
        (oa_source_id,form_id,form_type,row_id,status,workflow_status,applicant,application_date,scope_month,
         project_name,amount,currency,normalized_payload,raw_payload)
        values ('oa-principal','oa-principal','支付申请','oa-principal','active','completed','测试申请人',
                '2026-04-29','2026-04-01','测试项目',1000000,'CNY',
                '{"id":"oa-principal","project_name":"测试项目","amount":"1000000.00","expense_type":"还款"}', '{}')""")
    c.execute("""insert into app.invoices
        (legacy_mongo_id,invoice_type,invoice_no,amount,signed_amount,total_with_tax,status,workbench_visibility,invoice_date,invoice_month)
        values ('invoice-interest','input','test-interest-1497',%s,%s,%s,'active','visible','2026-04-29','2026-04-01')""", (Decimal('1497.22') + ordinary_amount,) * 3)
    c.execute("""update app.workbench_pair_relations set row_ids=row_ids||array['oa-principal','invoice-interest'],
        row_types=row_types||array['oa','invoice'],special_metadata='{"requires_oa":true,"requires_invoice":true}'
        where case_id='split-case'""")
    if ordinary_amount:
        c.execute("""insert into app.bank_transactions(legacy_mongo_id,account_no,counterparty_name_raw,txn_direction,amount,signed_amount,
            txn_date,txn_month,trade_time,status,currency,raw_payload)
            values ('ordinary','111','测试对方','outflow',100,-100,'2026-04-29','2026-04-01','2026-04-29 12:00:00+08','active','CNY','{}')""")
        c.execute("update app.workbench_pair_relations set row_ids=row_ids||array['ordinary'],row_types=row_types||array['bank'] where case_id='split-case'")
        c.execute("update app.oa_applications set amount=1597.22,normalized_payload=jsonb_set(normalized_payload,'{amount}','\"1597.22\"') where row_id='oa-interest'")
    query = PostgresWorkbenchPageQueryRepository(c, tenant_id='default')
    for level in ('summary', 'full'):
        page = query.get_workbench_groups_page(scope_key='all', zone='paired', page_size=10, detail_level=level)
        group = next(g for g in page['groups'] if g.get('case_id') == 'split-case')
        assert group['amount_check']['status'] == 'matched'
        assert group['amount_check']['bank_total'] == f'{Decimal("1001497.22") + ordinary_amount:.2f}'
        assert group['amount_check']['bank_original_total'] == f'{Decimal("1001497.22") + ordinary_amount:.2f}'
        assert group['amount_check']['evidence_required_total'] == f'{Decimal("1497.22") + ordinary_amount:.2f}'
        assert group['amount_check']['invoice_total'] == f'{Decimal("1497.22") + ordinary_amount:.2f}'
        assert group['completion']['is_complete'] is True
    from fin_ops_platform.services.cost_statistics_canonical_repository import PostgresCostStatisticsCanonicalRepository
    from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
    policy = CostStatisticsPolicy(PostgresCostStatisticsCanonicalRepository(c).load_snapshot())
    if not ordinary_amount:
        assert [row['amount'] for row in policy.serialized_cost_rows] == ['1497.22']
        assert policy.manual_allocation_tasks == []
    assert c.fetch_one('select count(*) as count from app.cost_statistics_manual_allocations')['count'] == 0
    # Same facts and changed policy must immediately change both SQL partition and detail.
    settings['bank_flow_rule_batch_tag_rules']['requirements_by_tag_code']['principal-custom']['requires_invoice'] = True
    c.execute("update app.app_settings set settings_payload=%s::jsonb where settings_key='app_settings'", (json.dumps(settings),))
    page = query.get_workbench_groups_page(scope_key='all', zone='unpaired', page_size=10, detail_level='full')
    group = next(g for g in page['groups'] if g.get('case_id') == 'split-case')
    assert group['amount_check']['status'] == 'mismatch'
    assert group['workbench_anomaly']['items'][0]['code'] == 'oa_bank_equal_invoice_less'


def test_workbench_sibling_ownership_is_complete_for_partial_selection(split_case):
    from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
    c = split_case.connection
    c.execute("update app.workbench_pair_relations set row_ids=array['oa-interest',%s],row_types=array['oa','bank'] where case_id='split-case'", (split_case.interest,))
    def parts():
        projection = PostgresBankDetailsCanonicalQueryRepository.workbench_category_projection_rows(
            c, settings=split_case.settings, transaction_ids=[split_case.interest])
        return {part['id']: part['relation_case_id'] for part in projection[split_case.interest]['bank_split_parts']}
    assert parts() == {split_case.principal: None, split_case.interest: 'split-case'}
    c.execute("""insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types,month_scope)
        values ('principal-owner','manual_confirmed','active',array[%s],array['bank'],'2026-04-01')""", (split_case.principal,))
    assert parts() == {split_case.principal: 'principal-owner', split_case.interest: 'split-case'}
    c.execute("update app.workbench_pair_relations set status='cancelled' where case_id='principal-owner'")
    assert parts()[split_case.principal] is None


@pytest.mark.parametrize("invalid_rule", ["archived", "missing_rules"])
def test_unknown_split_rule_is_unpaired_without_fabricated_amount_anomaly(split_case, invalid_rule):
    c = split_case.connection
    settings = split_case.settings
    if invalid_rule == 'archived':
        settings['bank_transaction_tags']['definitions'][1]['status'] = 'archived'
    else:
        settings['bank_transaction_tags']['definitions'][1].pop('rules')
    c.execute("update app.app_settings set settings_payload=%s::jsonb", (json.dumps(settings),))
    c.execute("""insert into app.invoices
        (legacy_mongo_id,invoice_type,invoice_no,amount,signed_amount,total_with_tax,status,workbench_visibility,invoice_date,invoice_month)
        values ('invoice-interest','input','test-interest-1497',1497.22,1497.22,1497.22,'active','visible','2026-04-29','2026-04-01')""")
    c.execute("update app.workbench_pair_relations set row_ids=row_ids||array['invoice-interest'],row_types=row_types||array['invoice'] where case_id='split-case'")
    query = PostgresWorkbenchPageQueryRepository(c, tenant_id='default')
    for level in ('summary', 'full'):
        page = query.get_workbench_groups_page(scope_key='all', zone='unpaired', page_size=10, detail_level=level)
        group = next(g for g in page['groups'] if g.get('case_id') == 'split-case')
        assert group['amount_check']['status'] == 'unknown'
        assert group['completion']['is_complete'] is False
        assert not group.get('workbench_anomaly')
    page = query.get_workbench_groups_page(scope_key='all', zone='paired', page_size=10)
    assert not any(g.get('case_id') == 'split-case' for g in page['groups'])
