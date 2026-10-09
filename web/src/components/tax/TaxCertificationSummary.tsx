import { FinanceStatusTag } from "../common/FinanceTable";
import { formatTaxMoney } from "../../features/tax/format";
import type { TaxCertificationResult } from "../../features/tax/types";

function Money({ label, value, missing, effective = false }: { label: string; value: string | null; missing: number; effective?: boolean }) {
  return <span className={`tax-certification-metric${effective ? " tax-certification-metric--effective" : ""}`}>
    <span>{label}</span><strong title={value ?? undefined}>{formatTaxMoney(value)}</strong>
    {missing > 0 ? <small>缺失 {missing}</small> : null}
  </span>;
}
export default function TaxCertificationSummary({ summary }: { summary: TaxCertificationResult["summary"] | null }) {
  return <div className="tax-certification-summary" aria-label="当前筛选专票认证统计">
    {(["certified", "uncertified"] as const).map(status => {
      const totals = summary?.[status]; const certified = status === "certified";
      return <div key={status} className="tax-certification-summary-group" aria-label={certified ? "已认证统计" : "未认证统计"}>
        <div className="tax-certification-summary-identity"><FinanceStatusTag tone={certified ? "success" : "neutral"}>{certified ? "已认证" : "未认证"}</FinanceStatusTag>
          <span>{totals ? `${totals.count} 张` : "—"}</span></div>
        <div className="tax-certification-metrics">
          <Money label="金额" value={totals?.amount ?? null} missing={totals?.missing_amount_count ?? 0} />
          <Money label="原票税额" value={totals?.tax_amount ?? null} missing={totals?.missing_tax_count ?? 0} />
          {certified ? <Money label="有效抵扣税额" value={summary?.certified.deductible_tax_amount ?? null} missing={summary?.certified.missing_deductible_tax_count ?? 0} effective /> : null}
        </div>
      </div>;
    })}
  </div>;
}
