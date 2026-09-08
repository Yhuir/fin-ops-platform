"""Opt-in cash query measurement, not a performance gate or ordinary test suite.

FIN_OPS_TEST_DATABASE_URL=<explicit disposable DB> PYTHONPATH=backend/src \
  python3 -m tests.test_cash_query_performance --rows 10000 100000 --samples 100

Only synthetic cash tables in that validated test DB are cleared. No HTTP, OA,
ordinary finance data, production database, cache, or permanent report is used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from time import perf_counter

from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cash_queries import CashQueryRepository
from fin_ops_platform.services.postgres_repositories.cash_tasks import CashTaskRepository

from tests.postgres_test_utils import assert_safe_test_database_url
from tests.test_cash_queries import CashPostgresCase


def seed(case: CashPostgresCase, rows: int) -> dict:
    case.setUp()
    tx = case.connection
    tx.execute("update cash.settings set personal_opening_date='2025-01-01',personal_counterparty='Synthetic party' where id=1")
    tx.execute("update cash.accounts set opening_date='2025-01-01'")
    accounts = [case.account["id"]] + [case.cash.create_account({
        "id": case.uid(), "name": f"Synthetic account {n}", "kind": "savings",
        "opening_date": "2025-01-01", "opening_amount": "1000.00",
    })["account"]["id"] for n in range(1, 4)]
    categories = [case.category["id"]] + [case.cash.create_category({
        "id": case.uid(), "name": f"Synthetic category {n}", "group": "turnover",
    })["category"]["id"] for n in range(1, 3)]
    tx.execute("""insert into cash.bill_labels(id,bank_name,label)
        select gen_random_uuid(),'Synthetic bank','Label '||n from generate_series(1,20)n""")
    bill_labels = [row["id"] for row in tx.fetch_all("select id from cash.bill_labels order by id")]
    tx.execute("""insert into cash.flows(id,occurred_on,kind,amount,from_account_id,to_account_id,category_id,content,source_kind,created_by_account,oa_project_id,project_name_snapshot)
        select gen_random_uuid(),date '2025-12-01'+(n%%304),
          case when n%%10=0 then 'transfer' when n%%10 in (1,2) then 'receipt' else 'payment' end,100,
          case when n%%10 not in (1,2) then (%s::uuid[])[1+n%%4] end,
          case when n%%10=0 then (%s::uuid[])[1+(n+1)%%4] when n%%10 in (1,2) then (%s::uuid[])[1+n%%4] end,
          case when n%%10<>0 then (%s::uuid[])[1+n%%3] end,
          'Synthetic load '||n,'manual','test',
          case when n%%5<>0 then 'project-'||(n%%8) end,
          case when n%%5<>0 then 'Synthetic project '||(n%%8) end
        from generate_series(1,%s)n""", (accounts, accounts, accounts, categories, rows))
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,obligation_direction,ledger_group,counterparty,content,origin_flow_id,origin_mode,bill_label_id,bill_month,oa_project_id,project_name_snapshot)
        select gen_random_uuid(),'loan',occurred_on,100,'receivable',case when n%%10=0 then 'personal' else 'company' end,
          'Synthetic party','Synthetic obligation',id,'created',case when n%%10=0 then (%s::uuid[])[1+(n/10)%%20] end,
          case when n%%10=0 then date_trunc('month',occurred_on)::date end,oa_project_id,project_name_snapshot
        from (select f.*,row_number() over(order by id) as n from cash.flows f where kind='payment') f where n<=%s""", (bill_labels, rows // 4))
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,content,origin_flow_id,origin_mode,related_obligation_id,oa_project_id,project_name_snapshot,category_id)
        select gen_random_uuid(),'expense',origin_date,100,'Synthetic expense',
          case when ledger_group<>'personal' then origin_flow_id end,case when ledger_group<>'personal' then 'created' end,id,
          case when ledger_group='personal' then 'source-project' else oa_project_id end,
          case when ledger_group='personal' then 'Synthetic source project' else project_name_snapshot end,%s
          from cash.items where type='loan'""", (case.payment_category["id"],))
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,content,ticket_provider,ticket_provided_on,ticket_description,oa_project_id,project_name_snapshot,category_id)
        select gen_random_uuid(),'ticket_source',date '2025-12-01'+(n%%304),100,'Synthetic ticket','Synthetic party',date '2025-12-01'+(n%%304),'Synthetic provided ticket',
          case when n%%5<>0 then 'project-'||(n%%8) end,case when n%%5<>0 then 'Synthetic project '||(n%%8) end
          ,%s from generate_series(1,%s)n""", (case.payment_category["id"], rows // 20))
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,source_item_id,remark)
        select gen_random_uuid(),'ticket_use',20,greatest(origin_date,date '2026-09-10'),id,'Synthetic use' from cash.items where type='ticket_source'""")
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,item_id,flow_id)
        select gen_random_uuid(),'cash_repayment',50,r.occurred_on,i.id,r.id
        from (select *,row_number() over(partition by oa_project_id order by id) as n from cash.flows where kind='receipt' and occurred_on>='2026-09-17') r
        join (select *,row_number() over(partition by oa_project_id order by id) as n from cash.items where type='loan' and origin_date<='2026-09-16') i
          on i.n=r.n and i.oa_project_id is not distinct from r.oa_project_id""")
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,item_id,source_item_id)
        select gen_random_uuid(),'non_ticket_offset',10,greatest(e.origin_date,date '2026-09-03'),i.id,e.id
        from cash.items e join cash.items i on i.id=e.related_obligation_id where e.type='expense' and i.ledger_group='personal'""")
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,content,obligation_direction,ledger_group,counterparty,ticket_source_id,oa_project_id,project_name_snapshot)
        select gen_random_uuid(),'company_receivable',i.origin_date,50,'Synthetic ticket receivable '||n,'receivable','company','Synthetic company',i.id,i.oa_project_id,i.project_name_snapshot
        from cash.items i cross join generate_series(1,2)n where i.type='ticket_source'""")
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,item_id,flow_id)
        select gen_random_uuid(),'company_collection',20,r.occurred_on,i.id,r.id
        from (select *,row_number() over(partition by oa_project_id order by id) as n from cash.flows where kind='receipt' and occurred_on>='2026-09-17') r
        join (select *,row_number() over(partition by oa_project_id order by id) as n from cash.items where type='company_receivable' and origin_date<='2026-09-16') i
          on i.n=r.n and i.oa_project_id is not distinct from r.oa_project_id""")
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,item_id,category_id,remark)
        select gen_random_uuid(),'non_ticket_offset',10,greatest(origin_date,date '2026-09-03'),id,%s,'Synthetic adjustment'
        from cash.items where type='company_receivable'""", (case.category["id"],))
    tx.execute("""insert into cash.task_templates(id,title,kind,execution_day,remind_days,effective_from_month,default_amount)
        select gen_random_uuid(),'Synthetic task '||n,case when n%%2=0 then 'receipt' else 'payment' end,5,2,'2026-01-01',100
        from generate_series(1,12)n""")
    invalid = tx.fetch_one("""select count(*) as n from cash.settlements s
        left join cash.items i on i.id=s.item_id left join cash.items source on source.id=s.source_item_id
        left join cash.flows f on f.id=s.flow_id
        where s.occurred_on<i.origin_date or s.occurred_on<source.origin_date
          or (f.id is not null and (s.occurred_on<>f.occurred_on or i.oa_project_id is distinct from f.oa_project_id))""")["n"]
    if invalid:
        raise AssertionError("Synthetic settlements must respect their source dates and project identity")
    for table in ("accounts", "categories", "bill_labels", "flows", "items", "settlements", "task_templates", "task_occurrences"):
        tx.execute("analyze cash." + table)
    dimensions = tx.fetch_one("""select count(*) as flow_count,count(distinct coalesce(from_account_id,to_account_id)) as accounts,
        count(distinct category_id) as categories,count(distinct oa_project_id) as projects,
        count(*) filter(where oa_project_id is null) as null_projects,
        count(*) filter(where category_id is null) as null_categories,
        count(*) filter(where kind='transfer') as transfers,
        count(*) filter(where occurred_on<'2026-01-01') as prior_year_flows from cash.flows""")
    dimensions.update(tx.fetch_one("""select count(*) as item_count,
        count(*) filter(where type='loan' and origin_date<'2026-01-01') as prior_year_obligations,
        count(*) filter(where type='company_receivable') as ticket_receivables,
        count(*) filter(where type='ticket_source') as ticket_sources,
        count(*) filter(where type='expense' and oa_project_id='source-project') as cross_project_expenses from cash.items"""))
    if dimensions["flow_count"] != rows or any(dimensions[key] < 1 for key in ("null_projects", "null_categories", "transfers", "prior_year_flows")) or dimensions["accounts"] != 4 or dimensions["categories"] != 3 or dimensions["projects"] != 8:
        raise AssertionError("Synthetic seed did not cover the required multi-value and cross-year dimensions")
    return {"accounts": accounts, "categories": categories, "dimensions": dimensions}


