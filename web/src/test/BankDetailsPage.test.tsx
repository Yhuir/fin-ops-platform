import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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

function requestUrls(fetchMock: ReturnType<typeof installMockApiFetch>, pathname: string) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === pathname);
}

function exactTextContent(text: string) {
  return (_content: string, element: Element | null) => (
    element?.textContent === text
    && Array.from(element.children).every((child) => child.textContent !== text)
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Bank details page", () => {
  test("uses MUI Table with compact server pagination instead of DataGrid", () => {
    const source = readFileSync(resolve(process.cwd(), "src/pages/BankDetailsPage.tsx"), "utf8");

    expect(source).not.toContain("@mui/x-data-grid");
    expect(source).not.toContain("<DataGrid");
    expect(source).not.toContain("disableVirtualization");
    expect(source).not.toContain("getRowHeight={() => \"auto\"}");
    expect(source).toContain("<Table aria-label=\"交易流水\"");
    expect(source).toContain("rowsPerPageOptions={[25, 50, 100]}");
  });

  test("loads all accounts by default and its transactions", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    expect(within(page).queryByRole("heading", { name: "银行明细" })).not.toBeInTheDocument();
    expect(within(page).getByRole("heading", { name: "全部流水" })).toBeInTheDocument();
    expect(within(page).getByText("总余额")).toBeInTheDocument();
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);
    expect(within(page).getByRole("button", { name: /全部流水 299 条/ })).toHaveAttribute("aria-current", "true");
    expect(await within(page).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).getByText("收")).toBeInTheDocument();
    expect(within(page).getByText("20,000.00")).toBeInTheDocument();
    const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
    expect(transactionRequest?.searchParams.get("account_key")).toBeNull();
  });

  test("requests the current year range for both accounts and transactions by default", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    await screen.findByText("云南溯源科技有限公司");

    const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
    const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);

    expect(accountRequest?.searchParams.get("date_from")).toBe("2026-01-01");
    expect(accountRequest?.searchParams.get("date_to")).toBe("2026-12-31");
    expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-01-01");
    expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-12-31");
    expect(transactionRequest?.searchParams.get("account_key")).toBeNull();
  });

  test("renders accounts as a list and transactions in the bank transaction table", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    const accountList = within(page).getByRole("list", { name: "银行账户" });
    expect(within(accountList).getAllByRole("listitem")).toHaveLength(3);
    const allAccountsButton = within(accountList).getByRole("button", { name: /全部流水/ });
    expect(allAccountsButton).toBeInTheDocument();
    expect(within(allAccountsButton).getByText("299 条").closest(".bank-account-count-chip")).toHaveClass("bank-account-title-count");
    expect(within(allAccountsButton).getByText("全部").closest(".bank-account-identity")).toBeInTheDocument();
    expect(within(allAccountsButton).getByText("130,500.50")).toHaveClass("bank-account-secondary-balance");
    const icbcAccountButton = within(accountList).getByRole("button", { name: /工商银行 6386/ });
    expect(within(icbcAccountButton).getByText("299 条").closest(".bank-account-count-chip")).toHaveClass("bank-account-title-count");
    expect(within(icbcAccountButton).getByText("299 条").closest(".bank-account-title-row")).toHaveClass("bank-account-title-row");
    expect(within(icbcAccountButton).getByText("工商银行").closest(".bank-account-identity")).toContainElement(within(icbcAccountButton).getByText("6386"));
    expect(within(icbcAccountButton).getByText("130,500.50")).toHaveClass("bank-account-secondary-balance");
    expect(accountList.querySelectorAll(".bank-account-divider")).toHaveLength(2);

    const table = await within(page).findByRole("table", { name: "交易流水" });
    const columnHeaders = within(table).getAllByRole("columnheader").map((header) => header.textContent ?? "");
    expect(columnHeaders).toEqual([
      "对方户名",
      "类型",
      "金额",
      "余额",
      "用途/交易用途",
      "摘要",
      "备注/附言/客户附言",
    ]);
    expect(within(table).queryByRole("columnheader", { name: "交易时间" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "操作" })).not.toBeInTheDocument();
    expect(table.closest(".bank-transaction-grid")).toHaveClass("bank-transaction-grid-readable");
    expect(await within(table).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    const tradeTimeChip = within(table).getByText("2026-05-01 10:30:00").closest(".bank-trade-time-chip");
    expect(within(table).queryByText("2026-05-01 10:30:00+08:00")).not.toBeInTheDocument();
    expect(within(table).getByText("2026-05-01 10:30:00")).toHaveClass("MuiChip-label");
    expect(tradeTimeChip).toHaveClass("bank-trade-time-chip-full");
    expect(tradeTimeChip).toHaveClass("bank-chip-auto-size");
    expect(tradeTimeChip?.closest(".bank-relation-time-row")).not.toBeNull();
    expect(tradeTimeChip?.closest(".bank-relation-chip-row")).toBeNull();
    expect(within(table).getByText("有oa").closest(".bank-relation-tag")).toHaveClass("bank-relation-tag-has");
    expect(within(table).getByText("无发票").closest(".bank-relation-tag")).toHaveClass("bank-relation-tag-none");
    expect(within(table).getByText("有oa").closest(".bank-relation-chip-row")?.previousElementSibling).toHaveClass("bank-relation-time-row");
    expect(within(table).getByText("收").closest(".direction-tag")).toHaveClass("bank-direction-tag-centered");
    expect(within(table).getByText("收").closest(".direction-tag")).toHaveClass("bank-chip-auto-size");
    expect(within(table).getByText("工商银行 6386")).toHaveClass("MuiChip-label");
    expect(within(table).getByText("工商银行 6386").closest(".bank-source-chip")).toHaveClass("bank-chip-auto-size");
    expect(within(table).getByText("货款")).toBeInTheDocument();
    expect(within(table).getByText("项目回款")).toBeInTheDocument();
    expect(within(page).getByText(exactTextContent("公司暂借款：待还款 2")).closest(".bank-category-tag")).toHaveClass("bank-chip-auto-size");
    expect(within(page).queryByText("未保存 0")).not.toBeInTheDocument();
    expect(within(page).getByText("每页行数")).toBeInTheDocument();
  });

  test("renders sidebar balances with the positive balance treatment", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    const accountSummary = within(page).getByText("总余额").closest(".bank-account-summary");
    expect(accountSummary).not.toBeNull();
    expect(within(accountSummary as HTMLElement).getByText("130,500.50")).toHaveClass("bank-balance-value");
    const icbcAccount = within(page).getByRole("button", { name: /工商银行 6386/ });
    expect(within(icbcAccount).getByText("130,500.50")).toHaveClass("bank-balance-value");
  });

  test("uses Chinese labels for table pagination and exposes keyword search", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    expect(within(page).getByText("每页行数")).toBeInTheDocument();
    expect(within(page).getByText("1-100 / 299")).toBeInTheDocument();
    expect(within(page).getByText("1-100 / 299").closest(".bank-transaction-pagination")).toBeInTheDocument();
    expect(within(page).getByPlaceholderText("搜索流水")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /筛选器/ })).not.toBeInTheDocument();
  });

  test("keeps pagination outside the table scroll area", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-transaction-table-container\s*\{[^}]*flex:\s*1 1 0[^}]*overflow-y:\s*auto/s);
    expect(source).toMatch(/\.bank-transaction-pagination\.MuiTablePagination-root\s*\{[^}]*flex:\s*0 0 auto[^}]*border-top:\s*1px solid var\(--bank-border-subtle\)/s);
  });

  test("formats the internal transfer tooltip as structured rows", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-internal-transfer-tooltip\s*\{[^}]*max-width:\s*360px/s);
    expect(source).toMatch(/\.bank-internal-transfer-tooltip-grid\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*52px minmax\(0,\s*1fr\)/s);
    expect(source).toMatch(/\.bank-internal-transfer-tooltip-value\s*\{[^}]*overflow-wrap:\s*anywhere/s);
  });

  test("shows read-only auto category and keeps manual category controls out of bank details", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    const table = await within(page).findByRole("table", { name: "交易流水" });
    expect(within(table).getByRole("columnheader", { name: "类型" })).toBeInTheDocument();
    expect(await within(table).findByText("工资")).toBeInTheDocument();
    expect(within(table).queryByLabelText("bank-detail-001 类型")).not.toBeInTheDocument();
    expect(within(table).queryByText("自动")).not.toBeInTheDocument();
    expect(await within(page).findByText(exactTextContent("公司暂借款：待还款 2"))).toBeInTheDocument();
    expect(within(page).getByText("工资 1")).toBeInTheDocument();
    expect(within(page).getByText("内部往来款 2")).toBeInTheDocument();
    expect(within(page).getByText(exactTextContent("质保金：待收款 1"))).toBeInTheDocument();
    expect(within(page).queryByText(/未保存/)).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "保存分类" })).not.toBeInTheDocument();
  });

  test("shows counterpart transaction details when hovering internal transfer tag", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.type(within(page).getByPlaceholderText("搜索流水"), "内部转账");
    const table = await within(page).findByRole("table", { name: "交易流水" });
    const internalTransferTag = (await within(table).findAllByText("内部往来款"))[0];

    await user.hover(internalTransferTag);

    const tooltip = await screen.findByRole("tooltip", { name: /对应内部往来流水/ });
    expect(within(tooltip).getByText("2026-04-03 12:00:00")).toBeInTheDocument();
    expect(within(tooltip).getByText("建设银行 1410")).toBeInTheDocument();
    expect(within(tooltip).getByText("13,000.00")).toBeInTheDocument();
    expect(within(tooltip).getByText("云南溯源科技有限公司工商银行账户")).toBeInTheDocument();
  });

  test("opens automatic tag rules drawer from the page toolbar", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));

    expect(await screen.findByRole("dialog", { name: "自动标签规则" })).toBeInTheDocument();
    expect(screen.getByText("优先级 0")).toBeInTheDocument();
    expect(screen.getByText("内部往来款")).toBeInTheDocument();
    const rulesRequest = requestUrls(fetchMock, "/api/bank-details/auto-tag-rules").at(-1);
    expect(rulesRequest?.pathname).toBe("/api/bank-details/auto-tag-rules");
  });

  test("saving automatic tag rules refreshes bank details", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      bankDetailTransactionReadModelStatuses: ["refreshing", "refreshing", "fresh"],
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await user.click(await within(drawer).findByRole("button", { name: "展开 工资" }));
    await waitFor(() => {
      expect(within(drawer).getAllByDisplayValue("工资").length).toBeGreaterThan(0);
    });
    const labelInputs = within(drawer).getAllByLabelText("标签名称", { selector: "input" });
    await user.clear(labelInputs[1]);
    await user.type(labelInputs[1], "人员薪酬");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getAllByText("规则已保存，银行明细正在刷新。").length).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    await waitFor(() => {
      expect(screen.getAllByText("规则已保存，银行明细已刷新。").length).toBeGreaterThan(0);
    }, { timeout: 2500 });
    const saveCall = fetchMock.mock.calls.find(([input, init]) => (
      new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules"
      && init?.method === "PUT"
    ));
    expect(saveCall).toBeTruthy();
    expect(JSON.parse(String(saveCall?.[1]?.body || "{}")).refresh_scope).toEqual({
      date_from: "2026-01-01",
      date_to: "2026-12-31",
    });
  });

  test("keeps the read-model refresh banner stable while retaining the last fresh rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      bankDetailAccountReadModelStatuses: ["refreshing", "refreshing", "refreshing"],
      bankDetailTransactionReadModelStatuses: ["fresh"],
      bankDetailRefreshingTransactionsEmpty: true,
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await user.click(await within(drawer).findByRole("button", { name: "展开 工资" }));
    await waitFor(() => {
      expect(within(drawer).getAllByDisplayValue("工资").length).toBeGreaterThan(0);
    });
    const labelInputs = within(drawer).getAllByLabelText("标签名称", { selector: "input" });
    await user.clear(labelInputs[1]);
    await user.type(labelInputs[1], "人员薪酬");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });

    expect(screen.getByText("银行明细读模型正在刷新。")).toBeInTheDocument();
    expect(screen.queryByText("规则已保存，银行明细已刷新。")).not.toBeInTheDocument();
    expect(within(page).getByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).queryByText("当前时间范围内没有流水。")).not.toBeInTheDocument();
  });

  test("uncategorized rows display a dash in the narrow type column", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("工资");
    expect(within(page).getByText("未分类 295")).toBeInTheDocument();
    expect(within(page).queryByText("无 295")).not.toBeInTheDocument();

    await user.type(within(page).getByPlaceholderText("搜索流水"), "普通供应商");
    const table = await within(page).findByRole("table", { name: "交易流水" });
    expect(await within(table).findByText("普通供应商")).toBeInTheDocument();
    expect(table.querySelector(".bank-auto-type-empty")).toHaveTextContent("-");
    expect(within(page).getByText("未分类 1")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "保存分类" })).not.toBeInTheDocument();
  });

  test("switches accounts without dirty-category prompts", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    await user.click(within(page).getByRole("button", { name: /交通银行 3847/ }));
    await within(page).findByText("当前时间范围内没有流水。");
    expect(within(page).getByRole("button", { name: /交通银行 3847/ })).toHaveAttribute("aria-current", "true");
    expect(screen.queryByRole("dialog", { name: "有未保存的分类变动" })).not.toBeInTheDocument();
    expect(within(page).queryByText(/未保存/)).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /工商银行 6386/ }));
    expect(await within(page).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /工商银行 6386/ })).toHaveAttribute("aria-current", "true");
  });

  test("selecting account and filters request accounts and transactions with the same date range", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.click(within(page).getByRole("button", { name: /交通银行 3847/ }));

    expect(await within(page).findByText("当前时间范围内没有流水。")).toBeInTheDocument();
    expect(within(page).getByLabelText(/交通银行 3847 余额/)).toHaveTextContent("余额为空");
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: "上月" }));
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBe("2026-04-01");
      expect(accountRequest?.searchParams.get("date_to")).toBe("2026-04-30");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-04-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-04-30");
    });
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: /2026-04-01 - 2026-04-30/ }));
    await user.clear(screen.getByLabelText("年月筛选"));
    await user.type(screen.getByLabelText("年月筛选"), "2026-03");
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBe("2026-03-01");
      expect(accountRequest?.searchParams.get("date_to")).toBe("2026-03-31");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-03-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-03-31");
    });

    fireEvent.blur(screen.getByLabelText("开始日期"), { target: { value: "2026-02-01" } });
    fireEvent.blur(screen.getByLabelText("结束日期"), { target: { value: "2026-02-15" } });
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBe("2026-02-01");
      expect(accountRequest?.searchParams.get("date_to")).toBe("2026-02-15");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-02-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-02-15");
    });
  });

  test("shows server total and requests the second page with the default page size", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    expect(within(page).getAllByText("299 条").length).toBeGreaterThan(0);
    expect(within(page).queryByText("1 / 3 页")).not.toBeInTheDocument();
    expect(within(page).getByText("1-100 / 299")).toBeInTheDocument();

    await user.click(within(page).getByLabelText("下一页"));

    await waitFor(() => {
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(transactionRequest?.searchParams.get("page")).toBe("2");
      expect(transactionRequest?.searchParams.get("page_size")).toBe("100");
    });

    await user.click(within(page).getByRole("button", { name: "上月" }));

    await waitFor(() => {
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-04-01");
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
      expect(transactionRequest?.searchParams.get("page_size")).toBe("100");
    });
  });

  test("searches current account and date range on the server before pagination", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    await user.click(within(page).getByRole("button", { name: /工商银行 6386/ }));
    await user.click(within(page).getByLabelText("下一页"));
    await waitFor(() => {
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(transactionRequest?.searchParams.get("account_key")).toBe("icbc:6386");
      expect(transactionRequest?.searchParams.get("page")).toBe("2");
    });

    await user.type(within(page).getByPlaceholderText("搜索流水"), "跨页目标");

    await waitFor(() => {
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(transactionRequest?.searchParams.get("account_key")).toBe("icbc:6386");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-01-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-12-31");
      expect(transactionRequest?.searchParams.get("keyword")).toBe("跨页目标");
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
      expect(transactionRequest?.searchParams.get("page_size")).toBe("100");
    });
    expect(await within(page).findByText("跨页目标供应商")).toBeInTheDocument();
    expect(within(page).getByText("1-1 / 1")).toBeInTheDocument();
    expect(within(page).getByText("手续费 1")).toBeInTheDocument();
    expect(within(page).queryByText("工资 1")).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /工商银行 6386.*299 条/ })).toBeInTheDocument();
  });

  test("exports all banks or the selected account with the current filters", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const originalCreateObjectUrl = window.URL.createObjectURL;
    const originalRevokeObjectUrl = window.URL.revokeObjectURL;
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:bank-export") });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    await user.click(within(page).getByRole("button", { name: "导出" }));
    await user.click(await screen.findByRole("menuitem", { name: "导出全部银行" }));

    await waitFor(() => {
      const exportRequest = requestUrls(fetchMock, "/api/bank-details/transactions/export").at(-1);
      expect(exportRequest?.searchParams.get("mode")).toBe("all");
      expect(exportRequest?.searchParams.get("date_from")).toBe("2026-01-01");
      expect(exportRequest?.searchParams.get("date_to")).toBe("2026-12-31");
      expect(exportRequest?.searchParams.get("account_key")).toBeNull();
    });
    expect(clickSpy).toHaveBeenCalled();
    expect(await within(page).findByText("已开始下载")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: /工商银行 6386/ }));
    await user.type(within(page).getByPlaceholderText("搜索流水"), "跨页目标");
    await waitFor(() => {
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(transactionRequest?.searchParams.get("keyword")).toBe("跨页目标");
    });
    await user.click(within(page).getByRole("button", { name: "导出" }));
    await user.click(await screen.findByRole("menuitem", { name: "导出当前账户" }));

    await waitFor(() => {
      const exportRequest = requestUrls(fetchMock, "/api/bank-details/transactions/export").at(-1);
      expect(exportRequest?.searchParams.get("mode")).toBe("account");
      expect(exportRequest?.searchParams.get("account_key")).toBe("icbc:6386");
      expect(exportRequest?.searchParams.get("keyword")).toBe("跨页目标");
    });

    clickSpy.mockRestore();
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: originalCreateObjectUrl });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectUrl });
  });

  test("refetches bank detail data when workbench relation updates without local tag patching", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    await screen.findByText("云南溯源科技有限公司");
    const initialAccountRequests = requestUrls(fetchMock, "/api/bank-details/accounts").length;
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    act(() => {
      window.dispatchEvent(new CustomEvent("workbenchRelationUpdated"));
    });

    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/accounts").length).toBeGreaterThan(initialAccountRequests);
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
  });

  test("refetches bank detail data when bank detail tag settings update", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    await screen.findByText("云南溯源科技有限公司");
    const initialAccountRequests = requestUrls(fetchMock, "/api/bank-details/accounts").length;
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    act(() => {
      window.dispatchEvent(new CustomEvent("finops:bank-transaction-tags-updated", { detail: { version: 2 } }));
    });

    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/accounts").length).toBeGreaterThan(initialAccountRequests);
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
  });

  test("refetches bank detail data on focus when bank tag version fallback detects a missed update", async () => {
    vi.stubGlobal("BroadcastChannel", undefined);
    let tagVersion = 1;
    const localStorageStore = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => localStorageStore.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        localStorageStore.set(key, value);
      }),
      removeItem: vi.fn((key: string) => {
        localStorageStore.delete(key);
      }),
      clear: vi.fn(() => {
        localStorageStore.clear();
      }),
    });
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
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/bank-details/transactions") {
        return new Response(JSON.stringify({
          rows: [
            {
              id: `bank-detail-version-${tagVersion}`,
              trade_time: "2026-05-01 10:30:00",
              counterparty_name: `版本${tagVersion}供应商`,
              direction: "income",
              direction_label: "收",
              amount: "20000.00",
              balance: "130500.50",
              summary: "项目回款",
              purpose: "货款",
              bank_name: "工商银行",
              account_last4: "6386",
              effective_category_code: "fee",
              effective_category_label: "手续费",
              effective_category_path: ["自动识别", "手续费"],
              effective_category_source: "auto",
            },
          ],
          category_counts: { fee: 1, uncategorized: 0 },
          pagination: { page: 1, page_size: 100, total: 1 },
          tag_dictionary: {
            version: tagVersion,
            tags: [{ code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" }],
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      throw new Error(`Unhandled fetch mock for ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderBankDetailsPage();
    expect(await screen.findByText("版本1供应商")).toBeInTheDocument();
    const initialTransactionRequests = requestUrls(fetchMock as ReturnType<typeof installMockApiFetch>, "/api/bank-details/transactions").length;

    tagVersion = 2;
    window.localStorage.setItem("finops.bankTransactionTags.version", "2");
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() => {
      expect(requestUrls(fetchMock as ReturnType<typeof installMockApiFetch>, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    expect(await screen.findByText("版本2供应商")).toBeInTheDocument();
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
