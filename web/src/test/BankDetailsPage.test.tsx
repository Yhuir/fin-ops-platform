import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import BankDetailsPage from "../pages/BankDetailsPage";
import { installMockApiFetch } from "./apiMock";

function renderBankDetailsPage() {
  return render(
    <MuiProviders>
      <BankDetailsPage />
    </MuiProviders>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Bank details page", () => {
  test("loads the first account and its transactions", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    expect(within(page).getByRole("heading", { name: "银行明细" })).toBeInTheDocument();
    expect(within(page).getByText("总余额")).toBeInTheDocument();
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);
    expect(within(page).getByRole("button", { name: /工商银行 6386/ })).toHaveAttribute("aria-current", "true");
    expect(await within(page).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).getByText("收")).toBeInTheDocument();
    expect(within(page).getByText("20,000.00")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/bank-details\/transactions\?account_key=icbc%3A6386/),
      expect.any(Object),
    );
  });

  test("renders accounts as a list and transactions in the bank transaction data grid", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    const accountList = within(page).getByRole("list", { name: "银行账户" });
    expect(within(accountList).getAllByRole("listitem")).toHaveLength(2);

    const grid = await within(page).findByRole("grid", { name: "交易流水" });
    expect(within(grid).getByRole("columnheader", { name: "交易时间" })).toBeInTheDocument();
    expect(within(grid).getByRole("columnheader", { name: "金额" })).toBeInTheDocument();
    expect(await within(grid).findByText("云南溯源科技有限公司")).toBeInTheDocument();
  });

  test("selecting account and filters request transactions without changing balances", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

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

    fireEvent.blur(within(page).getByLabelText("开始日期"), { target: { value: "2026-02-01" } });
    fireEvent.blur(within(page).getByLabelText("结束日期"), { target: { value: "2026-02-15" } });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("date_from=2026-02-01&date_to=2026-02-15"),
        expect.any(Object),
      );
    });
  });
});
