import type { MouseEvent } from "react";

import type { WorkbenchRecordType } from "../../features/workbench/types";

export type WorkbenchInlineAction =
  | "confirm-cash-pass-through"
  | "confirm-cash-ticket-purchase"
  | "cancel-cash-special"
  | "enter-invoice"
  | "manage-supporting-documents"
  | "assign-invoice-expense-items";

type RowActionsProps = {
  recordType: WorkbenchRecordType;
  showWorkflowActions: boolean;
  canOperateData: boolean;
  availableActions: string[];
  showDetailAction?: boolean;
  onOpenDetail: (event?: MouseEvent<HTMLButtonElement>) => void;
  onAction: (action: WorkbenchInlineAction, event?: MouseEvent<HTMLButtonElement>) => void;
};

export default function RowActions({
  recordType,
  showWorkflowActions,
  canOperateData,
  availableActions,
  showDetailAction = true,
  onOpenDetail,
  onAction,
}: RowActionsProps) {
  const actions: { id: WorkbenchInlineAction; label: string; warning?: boolean }[] = [];
  if (recordType === "bank" && canOperateData && showWorkflowActions) {
    if (availableActions.includes("confirm_cash_pass_through")) actions.push({ id: "confirm-cash-pass-through", label: "确认为过账" });
    if (availableActions.includes("confirm_cash_ticket_purchase")) actions.push({ id: "confirm-cash-ticket-purchase", label: "确认为买票" });
    if (availableActions.includes("cancel_cash_special")) actions.push({ id: "cancel-cash-special", label: "取消现金处理", warning: true });
  }
  if (!showDetailAction && actions.length === 0) return null;

  return (
    <div className="row-actions" onClick={event => event.stopPropagation()}>
      {showDetailAction ? <button className="row-action-btn" type="button" onClick={onOpenDetail}>详情</button> : null}
      {actions.map(action => (
        <button key={action.id} className={`row-action-btn${action.warning ? " warning" : ""}`} type="button"
          onClick={event => onAction(action.id, event)}>
          {action.label}
        </button>
      ))}
    </div>
  );
}
