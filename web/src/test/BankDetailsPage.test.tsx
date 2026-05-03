import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Bank details page", () => {
  test("route renders from navigation and loads the first account", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await user.click(await screen.findByRole("link", { name: "银行明细" }));

    const page = await screen.findByTestId("bank-details-page");
    expect(within(page).getByRole("heading", { name: "银行明细" })).toBeInTheDocument();
    expect(within(page).getByText("总余额")).toBeInTheDocument();
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);
    expect(within(page).getByRole("button", { name: /工商银行 6386/ })).toHaveAttribute("aria-current", "true");
    expect(within(page).getByRole("row", { name: /2026-05-01.*云南溯源科技有限公司.*收.*20,000.00/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/bank-details\/transactions\?account_key=icbc%3A6386/),
      expect.any(Object),
    );
  });

  test("selecting account and filters request transactions without changing balances", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/bank-details");

    const page = await screen.findByTestId("bank-details-page");
    await user.click(within(page).getByRole("button", { name: /交通银行 3847/ }));

    expect(await within(page).findByText("当前时间范围内没有流水。")).toBeInTheDocument();
    expect(within(page).getByLabelText("交通银行 3847 余额")).toHaveTextContent("余额为空");
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: "上月" }));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("date_from=2026-04-01&date_to=2026-04-30"),
      expect.any(Object),
    );
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);

    await user.clear(within(page).getByLabelText("年月筛选"));
    await user.type(within(page).getByLabelText("年月筛选"), "2026-03");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("date_from=2026-03-01&date_to=2026-03-31"),
      expect.any(Object),
    );

    await user.clear(within(page).getByLabelText("开始日期"));
    await user.type(within(page).getByLabelText("开始日期"), "2026-02-01");
    await user.clear(within(page).getByLabelText("结束日期"));
    await user.type(within(page).getByLabelText("结束日期"), "2026-02-15");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("date_from=2026-02-01&date_to=2026-02-15"),
      expect.any(Object),
    );
  });
});
