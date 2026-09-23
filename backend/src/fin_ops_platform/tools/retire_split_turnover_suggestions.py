from __future__ import annotations

import argparse
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.turnover_suggestion_retirement import (
    PostgresTurnoverSuggestionRetirementRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or retire system suggestions superseded by bank splits.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator", default="")
    args = parser.parse_args()
    if args.apply and not args.operator.strip():
        parser.error("--operator is required with --apply")
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as transaction:
            transaction.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if args.apply else
                                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            report = PostgresTurnoverSuggestionRetirementRepository(transaction).run(apply=args.apply, actor_id=args.operator)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
