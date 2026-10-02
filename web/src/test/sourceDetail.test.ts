import { sourceDetailSections } from '../features/sourceDetail';

const section = {title: '发票信息', document_kind: 'invoice', document_id: '123',
  invoice_navigation: {polarity: null, counterpartyName: null, totalWithTax: '0.00', invoiceDate: null, invoiceNo: '000123'},
  fields: [{label: '价税合计', value: '0.00'}]};

test('all source adapters preserve structured invoice summaries without parsing titles', () => {
  expect(sourceDetailSections([section])[0].invoice_navigation).toEqual(section.invoice_navigation);
  expect(() => sourceDetailSections([{...section, invoice_navigation: undefined}])).toThrow('发票导航摘要格式无效');
  expect(() => sourceDetailSections([{...section, invoice_navigation: {...section.invoice_navigation, totalWithTax: 0}}])).toThrow('发票导航摘要格式无效');
  expect(sourceDetailSections([{title: '申请信息', document_kind: 'oa', fields: []}])[0].invoice_navigation).toBeUndefined();
});
