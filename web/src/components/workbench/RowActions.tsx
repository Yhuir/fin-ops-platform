import { Dropdown } from "@heroui/react";
import { Ellipsis } from "lucide-react";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import type { WorkbenchRecordType } from "../../features/workbench/types";

export type WorkbenchInlineAction =
  | "relation-status"
  | "unlink"
  | "confirm-cash-pass-through"
  | "confirm-cash-ticket-purchase"
  | "cancel-cash-special"
  | "enter-invoice"
  | "assign-invoice-expense-items";

type RowActionsProps = {
  recordType: WorkbenchRecordType;
  showWorkflowActions: boolean;
  canMutateData: boolean;
  availableActions: string[];
  showDetailAction?: boolean;
  onOpenDetail: (event?: MouseEvent<HTMLButtonElement>) => void;
  onAction: (action: WorkbenchInlineAction, event?: MouseEvent<HTMLButtonElement>) => void;
  compact?: boolean;
};

export default function RowActions({
  recordType,
  showWorkflowActions,
  canMutateData,
  availableActions = [],
  showDetailAction = true,
  onOpenDetail,
  onAction,
  compact = false,
}: RowActionsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const canConfirmCashPassThrough = availableActions.includes("confirm_cash_pass_through");
  const canConfirmCashTicketPurchase = availableActions.includes("confirm_cash_ticket_purchase");
  const canCancelCashSpecial = availableActions.includes("cancel_cash_special");
  const menuWrapRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }

    const updateMenuPosition = () => {
      const button = menuButtonRef.current;
      if (!button) {
        return;
      }
      const rect = button.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 6,
        right: window.innerWidth - rect.right,
      });
    };

    const handlePointerDown = (event: MouseEvent | globalThis.MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) {
        return;
      }
      if (menuWrapRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setMenuOpen(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    window.addEventListener("keydown", handleEscape);
    window.addEventListener("mousedown", handlePointerDown);

    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
      window.removeEventListener("keydown", handleEscape);
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [menuOpen]);

  if (compact) {
    const actions: Array<{ id: WorkbenchInlineAction | "detail"; label: string; warning?: boolean }> = [];
    if (recordType === "bank" && showDetailAction) actions.push({ id: "detail", label: "详情" });
    if (recordType === "bank" && canMutateData && showWorkflowActions) {
      actions.push({ id: "relation-status", label: "关联情况" });
      actions.push({ id: "unlink", label: "取消关联" });
      if (canConfirmCashPassThrough) actions.push({ id: "confirm-cash-pass-through", label: "确认为过账" });
      if (canConfirmCashTicketPurchase) actions.push({ id: "confirm-cash-ticket-purchase", label: "确认为买票" });
      if (canCancelCashSpecial) actions.push({ id: "cancel-cash-special", label: "取消现金处理", warning: true });
    }
    if (actions.length === 0) return null;

    return (
      <div className="row-actions row-actions-compact" onClick={(event) => event.stopPropagation()}>
        <Dropdown>
          <Dropdown.Trigger aria-label="更多操作" className="row-actions-compact-trigger">
            <Ellipsis aria-hidden="true" size={16} />
          </Dropdown.Trigger>
          <Dropdown.Popover placement="bottom end">
            <Dropdown.Menu
              aria-label="记录操作"
              onAction={(key) => {
                const action = String(key) as WorkbenchInlineAction | "detail";
                if (action === "detail") onOpenDetail();
                else onAction(action);
              }}
            >
              {actions.map((action) => (
                <Dropdown.Item className={action.warning ? "row-menu-item-warning" : undefined} id={action.id} key={action.id}>
                  {action.label}
                </Dropdown.Item>
              ))}
            </Dropdown.Menu>
          </Dropdown.Popover>
        </Dropdown>
      </div>
    );
  }

  const handleMenuToggle = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setMenuOpen((current) => !current);
  };

  const handleAction = (action: WorkbenchInlineAction) => (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setMenuOpen(false);
    onAction(action, event);
  };

  return (
    <div className="row-actions" onClick={(event) => event.stopPropagation()}>
      {showDetailAction ? (
        <button className="row-action-btn" type="button" onClick={onOpenDetail}>
          详情
        </button>
      ) : null}

      {recordType === "bank" && canMutateData && showWorkflowActions ? (
        <div ref={menuWrapRef} className="row-menu-wrap">
          <button
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            className="row-action-btn"
            ref={menuButtonRef}
            type="button"
            onClick={handleMenuToggle}
          >
            更多
          </button>
          {menuOpen && menuPosition && typeof document !== "undefined"
            ? createPortal(
                <div
                  ref={menuRef}
                  className="row-menu row-menu-portal"
                  role="menu"
                  style={{ position: "fixed", top: menuPosition.top, right: menuPosition.right }}
                >
                  <button className="row-menu-item" role="menuitem" type="button" onClick={handleAction("relation-status")}>
                    关联情况
                  </button>
                  <button className="row-menu-item" role="menuitem" type="button" onClick={handleAction("unlink")}>
                    取消关联
                  </button>
                  {canConfirmCashPassThrough ? (
                    <button className="row-menu-item" role="menuitem" type="button" onClick={handleAction("confirm-cash-pass-through")}>
                      确认为过账
                    </button>
                  ) : null}
                  {canConfirmCashTicketPurchase ? (
                    <button className="row-menu-item" role="menuitem" type="button" onClick={handleAction("confirm-cash-ticket-purchase")}>
                      确认为买票
                    </button>
                  ) : null}
                  {canCancelCashSpecial ? (
                    <button className="row-menu-item warning" role="menuitem" type="button" onClick={handleAction("cancel-cash-special")}>
                      取消现金处理
                    </button>
                  ) : null}
                </div>,
                document.body,
              )
            : null}
        </div>
      ) : null}
    </div>
  );
}
