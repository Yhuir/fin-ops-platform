import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const legacyWorkbenchTables = new Set([
  "components/workbench/DetailDrawer.tsx",
  "components/workbench/PaneTable.tsx",
]);

const approvedNativeTableSurfaces = new Set([
  // The ordering form delegates arrow keys to dnd-kit instead of grid navigation.
  "components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx",
  // This grouped invoice table needs colgroup spans and a payment header spanning both rows.
  "components/inputInvoiceUsage/InputInvoiceUsageTable.tsx",
  // Six-column object rows span an independent eight-column HeroUI flow grid.
  "components/turnoverLedger/TurnoverLedgerGroupedTable.tsx",
  // Read-only financial breakdown and confirmation rows have no grid selection/sorting.
  "components/turnoverLedger/TurnoverLedgerSummary.tsx",
  "pages/TurnoverLedgerPage.tsx",
  // Static source key/value pairs use native row headers, without data-grid selection/sorting.
  "components/common/EntityDetailContent.tsx",
  "features/bankDetails/AutoTagRulesDrawer.tsx",
  // Grouped source-entry form with per-OA add rows; not a selectable data-list surface.
  "components/cost-statistics/CostSourceAllocationForm.tsx",
  // Current source correspondence needs native rowSpan/colSpan, outside shared data-list behavior.
  "components/cost-statistics/CostSourceEvidence.tsx",
]);

function tsxFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? tsxFiles(path) : entry.name.endsWith(".tsx") ? [path] : [];
  });
}

describe("HeroUI finance table migration", () => {
  it("keeps raw tables out of production components except approved native table surfaces", () => {
    const sourceRoot = join(process.cwd(), "src");
    const offenders = tsxFiles(sourceRoot)
      .filter((path) => !path.includes("/test/"))
      .filter((path) => !legacyWorkbenchTables.has(relative(sourceRoot, path)))
      .filter((path) => !approvedNativeTableSurfaces.has(relative(sourceRoot, path)))
      .filter((path) => /<table\b/.test(readFileSync(path, "utf8")))
      .map((path) => relative(sourceRoot, path));

    expect(offenders).toEqual([]);
  });
});
