from dataclasses import replace
from decimal import Decimal

from fin_ops_platform.services.etc_document_parsers import CcbCreditCardStatementParser, TicketRootClipboardTextParser
from fin_ops_platform.services.etc_reconciliation_matcher import refresh_reconciliation_matches
from fin_ops_platform.services.etc_reconciliation_models import CreditCardItem, TicketRootItem


def card(key='c', day='2026-08-01', description='贵州通智联', amount='23.50'):
    return CreditCardItem(item_id=key, task_id='task', statement_file_id='s', transaction_date=day,
        posting_date=day, card_last4='1234', description=description, currency='CNY',
        settlement_currency='CNY', amount=Decimal(amount), settlement_amount=Decimal(amount), is_etc_candidate=False)


def ticket(key='t', day='2026-08-01', amount='23.50', plate='云ADA0381'):
    return TicketRootItem(item_id=key, task_id='task', ticket_file_id='f', vehicle_plate=plate,
        transaction_at=day+' 12:00:00', amount=Decimal(amount), entry_station='', exit_station='',
        invoice_count=1, source_page=1, extraction_method='clipboard_text')


def test_ocr_merchant_is_reclassified_and_matched():
    cards, trips = refresh_reconciliation_matches(credit_card_items=[card()], ticket_root_items=[ticket()])
    assert cards[0].is_etc_candidate
    assert trips[0].linked_credit_card_item_ids == ['c']


def test_no_amount_only_unbounded_or_identity_conflicting_matches():
    for c, t in [(card(), ticket(day='2026-08-22')), (card(description='20260801高速通行费'), ticket(day='2026-08-02')),
                 (card(description='云A12345高速'), ticket()), (replace(card(), settlement_currency='USD'), ticket())]:
        cards, trips = refresh_reconciliation_matches(credit_card_items=[c], ticket_root_items=[t])
        assert not trips[0].linked_credit_card_item_ids
        assert cards[0].recommendation_status != 'needs_review'


def test_global_assignment_and_removed_rejected_edges():
    cards = [card('a'), card('b', day='2026-08-02', description='未知商户')]
    _, trips = refresh_reconciliation_matches(credit_card_items=cards, ticket_root_items=[ticket('x', day='2026-08-02'), ticket('y')])
    assert {t.item_id: t.linked_credit_card_item_ids for t in trips} == {'x': ['b'], 'y': ['a']}
    _, trips = refresh_reconciliation_matches(credit_card_items=[replace(card(), rejected_ticket_ids=['t'])], ticket_root_items=[ticket()])
    assert trips[0].linked_credit_card_item_ids == []
    _, trips = refresh_reconciliation_matches(credit_card_items=[card()], ticket_root_items=[replace(ticket(), removed=True, linked_credit_card_item_ids=['c'])])
    assert trips[0].linked_credit_card_item_ids == []


def test_dense_groups_preserve_all_trades_and_are_deterministic():
    for count in (16,17,40):
        cards = [card(str(i)) for i in range(count)]
        trips = [ticket(str(i)) for i in range(count)]
        first = refresh_reconciliation_matches(credit_card_items=cards, ticket_root_items=trips)
        second = refresh_reconciliation_matches(credit_card_items=list(reversed(cards)), ticket_root_items=list(reversed(trips)))
        mapping = lambda rows: {t.item_id: t.linked_credit_card_item_ids for t in rows}
        assert all(len(t.linked_credit_card_item_ids) == 1 for t in first[1])
        assert mapping(first[1]) == mapping(second[1])


def test_statement_bad_rows_are_visible_and_second_currency_is_preserved():
    result = CcbCreditCardStatementParser().parse_text(file_id='f', text='\n'.join([
        '2026-08-01 2026-08-02 1234 高速 CNY 23.50 USD 23.50',
        '2026-08-02 2026-08-03 1234 高速 CNY broken 23.50',
        '2026-02-30 2026-03-01 1234 高速 CNY 23.50 23.50']))
    assert len(result.credit_card_items) == 1
    assert result.credit_card_items[0].settlement_currency == 'USD'
    assert len(result.issues) == 2


