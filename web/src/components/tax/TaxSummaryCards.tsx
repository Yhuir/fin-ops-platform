import type { TaxSummary } from "../../features/tax/types";
import { formatMoney } from "../../features/money";

type TaxSummaryCardsProps = {
  summary: TaxSummary;
};

export default function TaxSummaryCards({ summary }: TaxSummaryCardsProps) {
  const cards = [
    { label: "销项税额", value: summary.outputTax, tone: "default" },
    { label: "已认证结果进项税额", value: summary.certifiedInputTax, tone: "default" },
    { label: "计划进项税额", value: summary.plannedInputTax, tone: "default" },
    { label: "本月抵扣额", value: summary.deductibleTax, tone: "default" },
    {
      label: summary.resultLabel,
      value: summary.resultAmount,
      tone: summary.resultLabel === "本月应纳税额" ? "warn" : "success",
    },
  ] as const;

  return (
    <div className="stats-row tax-summary-strip">
      {cards.map((card) => (
        <section
          key={card.label}
          className={`stat-card tax-summary-card${card.tone === "warn" ? " warn" : ""}${card.tone === "success" ? " success" : ""}`}
        >
          <span>{card.label}</span>
          <strong>{formatMoney(card.value)}</strong>
        </section>
      ))}
    </div>
  );
}
