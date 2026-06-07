import { existsSync, readdirSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";

const sourceRoot = resolve(__dirname, "..");

const runtimeForbiddenPattern =
  /from ["']@mui\/|import\s+[^;]*@mui\/|MuiProviders|muiTheme|@mui\/x-date-pickers|@mui\/x-data-grid|Mui[A-Z]/;

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const nextPath = resolve(dir, entry.name);
    const relativePath = relative(sourceRoot, nextPath);
    if (entry.isDirectory()) {
      if (
        relativePath === "components/workbench"
        || relativePath.startsWith("components/workbench/")
        || relativePath === "test"
        || relativePath.startsWith("test/")
      ) {
        return [];
      }
      return collectSourceFiles(nextPath);
    }
    return /\.(ts|tsx|css)$/.test(entry.name) ? [nextPath] : [];
  });
}

describe("MUI containment", () => {
  test("keeps MUI out of non-workbench runtime source files", () => {
    const runtimeFiles = collectSourceFiles(sourceRoot)
      .filter((path) => relative(sourceRoot, path) !== "app/styles.css");
    const offenders = runtimeFiles.flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return runtimeForbiddenPattern.test(source) ? [relative(sourceRoot, path)] : [];
    });

    expect(offenders).toEqual([]);
  });

  test("keeps global MUI CSS free of MUI-generated selectors", () => {
    const stylesPath = resolve(sourceRoot, "app/styles.css");
    const source = readFileSync(stylesPath, "utf8");
    const muiLines = source
      .split("\n")
      .map((line, index) => ({ line: line.trim(), number: index + 1 }))
      .filter(({ line }) => /Mui|@mui|DataGrid/.test(line));

    expect(muiLines.map(({ line, number }) => `${number}: ${line}`)).toEqual([]);
  });

  test("keeps legacy MUI providers out of app runtime", () => {
    expect(existsSync(resolve(sourceRoot, "app/MuiProviders.tsx"))).toBe(false);
    expect(existsSync(resolve(sourceRoot, "app/muiTheme.ts"))).toBe(false);
    expect(existsSync(resolve(sourceRoot, "test/legacyWorkbenchMuiProvider.tsx"))).toBe(false);
  });
});
