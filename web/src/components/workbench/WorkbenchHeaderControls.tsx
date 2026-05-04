import { useRef, useState, type FocusEvent } from "react";
import { Link as RouterLink } from "react-router-dom";

import { importWorkflowPath, type ImportWorkflowMode } from "../../features/imports/importRoutes";
import WorkbenchSearchBox from "./WorkbenchSearchBox";

type WorkbenchHeaderControlsProps = {
  canMutateData: boolean;
  className?: string;
  onOpenImport: (mode: ImportWorkflowMode) => void;
  onOpenSearch: () => void;
  onOpenSettings: () => void;
};

const IMPORT_ACTIONS: Array<{ label: string; mode: ImportWorkflowMode }> = [
  { label: "银行流水导入", mode: "bank_transaction" },
  { label: "发票导入", mode: "invoice" },
  { label: "ETC发票导入", mode: "etc_invoice" },
];

export default function WorkbenchHeaderControls({
  canMutateData,
  className,
  onOpenImport,
  onOpenSearch,
  onOpenSettings,
}: WorkbenchHeaderControlsProps) {
  const [importMenuHovered, setImportMenuHovered] = useState(false);
  const [importMenuFocused, setImportMenuFocused] = useState(false);
  const importMenuRef = useRef<HTMLDivElement | null>(null);
  const pointerIntentRef = useRef(false);
  const importMenuOpen = importMenuHovered || importMenuFocused;

  const handleImportMenuBlur = (event: FocusEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && importMenuRef.current?.contains(nextTarget)) {
      return;
    }
    setImportMenuFocused(false);
  };

  return (
    <div className={`workbench-header-controls${className ? ` ${className}` : ""}`}>
      <WorkbenchSearchBox onOpen={onOpenSearch} />
      <button className="workbench-settings-entry" type="button" onClick={onOpenSettings}>
        设置
      </button>
      {canMutateData ? (
        <div
          ref={importMenuRef}
          className={`workbench-import-entry${importMenuOpen ? " open" : ""}`}
          onBlur={handleImportMenuBlur}
          onFocus={() => {
            if (pointerIntentRef.current) {
              pointerIntentRef.current = false;
              return;
            }
            setImportMenuFocused(true);
          }}
          onMouseEnter={() => setImportMenuHovered(true)}
          onMouseLeave={() => {
            setImportMenuHovered(false);
            if (!(importMenuRef.current?.matches(":focus-within") ?? false)) {
              setImportMenuFocused(false);
            }
          }}
        >
          <button
            aria-expanded={importMenuOpen}
            aria-haspopup="menu"
            className="workbench-import-trigger"
            type="button"
            onPointerDown={() => {
              pointerIntentRef.current = true;
            }}
          >
            导入
          </button>
          <div aria-label="导入菜单" className="workbench-import-menu">
            {IMPORT_ACTIONS.map((action) => (
              <RouterLink
                key={action.mode}
                className="workbench-import-menu-item"
                tabIndex={importMenuOpen ? 0 : -1}
                to={importWorkflowPath(action.mode)}
                onClick={() => {
                  setImportMenuHovered(false);
                  setImportMenuFocused(false);
                  onOpenImport(action.mode);
                }}
              >
                {action.label}
              </RouterLink>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
