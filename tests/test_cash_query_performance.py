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
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from time import perf_counter

from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cash_queries import CashQueryRepository
from fin_ops_platform.services.postgres_repositories.cash_tasks import CashTaskRepository

from tests.test_cash_queries import CashPostgresCase


def seed(case: CashPostgresCase, rows: int) -> None:
    case.setUp()
    tx = case.connection
    tx.execute("update cash.settings set personal_opening_date='2026-01-01' where id=1")
    tx.execute("""insert into cash.bill_labels(id,bank_name,label)
        select gen_random_uuid(),'Synthetic bank','Label '||n from generate_series(1,20)n""")
    tx.execute("""insert into cash.flows(id,occurred_on,kind,amount,from_account_id,to_account_id,category_id,content,source_kind,created_by_account)
        select gen_random_uuid(),date '2026-09-01'+(n%%20),case when n%%4=0 then 'receipt' else 'payment' end,
          100,case when n%%4<>0 then %s::uuid end,case when n%%4=0 then %s::uuid end,%s,
          'Synthetic load '||n,'manual','test' from generate_series(1,%s)n""", (case.account["id"], case.account["id"], case.category["id"], rows))
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,obligation_direction,ledger_group,counterparty,content,origin_flow_id,origin_mode,bill_label_id,bill_month)
        select gen_random_uuid(),'loan',occurred_on,100,'receivable',case when n%%10=0 then 'personal' else 'company' end,
          'Synthetic party','Synthetic obligation',id,'created',case when n%%10=0 then (select id from cash.bill_labels order by id limit 1) end,
          case when n%%10=0 then date '2026-10-01' end
        from (select f.*,row_number() over(order by id) as n from cash.flows f where kind='payment') f where n<=%s""", (rows // 4,))
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,content,origin_flow_id,origin_mode,related_obligation_id)
        select gen_random_uuid(),'expense',origin_date,100,'Synthetic expense',origin_flow_id,'created',id from cash.items where type='loan'""")
    tx.execute("""insert into cash.items(id,type,origin_date,original_amount,content,ticket_provider,ticket_provided_on,ticket_description)
        select gen_random_uuid(),'ticket_source',date '2026-09-01',100,'Synthetic ticket','Synthetic provider',date '2026-09-01','Synthetic provided ticket'
        from generate_series(1,%s)n""", (rows // 20,))
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,source_item_id,remark)
        select gen_random_uuid(),'ticket_use',20,date '2026-09-10',id,'Synthetic use' from cash.items where type='ticket_source'""")
    tx.execute("""insert into cash.settlements(id,kind,amount,occurred_on,item_id,flow_id)
        select gen_random_uuid(),'cash_repayment',50,r.occurred_on,i.id,r.id
        from (select *,row_number() over(order by id) as n from cash.flows where kind='receipt' and occurred_on>='2026-09-17') r
        join (select *,row_number() over(order by id) as n from cash.items where type='loan' and origin_date<='2026-09-16') i on i.n=r.n""")
    tx.execute("""insert into cash.task_templates(id,title,kind,execution_day,remind_days,effective_from_month,default_amount)
        select gen_random_uuid(),'Synthetic task '||n,case when n%%2=0 then 'receipt' else 'payment' end,5,2,'2026-01-01',100
        from generate_series(1,12)n""")
    for table in ("accounts", "categories", "bill_labels", "flows", "items", "settlements", "task_templates", "task_occurrences"):
        tx.execute("analyze cash." + table)


def measure(name, call, samples, concurrency):
    response = call()
    times = []
    def run(_):
        start = perf_counter()
        result = call()
        elapsed = (perf_counter() - start) * 1000
        if result["pagination"]["total"] != response["pagination"]["total"]:
            raise AssertionError("Read result changed during a read-only performance run.")
        return elapsed
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        times = sorted(pool.map(run, range(samples)))
    return {"query": name, "concurrency": concurrency, "samples": samples,
            "p50_ms": round(times[math.ceil(samples * .50) - 1], 2),
            "p95_ms": round(times[math.ceil(samples * .95) - 1], 2),
            "p99_ms": round(times[math.ceil(samples * .99) - 1], 2),
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
    case = CashPostgresCase()
    case.setUpClass()
    try:
        for size in args.rows:
            seed(case, size)
            connection = PostgresConnection(PostgresSettings(database_url=case.dsn, pool_min_size=1, pool_max_size=2, pool_max_waiting=8, statement_timeout_ms=5000, pool_name="cash-measurement"))
            try:
                query = CashQueryService(CashQueryRepository(connection))
                tasks = CashTaskService(CashTaskRepository(connection), case.cash, today=lambda: date(2026, 9, 30))
                period = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
                calls = {"flows": lambda: query.list_flows(period),
                         "account_flows": lambda: query.list_flows({**period, "account_id": case.account["id"]}),
                         "turnover": lambda: query.query_turnover(period),
                         "tickets": lambda: query.query_tickets(period),
                         "personal_matrix": lambda: query.query_personal({"year": "2026"}),
                         "items": lambda: query.list_items({}),
                         "task_overdue": lambda: tasks.list_occurrences({"overdue_as_of": "2026-09-30"})}
                for concurrency in args.concurrency:
                    for name, call in calls.items():
                        print(json.dumps({"synthetic_flow_count": size, **measure(name, call, args.samples, concurrency)}), flush=True)
            finally:
                connection.close()
    finally:
        case.tearDownClass()


if __name__ == "__main__":
    main()
