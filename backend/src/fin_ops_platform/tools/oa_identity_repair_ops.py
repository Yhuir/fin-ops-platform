from __future__ import annotations

import argparse
import json

from fin_ops_platform.services.oa_identity_repair import build_identity_relation_repair, formal_repair_plans
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_identity_repair import PostgresOAIdentityRepairRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Restore exact OA relations removed by historical source identity changes.')
    parser.add_argument('--case-id', action='append', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-fingerprint')
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--operator-id')
    parser.add_argument('--reason')
    args = parser.parse_args(argv)
    if args.execute and not all((args.expected_fingerprint, args.expected_count, args.operator_id, args.reason)):
        parser.error('execute requires fingerprint, exact count, operator and reason')
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        with connection.transaction() as transaction:
            preview = build_identity_relation_repair(
                PostgresOAIdentityRepairRepository(transaction).load_evidence(args.case_id), args.case_id,
            )
            if args.execute:
                if preview['fingerprint'] != args.expected_fingerprint or preview['count'] != args.expected_count:
                    raise ValueError('oa_identity_repair_preview_changed')
                plans, metadata = formal_repair_plans(preview)
                for item in metadata.values():
                    item['oa_identity_repair_reason'] = args.reason
                result = WorkbenchRelationCommandService(
                    relation_repository=PostgresWorkbenchRelationRepository(transaction),
                ).confirm_formal_relation_plans(plans, actor_id=args.operator_id,
                                               paired_requirements_by_case_id=metadata)
                if len(result['changed_case_ids']) != preview['count']:
                    raise ValueError('oa_identity_repair_count_mismatch')
            print(json.dumps({'mode': 'execute' if args.execute else 'dry_run',
                              'fingerprint': preview['fingerprint'], 'count': preview['count'],
                              'repairs': [{'case_id': item['case_id'], 'replacements': item['replacements'],
                                           'member_count': len(item['members'])} for item in preview['plans']]},
                             ensure_ascii=False, sort_keys=True))
    finally:
        connection.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
