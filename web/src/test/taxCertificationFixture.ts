import type { TaxCertificationRow, TaxCertificationResult } from "../features/tax/types";

export function taxCertificationFixture(params = new URLSearchParams(), options: { certified?: boolean; importedInvoice?: boolean; importedEtc?: boolean; large?: boolean } = {}): TaxCertificationResult {
  const row = (id: string, invoiceNo: string, seller: string, tax: string, date = "2026-03-22"): TaxCertificationRow => ({
    id, digital_invoice_no: invoiceNo, invoice_no: invoiceNo, invoice_code: null, seller_name: seller, seller_tax_no: "91530100TEST001",
    issue_date: date, amount: "96000.00", tax_amount: tax, certification_status: "uncertified", selection_time: null, deductible_tax_amount: null, tax_period: null,
  });
  let rows = [row("ti-202603-001", "11203490", "设备供应商", "12480.00"), row("ti-202603-002", "11203491", "材料供应商", "5760.00", "2026-03-26")];
  if (options.certified) {
    rows[0] = { ...rows[0], certification_status: "certified", selection_time: "2026-03-31 10:00:00", deductible_tax_amount: "12480.00", tax_period: "2026-03" };
    rows.push({ ...row("tc-002", "ETC-202603-7788", "高速通行服务商", "1600.00"), certification_status: "certified", selection_time: "2026-03-31 11:00:00", deductible_tax_amount: "1600.00", tax_period: "2026-03" });
  }
  if (options.importedInvoice) rows.push(row("imported-invoice", "SD-INV-IMPORT-E2E-001", "发票导入进项供应商", "1038.87", "2026-05-21"));
  if (options.importedEtc) rows.push(row("imported-etc", "ETC-2026-005", "ETC导入通行服务商", "0.73", "2026-03-27"));
  if (options.large) rows.push(...Array.from({ length: 90 }, (_, index) => row(`large-${index}`, `11299${index.toString().padStart(5, "0")}`, `进项供应商-${index}`, "360.00", `2026-03-${String(index % 28 + 1).padStart(2, "0")}`)));
  const status = params.get("status") ?? "all"; const search = params.get("search") ?? "";
  rows = rows.filter(item => (status === "all" || item.certification_status === status)
    && (!params.get("issue_year") || item.issue_date?.startsWith(params.get("issue_year")! + "-"))
    && (!params.get("selection_year") || item.selection_time?.startsWith(params.get("selection_year")! + "-"))
    && (!params.get("issue_month") || item.issue_date?.startsWith(params.get("issue_month")!))
    && (!params.get("selection_month") || item.selection_time?.startsWith(params.get("selection_month")!))
    && (!search || `${item.digital_invoice_no} ${item.seller_name} ${item.seller_tax_no}`.includes(search)));
  const totals = (status: string) => { const group = rows.filter(row => row.certification_status === status); return {
    count: group.length, amount: group.reduce((sum, item) => sum + Number(item.amount), 0).toFixed(2), tax_amount: group.reduce((sum, item) => sum + Number(item.tax_amount), 0).toFixed(2), missing_amount_count: 0, missing_tax_count: 0,
  }; };
  const sort = params.get("sort_by") === "selection_time" ? "selection_time" : "issue_date";
  rows.sort((a, b) => ((a[sort] ?? "").localeCompare(b[sort] ?? "") || a.id.localeCompare(b.id)) * (params.get("sort_direction") === "asc" ? 1 : -1));
  const page = Number(params.get("page") ?? 1); const pageSize = Number(params.get("page_size") ?? 50);
  return { rows: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length, page, page_size: pageSize,
    summary: { certified: { ...totals("certified"), deductible_tax_amount: rows.filter(row => row.certification_status === "certified").reduce((sum, item) => sum + Number(item.deductible_tax_amount), 0).toFixed(2), missing_deductible_tax_count: 0 }, uncertified: totals("uncertified") },
    export_fields: [["sequence", "序号"], ["selection_status", "勾选状态"], ["invoice_source", "发票来源"], ["domestic_sales_certificate_no", "转内销证明编号"], ["digital_invoice_no", "数电发票号码"], ["invoice_code", "发票代码"], ["invoice_no", "发票号码"], ["issue_date", "开票日期"], ["seller_tax_no", "销售方纳税人识别号"], ["seller_name", "销售方纳税人名称"], ["amount", "金额"], ["tax_amount", "税额"], ["deductible_tax_amount", "有效抵扣税额"], ["invoice_kind", "票种"], ["invoice_kind_label", "票种标签"], ["invoice_status", "发票状态"], ["selection_time", "勾选时间"], ["risk_level", "发票风险等级"], ["risk_status", "风险状态"], ["certification_status", "认证状态"], ["tax_period", "所属期"]].map(([key, label]) => ({ key, label, default_selected: ["sequence", "digital_invoice_no", "issue_date", "seller_tax_no", "seller_name", "amount", "tax_amount", "deductible_tax_amount"].includes(key) })), 
  };
}