class QueryCounter:
    """Count statements for one untimed read; do not trace cash SQL or payloads."""

    def __init__(self, connection):
        self.connection = connection
        self.count = 0
        self.enabled = False

    @contextmanager
    def transaction(self):
        with self.connection.transaction() as tx:
            if not self.enabled:
                yield tx
                return
            counter = self
            class Transaction:
                def execute(self, *args):
                    counter.count += 1
                    return tx.execute(*args)
                def fetch_one(self, *args):
                    counter.count += 1
                    return tx.fetch_one(*args)
                def fetch_all(self, *args):
                    counter.count += 1
                    return tx.fetch_all(*args)
            yield Transaction()


def measure(name, call, samples, concurrency, counter):
    counter.count, counter.enabled = 0, True
    response = call()
    query_count, counter.enabled = counter.count, False
    def run(_):
        start = perf_counter()
        try:
            result = call()
            if result["pagination"]["total"] != response["pagination"]["total"] or len(result["rows"]) != len(response["rows"]):
                raise AssertionError("Read result changed during a read-only performance run")
            return (perf_counter() - start) * 1000, None
        except Exception as error:
            # Measurement records the failure, not a fake successful sample.
            # Do not print potentially sensitive database exception messages.
            return (perf_counter() - start) * 1000, type(error).__name__
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(run, range(samples)))
    times = sorted(elapsed for elapsed, error in results if error is None)
    failures = Counter(error for _, error in results if error is not None)
    def percentile(p):
        return round(times[math.ceil(len(times) * p) - 1], 2) if times else None
    return {"query": name, "scope": "service_and_postgres_including_pool_wait_not_http", "concurrency": concurrency,
            "statement_count_including_snapshot": query_count,
            "attempts": samples, "samples": len(times), "failures": dict(failures), "failure_rate": round((samples - len(times)) / samples, 4),
            "p50_ms": percentile(.50), "p95_ms": percentile(.95), "p99_ms": percentile(.99),
            "max_ms": max(times) if times else None, "slowest_5_ms": [round(value, 2) for value in times[-5:]],
            "row_count": len(response["rows"]), "total": response["pagination"]["total"],
            "payload_bytes": len(json.dumps(response, ensure_ascii=False).encode())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", nargs="+", type=int, default=[10000, 100000])
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4])
    args = parser.parse_args()
    if args.samples < 100 or any(n < 100 or n > 100000 for n in args.rows) or any(n not in {1, 4} for n in args.concurrency):
        parser.error("Use at least 100 samples, 100..100000 rows and concurrency 1 or 4.")
    database = assert_safe_test_database_url(os.environ["FIN_OPS_TEST_DATABASE_URL"])
    if not database.startswith("fin_ops_cash_test_"):
        parser.error("Cash measurement requires an explicit fin_ops_cash_test_* disposable database.")
    case = CashPostgresCase()
    case.setUpClass()
    failed = False
    try:
        for size in args.rows:
            seeded = seed(case, size)
            print(json.dumps({"synthetic_seed": seeded["dimensions"]}), flush=True)
            connection = PostgresConnection(PostgresSettings(database_url=case.dsn, pool_min_size=1, pool_max_size=2, pool_max_waiting=8, statement_timeout_ms=5000, pool_name="cash-measurement"))
            try:
                counter = QueryCounter(connection)
                query = CashQueryService(CashQueryRepository(counter), today=lambda: date(2026, 9, 30))
                tasks = CashTaskService(CashTaskRepository(counter), case.cash, today=lambda: date(2026, 9, 30))
                period = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
                full_period = {"date_from": "2025-12-01", "date_to": "2026-09-30"}
                multi_accounts = json.dumps(seeded["accounts"][:2])
                multi_categories = json.dumps(seeded["categories"][:2])
                calls = {"flows": lambda: query.list_flows(period),
                         "account_flows": lambda: query.list_flows({**period, "account_id": case.account["id"]}),
                         "multiple_accounts": lambda: query.list_flows({**period, "account_ids": multi_accounts}),
                         "multi_project_category": lambda: query.list_flows({**full_period, "project_ids": '["project-1","project-2"]', "category_ids": multi_categories}),
                         "null_project_category": lambda: query.list_flows({**full_period, "project_ids": '[null]', "category_ids": '[null]'}),
                         "transfer_two_accounts": lambda: query.list_flows({**full_period, "account_ids": multi_accounts, "kinds": '["transfer"]'}),
                         "deep_page": lambda: query.list_flows({**full_period, "page": str(max(2, size // 100)), "page_size": "50"}),
                         "cross_year": lambda: query.list_flows({"date_from": "2025-12-01", "date_to": "2026-01-31"}),
                         "historical_project_options": lambda: query.project_options(period),
                         "turnover": lambda: query.query_turnover(period),
                         "unsettled": lambda: query.query_turnover({"view": "unsettled", "date_to": "2026-09-30"}),
                         "turnover_multi_state": lambda: query.query_turnover({**full_period, "project_ids": '["project-1","project-2",null]', "states": '["open","partial"]'}),
                         "tickets": lambda: query.query_tickets(period),
                         "pending_collection": lambda: query.query_tickets({"view": "pending_collection", "date_to": "2026-09-30"}),
                         "tickets_multi_project": lambda: query.query_tickets({**full_period, "project_ids": '["project-1","project-2",null]'}),
                         "personal_matrix": lambda: query.query_personal({"year": "2026"}),
                         "personal_source_category": lambda: query.query_personal({"year": "2026", "view": "non_ticket_offsets", "source_project_id": "source-project", "category_id": case.payment_category["id"]}),
                         "items": lambda: query.list_items({}),
                         "task_overdue": lambda: tasks.list_occurrences({"overdue_as_of": "2026-09-30", "kinds": '["receipt","payment"]', "states": '["pending","partial"]'})}
                for concurrency in args.concurrency:
                    for name, call in calls.items():
                        result = measure(name, call, args.samples, concurrency, counter)
                        failed = failed or bool(result["failures"])
                        print(json.dumps({"synthetic_flow_count": size, **result}), flush=True)
            finally:
                connection.close()
    finally:
        case.tearDownClass()
    if failed:
        raise SystemExit("Cash measurement had failed samples; the measurement is incomplete.")


if __name__ == "__main__":
    main()
