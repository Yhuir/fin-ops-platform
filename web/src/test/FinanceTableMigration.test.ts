import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const legacyWorkbenchTables = new Set([
  "components/workbench/DetailDrawer.tsx",
  "components/workbench/PaneTable.tsx",
]);

function tsxFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? tsxFiles(path) : entry.name.endsWith(".tsx") ? [path] : [];
  });
}

describe("HeroUI finance table migration", () => {
  it("keeps raw tables out of every non-Workbench production component", () => {
    const sourceRoot = join(process.cwd(), "src");
    const offenders = tsxFiles(sourceRoot)
      .filter((path) => !path.includes("/test/"))
      .filter((path) => !legacyWorkbenchTables.has(relative(sourceRoot, path)))
      .filter((path) => /<table\b/.test(readFileSync(path, "utf8")))
      .map((path) => relative(sourceRoot, path));

    expect(offenders).toEqual([]);
  });
});
