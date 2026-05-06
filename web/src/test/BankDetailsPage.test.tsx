import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import BankDetailsPage from "../pages/BankDetailsPage";
import { installMockApiFetch } from "./apiMock";

const defaultSession: SessionPayload = {
  allowed: true,
  user: {
    userId: "1",
    username: "TESTFULL001",
    nickname: "测试全权限",
    displayName: "测试全权限",
    deptId: null,
    deptName: null,
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

const staticSession: SessionContextValue = {
  status: "authenticated",
  session: defaultSession,
  refresh: () => undefined,
};

function renderBankDetailsPage() {
  return render(
    <MuiProviders>
      <SessionContext.Provider value={staticSession}>
        <PageSessionStateProvider>
          <BankDetailsPage />
        </PageSessionStateProvider>
      </SessionContext.Provider>
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
    expect(within(page).getByLabelText(/交通银行 3847 余额/)).toHaveTextContent("余额为空");
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

  test("ignores aborted bank detail requests", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const url = new URL(rawUrl, "http://localhost");
      if (url.pathname === "/api/bank-details/accounts") {
        return new Response(JSON.stringify({
          total_balance: "130500.50",
          balance_account_count: 1,
          missing_balance_account_count: 0,
          accounts: [
            {
              account_key: "icbc:6386",
              bank_name: "工商银行",
              account_last4: "6386",
              display_name: "工商银行 6386",
              latest_balance: "130500.50",
              latest_balance_at: "2026-05-01 16:30:00",
              has_balance: true,
              transaction_count: 1,
            },
          ],
        }), { status: 200 });
      }
      if (url.pathname === "/api/bank-details/transactions") {
        throw new Error("signal is aborted without reason");
      }
      throw new Error(`Unhandled fetch mock for ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/^\/api\/bank-details\/transactions/),
        expect.any(Object),
      );
    });
    await expect(within(page).findByText("signal is aborted without reason", {}, { timeout: 1000 })).rejects.toThrow();
  });
});
