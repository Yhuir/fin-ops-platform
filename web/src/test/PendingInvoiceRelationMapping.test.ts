import { expect, test } from 'vitest';
import { mapPendingInvoiceRow } from '../features/pendingInvoices/api';
import { pendingInvoiceDisplayRows, pendingInvoiceMembers } from '../features/pendingInvoices/relationExpansion';

function canonicalRow() {
  const bank = { id: 'bank-650', counterparty_name: '报销人', amount: '650.00', debit_amount: '650.00', original_amount: '650.00', relation_case_ids: ['case-six'] };
  const invoices = ['100.00', '50.00', '50.00', '100.00', '50.00', '300.00'].map((amount, index) => ({
    id: `invoice-${index}`, digital_invoice_no: `TICKET-${index}`, total_with_tax: amount, relation_case_ids: ['case-six'],
  }));
  const oa = { id: 'oa-six', applicant: '报销人', project_name: '项目', relation_case_ids: ['case-six'] };
  return {
    id: bank.id,
    bank_transaction: bank,
    bank_transactions: { primary: bank, relation_count: 1, original_transaction_count: 1, has_multiple: false, summaries: [] },
    input_invoices: { primary: invoices[0], relation_count: 6, summaries: invoices, has_multiple: true },
    oa: { primary: oa, relation_count: 1, summaries: [], has_multiple: false },
    relation_case_ids: ['case-six'],
    invoice_acquisition_status: { code: 'paid_invoiced', primary_action: 'view_relation' },
  };
}

test('keeps a compact single bank and OA on all six actual invoice rows using canonical case arrays', () => {
  const row = mapPendingInvoiceRow(canonicalRow());
  const members = pendingInvoiceMembers(row);
  expect(members.bank[0].relationCaseIds).toEqual(['case-six']);
  expect(members.invoice.every(invoice => invoice.relationCaseIds?.[0] === 'case-six')).toBe(true);
  expect(members.oa[0].relationCaseIds).toEqual(['case-six']);
  const displays = pendingInvoiceDisplayRows(row, 'invoice', members);
  expect(displays.map(display => display.invoice?.totalWithTax)).toEqual(['100.00', '50.00', '50.00', '100.00', '50.00', '300.00']);
  expect(displays.map(display => display.bank?.id)).toEqual(Array(6).fill('bank-650'));
  expect(displays.map(display => display.oa?.id)).toEqual(Array(6).fill('oa-six'));
});

test('matches multiple cases by exact membership even when member arrays have different orders', () => {
  const base = canonicalRow();
  const row = mapPendingInvoiceRow({ ...base,
    bank_transactions: { ...base.bank_transactions, relation_count: 2, original_transaction_count: 2, has_multiple: true, summaries: [
      { ...base.bank_transaction, id: 'bank-b', relation_case_ids: ['case-b'] },
      { ...base.bank_transaction, id: 'bank-a', relation_case_ids: ['case-a'] },
    ] },
    input_invoices: { ...base.input_invoices, relation_count: 3, summaries: [
      { ...base.input_invoices.summaries[0], id: 'invoice-a', relation_case_ids: ['case-a'] },
      { ...base.input_invoices.summaries[1], id: 'invoice-b', relation_case_ids: ['case-b'] },
      { ...base.input_invoices.summaries[2], id: 'unrelated', relation_case_ids: ['other-case'] },
    ] },
    oa: { ...base.oa, relation_count: 2, has_multiple: true, summaries: [
      { ...base.oa.primary, id: 'oa-b', relation_case_ids: ['case-b'] },
      { ...base.oa.primary, id: 'oa-a', relation_case_ids: ['case-a'] },
    ] },
  });
  const displays = pendingInvoiceDisplayRows(row, 'invoice', pendingInvoiceMembers(row));
  expect(displays.map(display => [display.invoice?.id, display.bank?.id ?? null, display.oa?.id ?? null])).toEqual([
    ['invoice-a', 'bank-a', 'oa-a'], ['invoice-b', 'bank-b', 'oa-b'], ['unrelated', null, null],
  ]);
});

test('merges exact case memberships for split parts without duplicating the original bank', () => {
  const base = canonicalRow();
  const row = mapPendingInvoiceRow({ ...base,
    bank_transactions: { ...base.bank_transactions, relation_count: 2, original_transaction_count: 1, has_multiple: true, summaries: [
      { ...base.bank_transaction, id: 'part-a', parent_row_id: 'original-bank', relation_case_ids: ['case-a'] },
      { ...base.bank_transaction, id: 'part-b', parent_row_id: 'original-bank', relation_case_ids: ['case-b'] },
    ] },
    input_invoices: { ...base.input_invoices, relation_count: 2, summaries: [
      { ...base.input_invoices.summaries[0], id: 'invoice-a', relation_case_ids: ['case-a'] },
      { ...base.input_invoices.summaries[1], id: 'invoice-b', relation_case_ids: ['case-b'] },
    ] },
  });
  const members = pendingInvoiceMembers(row);
  expect(members.bank).toHaveLength(1);
  expect(members.bank[0].relationIds).toEqual(['case-a', 'case-b']);
  expect(pendingInvoiceDisplayRows(row, 'invoice', members).map(display => display.bank?.id)).toEqual(['original-bank', 'original-bank']);
});
