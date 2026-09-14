"""Explicit offline scope repair. Never called by API, worker, or idempotency replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_scope_repair import PostgresWorkbenchScopeRepairRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-id', action='append')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--actor')
    parser.add_argument('--reason')
    args = parser.parse_args()
    if args.rollback and not args.execute:
        parser.error('--rollback requires --execute')
    if args.execute and not (args.plan and args.actor and args.reason):
        parser.error('--execute requires --plan, --actor and --reason')
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        repository = PostgresWorkbenchScopeRepairRepository(connection)
        if args.execute:
            result = repository.apply(json.loads(args.plan.read_text()), actor=args.actor,
                reason=args.reason, rollback=args.rollback)
        else:
            with connection.transaction() as tx:
                tx.execute('set transaction isolation level repeatable read read only')
                tx.execute("set local statement_timeout = '10s'")
                result = PostgresWorkbenchScopeRepairRepository(tx).read_state(args.case_id)
        print(json.dumps(result, ensure_ascii=False, default=str))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
