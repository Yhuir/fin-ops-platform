import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import MonthPicker from "../components/MonthPicker";

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
  test("renders the current month through a MUI X month field", () => {
    renderMonthPicker();

    const monthField = screen.getByRole("group", { name: "月份" });
    expect(monthField.closest(".MuiFormControl-root")).not.toBeNull();
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
});
