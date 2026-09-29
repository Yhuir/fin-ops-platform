import type { EntityDetailSection } from '../components/common/EntityDetailContent';

/** Page API adapters preserve the authoritative source projection, never rebuild it from list rows. */
export function sourceDetailSections(value: unknown): EntityDetailSection[] {
  if (!Array.isArray(value)) throw new Error('原始详情响应缺少字段表');
  return value.map(section => {
    if (!section || typeof section !== 'object' || typeof section.title !== 'string' || !Array.isArray(section.fields)) {
      throw new Error('原始详情字段表格式无效');
    }
    return {
      title: section.title,
      document_id: section.document_id,
      document_title: section.document_title,
      document_kind: section.document_kind,
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
