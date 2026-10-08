import type { EntityDetailSection } from '../components/common/EntityDetailContent';

/** Page API adapters preserve the authoritative source projection, never rebuild it from list rows. */
export function sourceDetailSections(value: unknown): EntityDetailSection[] {
  if (!Array.isArray(value)) throw new Error('原始详情响应缺少字段表');
  return value.map(section => {
    if (!section || typeof section !== 'object' || typeof section.title !== 'string' || !Array.isArray(section.fields)) {
      throw new Error('原始详情字段表格式无效');
    }
    if (section.document_kind === 'invoice') {
      const summary = section.invoice_navigation;
      if (!summary || typeof summary !== 'object' ||
        ['polarity', 'counterpartyName', 'totalWithTax', 'invoiceDate'].some(key => summary[key] !== null && typeof summary[key] !== 'string')) {
        throw new Error('发票导航摘要格式无效');
      }
    }
    if (section.document_kind === 'bank') {
      const summary = section.bank_navigation;
      if (!summary || typeof summary !== 'object' ||
        ['counterpartyName', 'amount', 'direction', 'transactionDate'].some(key => summary[key] !== null && typeof summary[key] !== 'string') ||
        (summary.labels !== null && (!Array.isArray(summary.labels) || summary.labels.some((label: unknown) => typeof label !== 'string')))) {
        throw new Error('流水导航摘要格式无效');
      }
    }
    if (section.bank_labels !== undefined && (!Array.isArray(section.bank_labels) || section.bank_labels.some((label: unknown) => typeof label !== 'string'))) {
      throw new Error('流水标签格式无效');
    }
    return {
      title: section.title,
      document_id: section.document_id,
      document_title: section.document_title,
      document_kind: section.document_kind,
      invoice_navigation: section.invoice_navigation,
      bank_navigation: section.bank_navigation,
      bank_labels: section.bank_labels,
      bank_transaction_id: section.bank_transaction_id,
      fields: section.fields.map((field: {label: unknown; value: unknown}) => {
        if (typeof field.label !== 'string' || (field.value != null && !['string', 'number', 'boolean'].includes(typeof field.value))) {
          throw new Error('原始详情字段格式无效');
        }
        return {label: field.label, value: field.value as string | number | boolean | null | undefined};
      }),
    };
  });
}
