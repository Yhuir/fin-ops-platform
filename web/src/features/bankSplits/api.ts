import { apiRequestJson } from '../apiClient';

export type BankSplitPart = {
  id: string;
  category_code: string;
  category_label: string;
  category_path: string[];
  amount: string;
};
export type BankSplitTag = {
  code: string;
  label: string;
  path: string[];
  primary_label: string;
  sub_label: string;
  status: string;
  turnover_role: string;
};
export type BankSplitDetail = {
  transaction_id: string;
  canonical_transaction_id: string;
  amount: string;
  direction: string;
  version: number;
  category_code: string | null;
  category_label_path: string[];
  turnover_third_label_options: Array<{ value: string; label: string }>;
  parts: BankSplitPart[];
  tag_definitions: BankSplitTag[];
  can_edit: boolean;
};
export type SaveBankSplits = {
  version: number;
  parts: Array<{ id?: string; category_code: string; amount: string; category_label_path: string[] }>;
  category_code?: string;
  category_label_path?: string[];
};
export async function fetchBankSplits(id: string, signal?: AbortSignal) {
  const detail = await apiRequestJson<BankSplitDetail>(`/api/bank-transactions/${encodeURIComponent(id)}/splits`, { signal }, { allowHtmlFallback: false });
  if (!Array.isArray(detail.parts) || !Array.isArray(detail.tag_definitions) || typeof detail.amount !== 'string' || typeof detail.version !== 'number' || typeof detail.can_edit !== 'boolean') throw new Error('流水拆分详情格式错误');
  return detail;
}
export function saveBankSplits(id: string, request: SaveBankSplits) {
  return apiRequestJson<BankSplitDetail & { changed: boolean; affected_months: string[] }>(
    `/api/bank-transactions/${encodeURIComponent(id)}/splits`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) },
    { allowHtmlFallback: false },
  );
}

export function mapBankSplitParts(value: unknown): BankSplitPart[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new Error('流水拆分数据格式错误');
  return value.map(part => {
    if (!part || typeof part.id !== 'string' || typeof part.category_code !== 'string'
      || typeof part.category_label !== 'string' || typeof part.amount !== 'string' || !Array.isArray(part.category_path)) {
      throw new Error('流水拆分子项格式错误');
    }
    return part as BankSplitPart;
  });
}

export async function getBankTransactionSplitsBatch(transactionIds: string[], signal?: AbortSignal) {
  const response = await apiRequestJson<{ rows: BankSplitDetail[] }>('/api/bank-transactions/splits/query', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transaction_ids: transactionIds }),
  }, { allowHtmlFallback: false });
  if (!Array.isArray(response.rows) || response.rows.length !== transactionIds.length) throw new Error('批量流水拆分详情不完整');
  return response.rows;
}