def test_multiple_plate_sections_keep_their_own_identity():
    text = '\n'.join(f'车牌号 {plate}\n交易时间 2026-08-01 12:00:00\n交易金额 23.50\n发票数量 1' for plate in ['云A12345', '云A67890'])
    result = TicketRootClipboardTextParser().parse_text(file_id='f', text=text)
    assert not result.issues
    assert [t.vehicle_plate for t in result.ticket_root_items] == ['云A12345','云A67890']


def test_manual_unlink_survives_refresh_restart_and_duplicate_source_removal(tmp_path):
    from fin_ops_platform.services.etc_reconciliation_models import FileParseResult
    from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService

    service = EtcReconciliationTaskService(data_dir=tmp_path)
    task = service.create_task(title='test', created_by='test')
    source = FileParseResult(file_id='one', parser_code='ticket_root_clipboard_text_v1',
                             credit_card_items=[card()], ticket_root_items=[ticket()])
    task = service.apply_parse_result(task_id=task.task_id, parse_result=source, actor='test')
    task = service.apply_parse_result(task_id=task.task_id, actor='test', parse_result=FileParseResult(
        file_id='two', parser_code='ticket_root_clipboard_text_v1', ticket_root_items=[replace(ticket('copy'), ticket_file_id='two')]))
    task = service.patch_item(task_id=task.task_id, item_id='c', expected_version=task.version, actor='test',
                              payload={'action':'unlink_ticket','ticketItemId':'t'})
    before = (task.version, len(task.audit_events))
    task = service.refresh_matches(task_id=task.task_id, expected_version=task.version, actor='test')
    assert (task.version, len(task.audit_events)) == before
    service = EtcReconciliationTaskService(data_dir=tmp_path)
    task = service.refresh_matches(task_id=task.task_id)
    assert task.credit_card_items[0].rejected_ticket_ids == ['t']
    assert not task.ticket_root_items[0].linked_credit_card_item_ids
    task = service.patch_item(task_id=task.task_id, item_id='c', expected_version=task.version, actor='test', payload={'action':'restore_auto'})
    assert task.ticket_root_items[0].linked_credit_card_item_ids == ['c']


def test_reparse_preserves_manual_decisions_and_rejects_stale_version(tmp_path):
    import pytest
    from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind, FileParseResult
    from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
    from fin_ops_platform.services.etc_reconciliation_source_upload_service import EtcReconciliationSourceUploadService, EtcReconciliationSourceUpload

    service = EtcReconciliationTaskService(data_dir=tmp_path)
    task = service.create_task(title='test', created_by='test')
    task = service.apply_parse_result(task_id=task.task_id, actor='test', parse_result=FileParseResult(file_id='card', parser_code='test', credit_card_items=[card()]))
    upload = EtcReconciliationSourceUploadService(task_service=service)
    text = '票根网\n按行程查看\n车牌号 云ADA0381\n交易时间 2026-08-01 12:00:00\n交易金额 23.50\n发票数量 1'
    task = upload.upload_sources(task_id=task.task_id, expected_version=task.version, actor='test', source_kind=SourceFileKind.TICKET_ROOT,
        uploads=[EtcReconciliationSourceUpload(file_name='trips.txt', content=text.encode())])
    trip_id, source_id = task.ticket_root_items[0].item_id, task.source_files[0].file_id
    task = service.patch_item(task_id=task.task_id,item_id='c',expected_version=task.version,actor='test',payload={'action':'link_ticket','ticketItemId':trip_id})
    prior_version = task.version
    task = upload.reparse_source(task_id=task.task_id,file_id=source_id,expected_version=task.version,actor='test')
    assert task.ticket_root_items[0].item_id == trip_id
    assert task.credit_card_items[0].manual_resolution == 'included_etc'
    with pytest.raises(ValueError, match='task_version_conflict'):
        upload.reparse_source(task_id=task.task_id,file_id=source_id,expected_version=prior_version,actor='test')


