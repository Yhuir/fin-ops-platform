import { ChevronDown, ChevronUp } from "lucide-react";

type ExpandableCellTextProps = {
  text: string;
  expanded: boolean;
  onToggle: () => void;
  title?: string;
  threshold?: number;
};

function previewLabel(text: string) {
  return text.length > 28 ? `${text.slice(0, 28)}...` : text;
}

export default function ExpandableCellText({
  text,
  expanded,
  onToggle,
  title,
  threshold = 26,
}: ExpandableCellTextProps) {
  const value = text || "-";
  const canExpand = value.length > threshold;
  return (
    <span className="input-invoice-usage-expandable-cell-text">
      <span
        className={expanded || !canExpand ? "input-invoice-usage-expandable-cell-text__value" : "input-invoice-usage-expandable-cell-text__value input-invoice-usage-expandable-cell-text__value--clamped"}
        title={title ?? value}
      >
        {value}
      </span>
      {canExpand ? (
        <button
          aria-label={`${expanded ? "收起" : "展开"} ${previewLabel(value)}`}
          className="input-invoice-usage-expandable-cell-text__button"
          onClick={onToggle}
          title={expanded ? "收起" : "展开"}
          type="button"
        >
          {expanded ? <ChevronUp aria-hidden="true" size={14} /> : <ChevronDown aria-hidden="true" size={14} />}
        </button>
      ) : null}
    </span>
  );
}
