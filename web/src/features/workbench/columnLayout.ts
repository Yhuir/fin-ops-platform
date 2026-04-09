import { defaultWorkbenchColumnLayouts } from "./tableConfig";
import type { WorkbenchColumnLayouts, WorkbenchRecordType } from "./types";

export type WorkbenchColumnDropPosition = "before" | "after";

export function reorderWorkbenchColumnLayout(
  layouts: WorkbenchColumnLayouts,
  paneId: WorkbenchRecordType,
  activeKey: string,
  overKey: string,
  position: WorkbenchColumnDropPosition,
) {
  const currentOrder = layouts[paneId]?.length ? layouts[paneId] : defaultWorkbenchColumnLayouts[paneId];
  if (activeKey === overKey && position === "before") {
    return layouts;
  }

  const withoutActive = currentOrder.filter((key) => key !== activeKey);
  const targetIndex = withoutActive.indexOf(overKey);
  if (targetIndex < 0) {
    return layouts;
  }

  const insertIndex = position === "after" ? targetIndex + 1 : targetIndex;
  const nextOrder = [...withoutActive];
  nextOrder.splice(insertIndex, 0, activeKey);

  if (nextOrder.join("|") === currentOrder.join("|")) {
    return layouts;
  }

  return {
    ...layouts,
    [paneId]: nextOrder,
  };
}
