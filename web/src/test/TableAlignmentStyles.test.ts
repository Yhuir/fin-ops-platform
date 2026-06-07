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

describe("finance table alignment styles", () => {
  test("defines the shared HeroUI finance table shell contract", () => {
    expectDeclaration(".finance-table", /--finance-table-row-height:\s*var\(--fp-table-row-height\)/);
    expectDeclaration(".finance-table__scroll", /overflow-x:\s*auto/);
    expectDeclaration(".finance-table__content", /min-width:\s*var\(--finance-table-min-width/);
    expectDeclaration(".finance-table__row", /min-height:\s*var\(--fp-table-row-height\)/);
    expectDeclaration(".finance-table__row", /transition:[^;]*background-color var\(--motion-fast\) var\(--ease-standard\)/);
  });

  test("aligns cells by column role instead of globally centering every table cell", () => {
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