def test_mixed_pdf_keeps_rows_from_both_pages_and_page_locations():
    from fin_ops_platform.services.untrusted_document_policy import ValidatedDocument
    row = '2026-08-01 2026-08-02 1234 高速 CNY 23.50 23.50'
    parser = CcbCreditCardStatementParser(pdf_text_extractor=lambda _: row+'\f', ocr_text_extractor=lambda _: ['',row])
    result = parser.parse_pdf_bytes(file_id='mixed',document=ValidatedDocument(file_name='mixed.pdf', kind='pdf', content=b'',
        content_type='application/pdf', content_sha256='test', pdf_page_count=2))
    assert [c.source_page for c in result.credit_card_items] == [1,2]
    assert len({c.item_id for c in result.credit_card_items}) == 2


def test_explicit_stations_and_labeled_passage_date_constrain_matching():
    _, trips = refresh_reconciliation_matches(credit_card_items=[card(description='高速 入口站：东站 出口站：西站')],
        ticket_root_items=[replace(ticket(), entry_station='南站',exit_station='北站')])
    assert trips[0].linked_credit_card_item_ids == []
    _, trips = refresh_reconciliation_matches(credit_card_items=[card(description='通行日期：2026-07-31 高速')],ticket_root_items=[ticket(day='2026-07-31')])
    assert trips[0].linked_credit_card_item_ids == ['c']


def test_explicit_statement_total_difference_is_visible_without_invented_rows():
    result = CcbCreditCardStatementParser().parse_text(file_id='s',text='支出合计 CNY 30.00\n2026-08-01 2026-08-01 1234 高速 CNY 23.50 23.50')
    assert len(result.credit_card_items) == 1
    assert result.issues[0].field_name == 'statement_total'
    assert result.ok


def test_pdf_total_is_checked_across_pages_including_summary_page():
    from fin_ops_platform.services.untrusted_document_policy import ValidatedDocument
    row = '2026-08-01 2026-08-02 1234 高速 CNY 23.50 23.50'
    document = ValidatedDocument(file_name='mixed.pdf', kind='pdf', content=b'',
        content_type='application/pdf', content_sha256='test', pdf_page_count=3)
    for total, warnings in [('47.00', 0), ('48.00', 1)]:
        parser = CcbCreditCardStatementParser(pdf_text_extractor=lambda _, total=total: row+'\f'+row+'\f支出合计 CNY '+total)
        result = parser.parse_pdf_bytes(file_id='mixed', document=document)
        assert len(result.credit_card_items) == 2
        assert len([i for i in result.issues if i.field_name == 'statement_total']) == warnings


def test_duplicate_ticket_representative_removal_preserves_rejection(tmp_path):
    from fin_ops_platform.services.etc_reconciliation_models import FileParseResult
    from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
    service = EtcReconciliationTaskService(data_dir=tmp_path)
    task = service.create_task(title='test', created_by='test')
    for result in [FileParseResult(file_id='s', parser_code='test', credit_card_items=[card()]),
        FileParseResult(file_id='one', parser_code='ticket_root_clipboard_text_v1', ticket_root_items=[replace(ticket(),ticket_file_id='one')]),
        FileParseResult(file_id='two', parser_code='ticket_root_clipboard_text_v1', ticket_root_items=[replace(ticket('copy'), ticket_file_id='two')])]:
        task = service.apply_parse_result(task_id=task.task_id, parse_result=result, actor='test')
    task = service.patch_item(task_id=task.task_id, item_id='c', expected_version=task.version, actor='test', payload={'action':'unlink_ticket','ticketItemId':'t'})
    task = service.delete_source_file(task_id=task.task_id,file_id='one',expected_version=task.version,actor='test')
    assert len(task.ticket_root_items) == 1
    assert task.ticket_root_items[0].ticket_file_id == 'two'
    assert task.ticket_root_items[0].item_id == 't'
    assert task.credit_card_items[0].rejected_ticket_ids == ['t']
    assert task.ticket_root_items[0].linked_credit_card_item_ids == []
