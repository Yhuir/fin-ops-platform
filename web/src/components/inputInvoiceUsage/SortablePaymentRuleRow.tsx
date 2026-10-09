import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

/** Sorting belongs to this drawer; shared finance rows keep their existing behavior. */
export default function SortablePaymentRuleRow({ id, name, order, disabled, children }: {
  id: string;
  name: string;
  order: number;
  disabled: boolean;
  children: (handle: ReactNode) => ReactNode;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id, disabled });
  const style = {
    "--payment-rule-transform": CSS.Transform.toString(transform),
    "--payment-rule-transition": transition,
  } as CSSProperties;
  const handle = <button type="button" className="payment-rule-order" ref={setActivatorNodeRef}
    {...attributes} {...listeners} disabled={disabled}
    aria-label={`调整规则 ${name} 的顺序，当前第 ${order} 条`}>
    <GripVertical size={16} aria-hidden="true" /><span>{order}</span>
  </button>;
  return <tr data-key={id} ref={setNodeRef} style={style}
    className={`table__row finance-table__row payment-rule-sortable-row${isDragging ? " payment-rule-sortable-row--dragging" : ""}`}>
    {children(handle)}
  </tr>;
}
