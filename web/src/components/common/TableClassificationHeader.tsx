import type { CSSProperties } from "react";
import CountLabel from "./CountLabel";
import "./tableClassificationHeader.css";

export type ClassificationCell = {
  id: string;
  label: string;
  count?: number;
  selected?: boolean | "mixed";
  onSelect?: () => void;
};
export type ClassificationGroup = ClassificationCell & {
  tone: "blue" | "green" | "purple" | "rose";
  children: ClassificationCell[];
};

/** Fixed three-level presentation. Query semantics and counts belong to each page. */
export default function TableClassificationHeader({ label, unit, root, groups, pending, invalid }: {
  label: string;
  unit: "笔" | "条" | "张";
  root: ClassificationCell;
  groups: ClassificationGroup[];
  pending: boolean;
  invalid: boolean;
}) {
  function cell(item: ClassificationCell, level: string) {
    const content = <><span>{item.label}</span><CountLabel value={invalid ? undefined : item.count} unit={unit} spaced /></>;
    const className = `table-classification__cell table-classification__${level}`;
    return item.onSelect
      ? <button key={item.id} type="button" className={className} data-classification-id={item.id}
          aria-pressed={item.selected ?? false} onClick={item.onSelect}>{content}</button>
      : <div key={item.id} className={className} data-classification-id={item.id}>{content}</div>;
  }
  return <section className="table-classification" aria-label={label} aria-busy={pending && !invalid} data-count-pending={pending && !invalid ? "true" : "false"}>
    {cell(root, "root")}
    <div className="table-classification__groups">
      {groups.map(group => <div key={group.id} role="group" aria-label={group.label}
        className={`table-classification__group table-classification__group--${group.tone}`}
        style={{ "--classification-columns": group.children.length } as CSSProperties}>
        {cell(group, "parent")}
        <div className="table-classification__children">{group.children.map(child => cell(child, "leaf"))}</div>
      </div>)}
    </div>
  </section>;
}
