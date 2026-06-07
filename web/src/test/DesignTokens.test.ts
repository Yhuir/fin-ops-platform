import { readFileSync } from "node:fs";

const source = () => readFileSync("src/app/styles.css", "utf8");

describe("Ledger Calm design tokens", () => {
  test("defines the core finance platform CSS variables", () => {
    const css = source();

    expect(css).toMatch(/--fp-ink:\s*#111827\b/);
    expect(css).toMatch(/--fp-text-primary:\s*#1f2937\b/);
    expect(css).toMatch(/--fp-page:\s*#f6f8fb\b/);
    expect(css).toMatch(/--fp-surface:\s*#ffffff\b/);
    expect(css).toMatch(/--fp-border:\s*#d7dee8\b/);
    expect(css).toMatch(/--fp-primary:\s*#1d4ed8\b/);
    expect(css).toMatch(/--fp-primary-hover:\s*#1e40af\b/);
    expect(css).toMatch(/--fp-success:\s*#16803c\b/);
    expect(css).toMatch(/--fp-warning:\s*#b76e00\b/);
    expect(css).toMatch(/--fp-danger:\s*#c2412d\b/);
  });

  test("maps Ledger Calm tokens to HeroUI semantic variables", () => {
    const css = source();

    expect(css).toMatch(/--background:\s*var\(--fp-page\)/);
    expect(css).toMatch(/--foreground:\s*var\(--fp-text-primary\)/);
    expect(css).toMatch(/--surface:\s*var\(--fp-surface\)/);
    expect(css).toMatch(/--accent:\s*var\(--fp-primary\)/);
    expect(css).toMatch(/--accent-foreground:\s*var\(--fp-surface\)/);
    expect(css).toMatch(/--success:\s*var\(--fp-success\)/);
    expect(css).toMatch(/--warning:\s*var\(--fp-warning\)/);
    expect(css).toMatch(/--danger:\s*var\(--fp-danger\)/);
  });

  test("documents the required Tailwind and HeroUI import order", () => {
    const css = source();
    const tailwindIndex = css.indexOf('@import "tailwindcss";');
    const herouiIndex = css.indexOf('@import "@heroui/styles";');

    expect(tailwindIndex).toBeGreaterThanOrEqual(0);
    expect(herouiIndex).toBeGreaterThan(tailwindIndex);
  });

  test("exposes project tokens through a Tailwind v4 theme bridge", () => {
    const css = source();

    expect(css).toMatch(/@theme\s+inline\s*\{/);
    expect(css).toMatch(/--color-fp-primary:\s*var\(--fp-primary\)/);
    expect(css).toMatch(/--color-fp-page:\s*var\(--fp-page\)/);
    expect(css).toMatch(/--color-fp-surface:\s*var\(--fp-surface\)/);
    expect(css).toMatch(/--radius-fp-sm:\s*var\(--fp-radius-sm\)/);
    expect(css).toMatch(/--shadow-fp-drawer:\s*var\(--fp-shadow-drawer\)/);
  });

  test("defines shared motion tokens and reduced motion fallback", () => {
    const css = source();

    expect(css).toMatch(/--motion-fast:\s*120ms\b/);
    expect(css).toMatch(/--motion-base:\s*180ms\b/);
    expect(css).toMatch(/--motion-slow:\s*240ms\b/);
    expect(css).toMatch(/--ease-standard:\s*cubic-bezier\(0\.2,\s*0,\s*0,\s*1\)/);
    expect(css).toMatch(/--ease-out-quart:\s*cubic-bezier\(0\.25,\s*1,\s*0\.5,\s*1\)/);
    expect(css).toMatch(/--ease-fp-standard:\s*var\(--ease-standard\)/);
    expect(css).toMatch(/--ease-fp-out-quart:\s*var\(--ease-out-quart\)/);
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    expect(css).toMatch(/transition-duration:\s*1ms\s*!important/);
  });
});
