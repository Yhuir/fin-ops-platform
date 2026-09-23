from __future__ import annotations

import argparse
import json

from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
from fin_ops_platform.services.bank_split_cost_migration_service import BankSplitCostMigrationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Preview or revoke obsolete external-turnover cost allocations.')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--operator', default='')
    args = parser.parse_args()
    if args.apply and not args.operator.strip():
        parser.error('--operator is required with --apply')
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as transaction:
            transaction.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE' if args.apply else 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            service = BankSplitCostMigrationService(
                allocation_repository_factory=PostgresCostStatisticsManualAllocationRepository,
                settings_snapshot_provider=PostgresBankDetailsCanonicalQueryRepository.settings_payload,
                effective_category_rows=PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows,
            )
            report = service.run(transaction, actor_id=args.operator, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
