import { readFileSync } from "node:fs";

const source = () => readFileSync("src/app/styles.css", "utf8");

describe("finance table layout tokens", () => {
  test("defines table density and cell tokens", () => {
    const css = source();

    expect(css).toMatch(/--fp-table-row-height:\s*44px\b/);
    expect(css).toMatch(/--fp-table-row-height-complex:\s*60px\b/);
    expect(css).toMatch(/--fp-table-cell-padding-x:\s*10px\b/);
    expect(css).toMatch(/--fp-table-cell-padding-y:\s*8px\b/);
    expect(css).toMatch(/--fp-table-header-bg:\s*var\(--fp-surface-muted\)/);
  });

  test("defines amount and numeric layout tokens", () => {
    const css = source();

    expect(css).toMatch(/--fp-table-amount-align:\s*right\b/);
    expect(css).toMatch(/--fp-table-data-font:\s*var\(--fp-font-data\)/);
    expect(css).toMatch(/--fp-table-numeric-variant:\s*tabular-nums\b/);
  });

  test("defines stable tag sizing for repeated table rows", () => {
    const css = source();

    expect(css).toMatch(/--fp-tag-height-table:\s*22px\b/);
    expect(css).toMatch(/--fp-tag-direction-min-width:\s*44px\b/);
    expect(css).toMatch(/--fp-tag-radius-table:\s*var\(--fp-radius-xs\)/);
  });
});
