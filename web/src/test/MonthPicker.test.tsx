import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import MonthPicker from "../components/MonthPicker";

describe("MonthPicker", () => {
  test("shifts the popover left when opening near the right viewport edge", async () => {
    const user = userEvent.setup();
    const originalInnerWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 320,
    });

    const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function mockRect() {
      if (this.classList.contains("month-picker")) {
        return {
          x: 240,
          y: 0,
          top: 0,
          left: 240,
          bottom: 40,
          right: 304,
          width: 64,
          height: 40,
          toJSON: () => ({}),
        };
      }

      if (this.classList.contains("month-picker-popover")) {
        return {
          x: 240,
          y: 50,
          top: 50,
          left: 240,
          bottom: 250,
          right: 532,
          width: 292,
          height: 200,
          toJSON: () => ({}),
        };
      }

      return {
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        bottom: 0,
        right: 0,
        width: 0,
        height: 0,
        toJSON: () => ({}),
      };
    });

    render(<MonthPicker value="2026-03" onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: "年月选择" }));

    const popover = await screen.findByRole("dialog", { name: "年月面板" });
    await waitFor(() => {
      expect(popover).toHaveStyle({ left: "-228px" });
    });

    rectSpy.mockRestore();
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: originalInnerWidth,
    });
  });
});
