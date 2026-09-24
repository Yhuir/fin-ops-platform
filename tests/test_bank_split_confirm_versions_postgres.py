"""Confirmation must compare split revisions after locking canonical parents."""
import pytest

from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)


@pytest.fixture
def split_source():
    from tests.test_bank_split_consumers_postgres import BankSplitConsumersPostgresTests
    BankSplitConsumersPostgresTests.setUpClass()
    fixture = BankSplitConsumersPostgresTests()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()
        fixture.connection.close()


def test_locked_split_version_reader_deduplicates_parent_and_reads_current_revision(split_source):
    with split_source.connection.transaction() as tx:
        repository = PostgresWorkbenchRelationRepository(tx)
        ids = [split_source.principal, split_source.interest]
        repository.acquire_relation_member_locks(ids, row_types=["bank", "bank"])
        assert repository.lock_canonical_relation_members(ids, row_types=["bank", "bank"]) == []
        assert repository.bank_split_versions_for_members(ids) == {"bank-parent": 1}
        tx.execute("update app.bank_transaction_split_sets set version=2 where bank_transaction_id=%s::uuid", (split_source.parent,))
        assert repository.bank_split_versions_for_members(ids) == {"bank-parent": 2}


def test_stale_split_confirmation_rolls_back_without_relation_or_history_change(split_source):
    connection = split_source.connection
    owner = PostgresWorkbenchRelationRepository(connection)
    before = owner.load_workbench_pair_relations()
    connection.execute("update app.bank_transaction_split_sets set version=2 where bank_transaction_id=%s::uuid", (split_source.parent,))
    with pytest.raises(WorkbenchRelationCommandError) as caught:
        with connection.transaction() as tx:
            repository = PostgresWorkbenchRelationRepository(tx)
            ids = [split_source.principal, split_source.interest]
            # The production UoW acquires typed-member advisory locks first.
            repository.acquire_relation_member_locks(ids, row_types=["bank", "bank"])
            WorkbenchRelationCommandService(relation_repository=repository, tenant_id="default").confirm_relation(
                case_id="new-confirm", row_ids=ids, row_types=["bank", "bank"],
                relation_mode="manual_confirmed", actor_id="test", replace_existing=True,
                bank_split_versions={"bank-parent": 1},
            )
    assert caught.value.error_code == "bank_split_version_conflict"
    assert caught.value.payload["current_bank_split_versions"] == {"bank-parent": 2}
    assert owner.load_workbench_pair_relations() == before
