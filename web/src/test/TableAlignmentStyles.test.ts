import { readFileSync } from "node:fs";

const source = readFileSync("src/app/styles.css", "utf8");

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function cssBlock(selector: string) {
  const match = source.match(new RegExp(`(?:^|\\n)${escapeRegExp(selector)}\\s*\\{(?<body>[^}]*)\\}`, "s"));
  expect(match, `Missing CSS block for ${selector}`).not.toBeNull();
  return match?.groups?.body ?? "";
}

function expectDeclaration(selector: string, declaration: RegExp) {
  expect(cssBlock(selector)).toMatch(declaration);
}

function expectSquareSurface(selector: string) {
  const radii = [...cssBlock(selector).matchAll(/border-radius:\s*([^;]+);/g)].map((match) => match[1]?.trim());
  expect(radii.every((radius) => radius === "0" || radius === "0px"), selector).toBe(true);
}

describe("finance table alignment styles", () => {
  test("defines the shared HeroUI finance table shell contract", () => {
    expectDeclaration(".finance-table", /--finance-table-row-height:\s*var\(--fp-table-row-height\)/);
    expectDeclaration(".finance-table", /border-radius:\s*0/);
    expectDeclaration(".finance-table", /background:\s*var\(--fp-surface\)/);
    expectDeclaration(".finance-table", /padding:\s*0/);
    expectDeclaration(".finance-page-table-frame", /height:\s*clamp\(600px, calc\(100dvh - 132px\), 1080px\)/);
    expectDeclaration(".finance-page-table-frame", /overflow:\s*hidden/);
    expectDeclaration(".finance-table__scroll", /overflow-x:\s*auto/);
    expectDeclaration(".finance-table--contained", /height:\s*100%/);
    expectDeclaration(".finance-table--contained .finance-table__scroll", /overflow:\s*auto/);
    expectDeclaration(".finance-table--contained .finance-table__scroll", /overscroll-behavior:\s*contain/);
    expectDeclaration(".finance-table--contained .finance-table__scroll", /scrollbar-gutter:\s*stable/);
    expectDeclaration(".finance-page-table-frame .finance-table--contained", /grid-template-rows:\s*minmax\(0, 1fr\) auto/);
    expectDeclaration(".finance-page-table-frame .finance-table--contained", /overflow:\s*hidden/);
    expectDeclaration(".finance-page-table-frame .finance-table--contained .finance-table__scroll", /height:\s*auto/);
    expectDeclaration(".finance-table__content", /min-width:\s*var\(--finance-table-min-width/);
    expectDeclaration(".finance-table__row", /min-height:\s*var\(--fp-table-row-height\)/);
    expectDeclaration(".finance-table__row", /transition:[^;]*background-color var\(--motion-fast\) var\(--ease-standard\)/);
    expectDeclaration(".finance-table__column", /position:\s*sticky/);
    expectDeclaration(".finance-table__column", /top:\s*0/);
    expectDeclaration(".finance-table__cell", /border-bottom:\s*1px solid var\(--fp-border-subtle\)/);
  });

  test("keeps table-bearing page surfaces square instead of nesting rounded cards", () => {
    const flatSurfaceSelectors = [
      ".oa-pending-payments-table-frame",
      ".batch-accounting-oa-panel",
      ".turnover-ledger-table-panel",
      ".turnover-ledger-table-wrap",
      ".turnover-ledger-export-dialog__table-wrap",
      ".bank-flow-rule-batches-transactions",
      ".app-health-section",
      ".app-health-inventory-panel",
      ".import-workflow-panel--table",
      ".tax-panel",
      ".settings-native-table-shell",
      ".bank-transaction-panel",
      ".bank-transaction-grid",
      ".etc-invoice-table-container",
      ".etc-reconciliation-table-container",
      ".input-invoice-usage-rules-table-shell",
      ".output-invoice-collection-rules-table-frame",
      ".bank-auto-tag-table-container",
    ];

    flatSurfaceSelectors.forEach((selector) => {
      expectSquareSurface(selector);
    });

    expect(source).toMatch(/\.settings-native-table-shell\s*\{[^}]*border-radius:\s*0/s);
    expect(source).toMatch(/\.cost-table-shell,\s*\.cost-table-section\s*\{[^}]*border-radius:\s*0/s);
  });

  test("aligns cells by column role instead of globally centering every table cell", () => {
    expectDeclaration(".output-invoice-collections-table-column-heading", /width:\s*100%/);
    expectDeclaration(".output-invoice-collections-table-header-stack", /justify-content:\s*center/);
    expectDeclaration(".output-invoice-collections-table-header-stack", /text-align:\s*center/);

    expectDeclaration(".finance-table__cell[data-column-role=\"identity\"]", /text-align:\s*left/);
    expectDeclaration(".finance-table__cell[data-column-role=\"account\"]", /text-align:\s*left/);
    expectDeclaration(".finance-table__cell[data-column-role=\"description\"]", /text-align:\s*left/);

    expectDeclaration(".finance-table__cell[data-column-role=\"amount\"]", /text-align:\s*right/);
    expectDeclaration(".finance-table__cell[data-column-role=\"quantity\"]", /text-align:\s*right/);
    expectDeclaration(".finance-table__cell[data-column-role=\"amount\"]", /font-variant-numeric:\s*tabular-nums/);

    expectDeclaration(".finance-table__cell[data-column-role=\"date\"]", /text-align:\s*center/);
    expectDeclaration(".finance-table__cell[data-column-role=\"status\"]", /text-align:\s*center/);
    expectDeclaration(".finance-table__cell[data-column-role=\"direction\"]", /text-align:\s*center/);
    expectDeclaration(".finance-table__cell[data-column-role=\"selection\"]", /text-align:\s*center/);
  });

  test("stabilizes amount, direction tag, and empty value primitives", () => {
    expectDeclaration(".finance-amount-cell", /font-variant-numeric:\s*tabular-nums/);
    expectDeclaration(".finance-amount-cell", /text-align:\s*right/);
    expectDeclaration(".finance-amount-cell__meta", /grid-template-columns:\s*var\(--fp-tag-direction-min-width\)/);

    expectDeclaration(".finance-direction-tag", /height:\s*var\(--fp-tag-height-table\)/);
    expectDeclaration(".finance-direction-tag", /min-width:\s*var\(--fp-tag-direction-min-width\)/);
    expectDeclaration(".finance-direction-tag", /transition:[^;]*background-color var\(--motion-fast\) var\(--ease-standard\)/);

    expectDeclaration(".finance-empty-value", /color:\s*var\(--fp-text-muted\)/);
  });

  test("keeps table status tags on the shared interaction timing system", () => {
    expectDeclaration(".finance-status-tag", /height:\s*var\(--fp-tag-height-table\)/);
    expectDeclaration(".finance-status-tag", /transition:[^;]*background-color var\(--motion-fast\) var\(--ease-standard\)/);
  });
});
