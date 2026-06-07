import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import MonthPicker, { formatMonthLabel } from "../components/MonthPicker";

const monthPickerSourceFiles = [
  "src/components/MonthPicker.tsx",
  "src/app/App.tsx",
] as const;

const removedDateCompatFiles = [
  "src/app/MuiDatePickerCompatProvider.tsx",
] as const;

function readWebSource(path: (typeof monthPickerSourceFiles)[number]) {
  return readFileSync(resolve(__dirname, "..", path.replace(/^src\//, "")), "utf8");
}

function renderMonthPicker(
  props: Partial<Parameters<typeof MonthPicker>[0]> = {},
) {
  return render(
    <MuiProviders>
      <MonthPicker
        value="2026-03"
        onChange={() => {}}
        {...props}
      />
    </MuiProviders>,
  );
}

describe("MonthPicker", () => {
  test("targets project month primitives and removes date picker compatibility", () => {
    const sourceByPath = Object.fromEntries(monthPickerSourceFiles.map((path) => [path, readWebSource(path)]));
    const remainingDateCompatFiles = removedDateCompatFiles.flatMap((path) => (
      existsSync(resolve(__dirname, "..", path.replace(/^src\//, ""))) ? [path] : []
    ));
    const forbiddenMuiImports = monthPickerSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenDateCompat = monthPickerSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /MuiDatePickerCompatProvider|LocalizationProvider|DatePicker|StaticDatePicker|MuiInputBase|MuiFormControl/.test(source)
        ? [path]
        : [];
    });

    expect(remainingDateCompatFiles).toEqual([]);
    expect(forbiddenMuiImports).toEqual([]);
    expect(forbiddenDateCompat).toEqual([]);
  });

  test("renders the current month as a labeled month control", () => {
    renderMonthPicker();

    const monthField = screen.getByRole("group", { name: "月份" });
    expect(monthField).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "年份" })).toHaveAttribute("aria-valuenow", "2026");
    expect(screen.getByRole("spinbutton", { name: "月份" })).toHaveAttribute("aria-valuenow", "3");
  });

  test("keeps the external value as YYYY-MM when a month is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderMonthPicker({ onChange });

    await user.click(screen.getByLabelText("年月选择"));
    await user.click(await screen.findByRole("radio", { name: "2026" }));
    await user.click(screen.getByRole("radio", { name: "五月" }));

    expect(onChange).toHaveBeenCalledWith("2026-05");
  });

  test("supports inline month selection without changing the external contract", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderMonthPicker({ inline: true, onChange });

    await user.click(screen.getByRole("radio", { name: "五月" }));

    expect(onChange).toHaveBeenCalledWith("2026-05");
  });

  test("formats month labels and invalid values predictably", () => {
    expect(formatMonthLabel("2026-12")).toBe("2026年12月");
    expect(formatMonthLabel("bad-value")).toBe("2026年1月");
  });
});
