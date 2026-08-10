import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import BusinessPeriodPicker, { formatMonthLabel } from "../components/common/BusinessPeriodPicker";

const sourcePath = "src/components/common/BusinessPeriodPicker.tsx";

function renderPeriodPicker(
  props: Partial<Parameters<typeof BusinessPeriodPicker>[0]> = {},
) {
  return render(
    <BusinessPeriodPicker
      allowAll={false}
      allowedModes={["month"]}
      ariaLabel="月份"
      onChange={() => {}}
      selection={{ mode: "month", year: "2026", month: "2026-03" }}
      years={["2025", "2026", "2027"]}
      {...props}
    />,
  );
}

describe("BusinessPeriodPicker", () => {
  test("uses HeroUI primitives and keeps the retired month picker deleted", () => {
    const source = readFileSync(resolve(__dirname, "..", sourcePath.replace(/^src\//, "")), "utf8");

    expect(existsSync(resolve(__dirname, "../components/MonthPicker.tsx"))).toBe(false);
    expect(source).toContain("@heroui/react");
    expect(source).not.toMatch(/<button|@mui\/|MuiDatePickerCompatProvider/);
  });

  test("keeps the external month value as YYYY-MM", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPeriodPicker({ onChange });

    await user.click(screen.getByRole("button", { name: "月份：2026年3月" }));
    await user.click(await screen.findByRole("button", { name: "2026年" }));
    await user.click(screen.getByRole("button", { name: "五月" }));

    expect(onChange).toHaveBeenCalledWith({ mode: "month", year: "2026", month: "2026-05" });
  });

  test("supports permanent inline month selection", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPeriodPicker({ inline: true, onChange });

    await user.click(screen.getByRole("button", { name: "五月" }));

    expect(onChange).toHaveBeenCalledWith({ mode: "month", year: "2026", month: "2026-05" });
  });

  test("exposes all time as the left selected action", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPeriodPicker({
      allowAll: true,
      allLabel: "全部发票",
      onChange,
      selection: { mode: "all", year: "2026", month: "2026-03" },
    });

    const allButton = screen.getByRole("button", { name: "全部发票" });
    expect(allButton).toHaveAttribute("aria-pressed", "true");
    expect(allButton.closest(".business-period-picker")).toHaveClass("business-period-picker--segmented");
    await user.click(allButton);
    expect(onChange).toHaveBeenCalledWith({ mode: "all", year: "2026", month: "2026-03" });
  });

  test("formats month labels and invalid values predictably", () => {
    expect(formatMonthLabel("2026-12")).toBe("2026年12月");
    expect(formatMonthLabel("bad-value")).toBe("2026年1月");
  });
});
