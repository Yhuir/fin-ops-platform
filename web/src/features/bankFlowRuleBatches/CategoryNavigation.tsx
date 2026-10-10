import { ChevronRight } from "lucide-react";
import { cx, type BankFlowRuleCategoryGroup } from "./viewModel";

export default function CategoryNavigation({ groups, primaryLabel, subKey, loading, disabled, onSelect }: {
  groups: BankFlowRuleCategoryGroup[];
  primaryLabel: string;
  subKey: string | null;
  loading: boolean;
  disabled: boolean;
  onSelect: (primary: string, sub: string | null, codes: string[]) => void;
}) {
  const selected = groups.find((group) => group.label === primaryLabel);
  return <nav aria-label="流水分类" aria-busy={loading} className="bank-flow-rule-batches-categories">
    <section aria-label="主标签" className="bank-flow-rule-batches-rail">
      <h2 className="bank-flow-rule-batches-rail__title">主标签</h2>
      {groups.map((group) => <button type="button" key={group.label}
        aria-label={`${group.label} ${group.childCount} 个子标签`}
        aria-pressed={primaryLabel === group.label}
        disabled={disabled}
        className={cx("bank-flow-rule-batches-rail__item", "bank-flow-rule-batches-rail__item--primary")}
        onClick={() => onSelect(group.label, null, group.codes)}>
        <span className="bank-flow-rule-batches-rail__item-label">{group.label}</span>
        <span className="bank-flow-rule-batches-rail__item-count">{group.childCount} 个</span>
        <ChevronRight size={14} aria-hidden="true" />
      </button>)}
    </section>
    <section aria-label="子标签" className="bank-flow-rule-batches-rail">
      <h2 className="bank-flow-rule-batches-rail__title">子标签</h2>
      {selected ? selected.children.map((child) => <button type="button" key={child.key}
        aria-label={`${selected.label} / ${child.label} ${child.rowCount} 笔`}
        aria-pressed={subKey === child.key}
        disabled={disabled}
        className="bank-flow-rule-batches-rail__item"
        onClick={() => onSelect(selected.label, child.key, child.codes)}>
        <span className="bank-flow-rule-batches-rail__item-label">{child.label}</span>
        <span className="bank-flow-rule-batches-rail__item-count">{child.rowCount} 笔</span>
      </button>) : <span className="bank-flow-rule-batches-rail__empty" aria-label="未选择主标签">—</span>}
    </section>
  </nav>;
}
