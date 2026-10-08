import { formatMoney } from "../../features/money";
import type { TaxCertificationResult, TaxCertificationStatus } from "../../features/tax/types";

function Money({ label, value, missing }: { label: string; value: string | null; missing: number }) {
  return <span className="tax-certification-metric"><span>{label}</span><strong>{formatMoney(value, "—")}</strong>{missing > 0 ? <small>缺失 {missing}</small> : null}</span>;
}
export default function TaxCertificationSummary({ summary, status }: { summary: TaxCertificationResult["summary"]; status: TaxCertificationStatus }) {
  return <div className="tax-certification-summary" aria-label="专票认证统计">
    {status !== "uncertified" ? <div className="tax-certification-summary-row" aria-label="已认证统计"><strong>已认证</strong><span>{summary.certified.count} 张</span>
      <Money label="金额" value={summary.certified.amount} missing={summary.certified.missing_amount_count} />
      <Money label="税额" value={summary.certified.tax_amount} missing={summary.certified.missing_tax_count} />
      <Money label="有效抵扣税额" value={summary.certified.deductible_tax_amount} missing={summary.certified.missing_deductible_tax_count} /></div> : null}
    {status !== "certified" ? <div className="tax-certification-summary-row" aria-label="未认证统计"><strong>未认证</strong><span>{summary.uncertified.count} 张</span>
      <Money label="金额" value={summary.uncertified.amount} missing={summary.uncertified.missing_amount_count} />
      <Money label="税额" value={summary.uncertified.tax_amount} missing={summary.uncertified.missing_tax_count} /></div> : null}
  </div>;
}
