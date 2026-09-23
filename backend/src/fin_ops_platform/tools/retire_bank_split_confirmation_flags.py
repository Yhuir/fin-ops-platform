"""Explicit, audited retirement of the removed split confirmation policy."""
import argparse
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator", default="")
    args = parser.parse_args()
    if args.apply and not args.operator.strip():
        parser.error("--operator is required with --apply")
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as transaction:
            transaction.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if args.apply
                                else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cases = PostgresWorkbenchRelationRepository(transaction).retire_bank_split_confirmation_flags(actor_id=args.operator, apply=args.apply)
        print(json.dumps({"applied": args.apply, "case_ids": cases, "count": len(cases)}, ensure_ascii=False))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
