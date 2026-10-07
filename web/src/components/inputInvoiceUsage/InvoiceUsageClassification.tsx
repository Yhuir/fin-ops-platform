import CountLabel from "../common/CountLabel";
import "./invoiceUsageClassification.css";
import "../common/classificationSelection.css";

import type { InvoiceUsageClassificationData, InvoiceUsageClassificationItem } from "../../features/inputInvoiceUsage/types";
export type { InvoiceUsageClassificationData } from "../../features/inputInvoiceUsage/types";

/** Display only: classification, counts and filter selection belong to the page API. */
export default function InvoiceUsageClassification({
  data,
  selectedId,
  pending = false,
  invalid = false,
  onSelect,
}: {
  data: InvoiceUsageClassificationData;
  selectedId: string;
  pending?: boolean;
  invalid?: boolean;
  onSelect: (id: string) => void;
}) {
  const renderButton = (item: InvoiceUsageClassificationItem, className: string, selectionId = item.id) => (
    <button
      type="button"
      key={selectionId}
      className={`invoice-usage-classification__button classification-choice ${className}`}
      aria-pressed={selectedId === selectionId}
      disabled={invalid}
      onClick={() => onSelect(selectionId)}
    >
      <span className="invoice-usage-classification__label">{item.label}</span>
      <CountLabel value={invalid ? undefined : item.count} unit="张" spaced />
      <span className="classification-choice__check" aria-hidden="true">✓</span>
    </button>
  );

  return (
    <section className="invoice-usage-classification" aria-label="进项发票使用分类" aria-busy={pending && !invalid}>
      {renderButton(data.all, "invoice-usage-classification__all")}
      <div className="invoice-usage-classification__structure">
        <div className="invoice-usage-classification__used-region" role="group" aria-label={data.used.label}>
          {renderButton(data.used, "invoice-usage-classification__used")}
          <div className="invoice-usage-classification__groups">
            {data.groups.map(group => (
              <div
                key={group.id}
                role="group"
                aria-label={group.label}
                className={`invoice-usage-classification__group invoice-usage-classification__group--${group.tone}`}
              >
                {renderButton(group, "invoice-usage-classification__group-title")}
                <div className="invoice-usage-classification__children">
                  {group.children.map(child => renderButton(child, "invoice-usage-classification__child", `category:${group.id}:${child.id.slice("category:".length)}`))}
                </div>
              </div>
            ))}
          </div>
        </div>
        {renderButton(data.unused, "invoice-usage-classification__unused")}
      </div>
    </section>
  );
}
