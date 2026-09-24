"""Preview or atomically retire fully equivalent historical cost decisions."""
import argparse
import json

from fin_ops_platform.services.cost_statistics_automatic_migration_service import CostStatisticsAutomaticMigrationService
from fin_ops_platform.services.cost_statistics_canonical_repository import PostgresCostStatisticsCanonicalRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import PostgresCostStatisticsManualAllocationRepository
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator", default="")
    parser.add_argument("--restore-case")
    parser.add_argument("--expected-version", type=int)
    args = parser.parse_args()
    if args.apply and not args.operator.strip():
        parser.error("--operator is required with --apply")
    if args.restore_case and (not args.apply or not args.expected_version or args.expected_version < 1):
        parser.error("--restore-case requires --apply and a positive --expected-version")
    if args.expected_version is not None and not args.restore_case:
        parser.error("--expected-version requires --restore-case")
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as transaction:
            transaction.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if args.apply
                                else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            service = CostStatisticsAutomaticMigrationService(
                canonical_repository=PostgresCostStatisticsCanonicalRepository(transaction, transaction_bound=True),
                allocation_repository=PostgresCostStatisticsManualAllocationRepository(transaction),
                audit_repository=PostgresOperationsAuditRepository(transaction))
            report = (service.restore(case_id=args.restore_case, expected_version=args.expected_version, actor_id=args.operator)
                      if args.restore_case else service.run(apply=args.apply, actor_id=args.operator))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
