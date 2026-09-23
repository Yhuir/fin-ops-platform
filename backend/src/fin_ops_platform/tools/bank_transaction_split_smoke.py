"""Exercise real split SQL in an always-rolled-back, test-owned transaction."""
from __future__ import annotations

import json
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
from fin_ops_platform.services.bank_transaction_split_relation_service import BankTransactionSplitRelationService
from fin_ops_platform.services.bank_transaction_split_service import validate_split_parts
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_transaction_splits import (
    PostgresBankTransactionSplitRepository,
)
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)
from fin_ops_platform.services.postgres_repositories.turnover_bank_split import PostgresTurnoverBankSplitRepository
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class _ProbeRollback(Exception):
    pass


def run(connection):
    parent = str(uuid4())
    repository = PostgresBankTransactionSplitRepository(connection)
    owner = BankTransactionSplitRelationService(
        relation_repository_factory=PostgresWorkbenchRelationRepository,
        settings_snapshot_provider=lambda tx: AppSettingsService.bank_category_relation_policy_snapshot(PostgresBankDetailsCanonicalQueryRepository.settings_payload(tx)),
        effective_category_rows=PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows,
        relation_delta_publisher=lambda *_args, **_kwargs: None,
        allocation_repository_factory=PostgresCostStatisticsManualAllocationRepository,
        batch_repository_factory=PostgresWorkbenchRepository,
        turnover_split_migrator=lambda tx, **kwargs: PostgresTurnoverBankSplitRepository(tx).apply(**kwargs),
    )
    samples = []
    try:
        with connection.transaction() as tx:
            tx.execute("SET LOCAL statement_timeout='10s'")
            tx.execute("SET LOCAL lock_timeout='3s'")
            tx.execute("""INSERT INTO app.bank_transactions(id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,currency,status)
                VALUES (%s::uuid,'SPLIT-SMOKE','outflow','SPLIT-SMOKE',1001497.22,-1001497.22,current_date,date_trunc('month',current_date),'CNY','pending')""", (parent,))
            before = repository.load(tx, parent, for_update=True)
            definitions = [d for d in before['tag_definitions'] if d['status']=='active']
            principal = next(d for d in definitions if d.get('turnover_role')=='external_turnover' and len(d['path']) >= 2 and d.get('turnover_action_type'))
            expense = next(d['code'] for d in definitions if not d.get('turnover_role'))
            for index in range(100):
                start = perf_counter()
                before = repository.load(tx, parent, for_update=True)
                parts = [{'category_code':principal['code'],'category_label_path':[*principal['path'][:2],before['turnover_third_label_options'][0]['value']],'amount':'1000000.00' if index%2==0 else '999999.99'},
                         {'category_code':expense,'amount':'1497.22' if index%2==0 else '1497.23'}]
                if before['parts']:
                    for part, prior in zip(parts,before['parts'],strict=True):
                        part['id']=prior['id']
                normalized = validate_split_parts({'parts':parts},amount=Decimal(before['amount']),current_parts=before['parts'],definitions=before['tag_definitions'])
                after = repository.persist(tx,before=before,parts=normalized,category_code=None,actor_id='split-smoke')
                owner.apply(tx,before=before,after=after,actor_id='split-smoke')
                repository.audit(tx,before=before,after=after,actor_id='split-smoke')
                read = repository.load(tx,parent,for_update=False)
                assert read['parts']==after['parts'] and read['version']==index+1
                units = tx.fetch_one("SELECT count(*) as n,sum(amount) as total FROM app.bank_transaction_units WHERE parent_bank_transaction_id=%s::uuid",(parent,))
                assert units['n']==2 and units['total']==Decimal('1001497.22')
                samples.append((perf_counter()-start)*1000)
            raise _ProbeRollback()
    except _ProbeRollback:
        pass
    assert connection.fetch_one("SELECT count(*) AS n FROM app.bank_transactions WHERE id=%s::uuid",(parent,))['n']==0
    assert connection.fetch_one("SELECT count(*) AS n FROM audit.events WHERE object_id=%s",(parent,))['n']==0
    values=sorted(samples)
    return {'status':'passed','samples':len(samples),'rollback_verified':True,
            'scope':'real repository validation/write/relations/audit/unit read inside rollback; excludes HTTP, commit and existing related case',
            'p50_ms':round(values[49],2),'p95_ms':round(values[94],2),'p99_ms':round(values[98],2),'max_ms':round(values[-1],2)}


def main():
    connection=PostgresConnection(PostgresSettings.from_env())
    try:
        print(json.dumps(run(connection),ensure_ascii=False,indent=2))
    finally:
        connection.close()


if __name__=='__main__':
    main()
