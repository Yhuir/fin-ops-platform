export type BatchAccountingHistoryRow = {
  relation_id: string;
  trade_time: string;
  bank_accounts: { bank_name: string; account_last4: string }[];
  counterparty_names: string[];
  bank_amount: string | null;
  bank_count: number;
  oa_count: number;
};

export type BatchAccountingHistoryResponse = {
  summary: { relation_count: number; transaction_count: number; bank_year: string | null };
  rows: BatchAccountingHistoryRow[];
  pagination: { page: number; page_size: number; total: number };
  available_years: string[];
};

export type BatchAccountingInvoiceRow = {
  id: string; invoice_no: string; invoice_code: string; digital_invoice_no: string;
  issue_date: string; seller_name: string; buyer_name: string;
  amount: string | null; total_with_tax: string | null;
  etc_invoice_detail_rows?: BatchAccountingInvoiceRow[];
};

export type BatchAccountingHistoryDetail = {
  relation_id: string;
  note: string;
  bank_rows: { id: string; trade_time: string; counterparty_name: string; bank_name: string; account_last4: string; amount: string | null; signed_amount: string | null; direction: string }[];
  oa_rows: { id: string; applicant: string; apply_time: string; project_name: string; amount: string | null; reason: string; apply_type: string; expense_type: string }[];
  invoice_rows: BatchAccountingInvoiceRow[];
  bank_amount: string | null;
  oa_amount: string | null;
  amount_delta: string | null;
  missing_member_ids: string[];
};
