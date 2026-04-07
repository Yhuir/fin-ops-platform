import { useEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import type { WorkbenchActionVariant, WorkbenchRecordType } from "../../features/workbench/types";

export type WorkbenchInlineAction =
  | "relation-status"
  | "unlink"
  | "handle-exception"
  | "confirm-match"
  | "flag-exception"
  | "ignore-row"
  | "cancel-exception";

type RowActionsMode = "default" | "cancel-exception-only";

type RowActionsProps = {
  recordType: WorkbenchRecordType;
  variant: WorkbenchActionVariant;
  showWorkflowActions: boolean;
  canMutateData: boolean;
  availableActions: string[];
  mode?: RowActionsMode;
  onOpenDetail: (event: MouseEvent<HTMLButtonElement>) => void;
  onAction: (action: WorkbenchInlineAction, event: MouseEvent<HTMLButtonElement>) => void;
};

export default function RowActions({
  recordType,
  variant,
  showWorkflowActions,
  canMutateData,
  availableActions = [],
  mode = "default",
  onOpenDetail,
  onAction,
}: RowActionsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const canIgnore = availableActions.includes("ignore");
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

  const handleMenuToggle = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setMenuOpen((current) => !current);
  };

  const handleAction = (action: WorkbenchInlineAction) => (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setMenuOpen(false);
    onAction(action, event);
  };

  if (mode === "cancel-exception-only") {
    return (
      <div className="row-actions" onClick={(event) => event.stopPropagation()}>
        {canMutateData ? (
          <button className="row-action-btn warning" type="button" onClick={handleAction("cancel-exception")}>
            取消异常处理
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="row-actions" onClick={(event) => event.stopPropagation()}>
      <button className="row-action-btn" type="button" onClick={onOpenDetail}>
        详情
      </button>

      {canMutateData && canIgnore ? (
        <button className="row-action-btn warning" type="button" onClick={handleAction("ignore-row")}>
          忽略
        </button>
      ) : null}

      {canMutateData && showWorkflowActions && variant === "confirm-exception" ? (
        <>
          <button className="row-action-btn primary" type="button" onClick={handleAction("confirm-match")}>
            确认关联
          </button>
          <button className="row-action-btn warning" type="button" onClick={handleAction("flag-exception")}>
            {recordType === "invoice" ? "标记异常" : "异常处理"}
          </button>
        </>
      ) : null}

      {canMutateData && showWorkflowActions && variant === "bank-review" ? (
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
                  <button className="row-menu-item warning" role="menuitem" type="button" onClick={handleAction("handle-exception")}>
                    异常处理
                  </button>
                </div>,
                document.body,
              )
            : null}
        </div>
      ) : null}
    </div>
  );
}
