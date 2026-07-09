import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, vi } from "vitest";

import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import type { SessionPayload } from "../features/session/api";
import BankDetailsPage from "../pages/BankDetailsPage";
import { installMockApiFetch } from "./apiMock";
import { renderAuthenticatedAppAt } from "./renderHelpers";

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
    <SessionContext.Provider value={staticSession}>
      <GlobalOperationOverlayProvider>
        <PageSessionStateProvider>
          <BankDetailsPage />
        </PageSessionStateProvider>
      </GlobalOperationOverlayProvider>
    </SessionContext.Provider>,
  );
}

function requestUrls(fetchMock: ReturnType<typeof installMockApiFetch>, pathname: string) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === pathname);
}

function operationBarrierRequests(fetchMock: ReturnType<typeof installMockApiFetch>) {
  return fetchMock.mock.calls
    .filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST";
    })
    .map(([, init]) => JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
}

function findTransactionRequest(
  fetchMock: ReturnType<typeof installMockApiFetch>,
  predicate: (url: URL) => boolean,
) {
  return requestUrls(fetchMock, "/api/bank-details/transactions").find(predicate);
}

function exactTextContent(text: string) {
  return (_content: string, element: Element | null) => (
    element?.textContent === text
    && Array.from(element.children).every((child) => child.textContent !== text)
  );
}

async function openCategoryFilterPanel(user: ReturnType<typeof userEvent.setup>, page: HTMLElement) {
  const trigger = getCategoryFilterTrigger(page);
  await user.click(trigger);
  return screen.findByRole("menu", { name: "银行明细标签筛选" });
}

function getCategoryFilterTrigger(page: HTMLElement) {
  return within(page).getByRole("button", { name: /^标签筛选：/ });
}

async function findBankTransactionSurface(page: HTMLElement) {
  const scope = within(page);
  const currentTable = scope.queryByRole("table", { name: "交易流水" });
  if (currentTable) {
    return currentTable;
  }
  const currentGrid = scope.queryByRole("grid", { name: "交易流水" });
  if (currentGrid) {
    return currentGrid;
  }
  try {
    return await scope.findByRole("table", { name: "交易流水" }, { timeout: 500 });
  } catch {
    return scope.findByRole("grid", { name: "交易流水" });
  }
}

async function editRuleLabelInDrawer(user: ReturnType<typeof userEvent.setup>, drawer: HTMLElement, currentLabel: string, primary: string, sub: string) {
  const [_currentPrimary, currentSub = ""] = currentLabel.split(" / ");
  const currentInput = await within(drawer).findByDisplayValue(currentSub || _currentPrimary);
  const row = currentInput.closest("tr");
  if (!(row instanceof HTMLElement)) {
    throw new Error(`rule row for ${currentLabel} not found`);
  }
  const primaryInput = within(row).queryByLabelText(/主标签$/, { selector: "input" })
    ?? within(drawer).getByDisplayValue(_currentPrimary);
  const subInput = within(row).getByLabelText(/子标签$/, { selector: "input" });
  await user.clear(primaryInput);
  await user.type(primaryInput, primary);
  await user.clear(subInput);
  if (sub) {
    await user.type(subInput, sub);
  }
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Bank details page", () => {
  test("targets project table, menu, date, drawer and dialog primitives", () => {
    const source = readFileSync(resolve(process.cwd(), "src/pages/BankDetailsPage.tsx"), "utf8");
    const drawerSource = readFileSync(resolve(process.cwd(), "src/features/bankDetails/AutoTagRulesDrawer.tsx"), "utf8");
    const tagSource = readFileSync(resolve(process.cwd(), "src/features/bankDetails/BankCategoryTag.tsx"), "utf8");

    expect(source).toContain("FinanceTable");
    expect(source).not.toContain("@mui/x-data-grid");
    expect(source).not.toContain("@mui/material/Table");
    expect(source).not.toContain("@mui/material/TablePagination");
    expect(source).not.toContain("@mui/x-date-pickers");
    expect(source).not.toContain("@mui/material/Popover");
    expect(source).not.toContain("@mui/material/Popper");
    expect(source).not.toContain("@mui/material/Menu");
    expect(source).not.toContain("<DataGrid");
    expect(source).not.toContain("disableVirtualization");
    expect(source).not.toContain("getRowHeight={() => \"auto\"}");
    expect(source).not.toContain("role=\"tree\"");
    expect(source).not.toContain("bank-category-tree");
    expect(source).toContain("pageSizeOptions={[25, 50, 100]}");
    expect(drawerSource).toContain("AppDrawer");
    expect(drawerSource).toContain("AppDialog");
    expect(drawerSource).not.toContain("@mui/material/Drawer");
    expect(drawerSource).not.toContain("@mui/material/Dialog");
    expect(source).toContain("@heroui/react");
    expect(source).toContain("Chip");
    expect(tagSource).toContain("@heroui/react");
    expect(tagSource).toContain("Chip");
    expect(tagSource).not.toContain("@mui/material/Chip");
    expect(tagSource).not.toContain("@mui/material/Tooltip");
  });

  test("loads all accounts by default and its transactions", async () => {
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    expect(within(page).getByRole("heading", { name: "银行明细" })).toBeInTheDocument();
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
    const user = userEvent.setup();
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

    const table = await findBankTransactionSurface(page);
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
    const tradeTimeText = within(table).getByText("2026-05-01 10:30:00").closest(".bank-trade-time-text");
    expect(within(table).queryByText("2026-05-01 10:30:00+08:00")).not.toBeInTheDocument();
    expect(tradeTimeText?.closest(".bank-counterparty-meta-row")).not.toBeNull();
    expect(tradeTimeText?.closest(".bank-relation-chip-row")).toBeNull();
    expect(within(table).getByText("候选oa").closest(".bank-relation-tag")).toHaveClass("bank-relation-tag-candidate");
    expect(within(table).getByText("候选发票").closest(".bank-relation-tag")).toHaveClass("bank-relation-tag-candidate");
    expect(within(table).getByText("候选oa").closest(".bank-counterparty-meta-row")?.querySelector(".bank-trade-time-text")).not.toBeNull();
    expect(within(table).getByText("收").closest(".direction-tag")).toHaveClass("bank-direction-tag-centered");
    expect(within(table).getByText("收").closest(".direction-tag")).toHaveClass("bank-chip-auto-size");
    expect(within(table).getByText("工商银行 6386").closest(".bank-source-chip")).toHaveClass("bank-chip-auto-size");
    expect(within(table).getByText("货款")).toBeInTheDocument();
    expect(within(table).getByText("项目回款")).toBeInTheDocument();
    expect(within(page).queryByText(exactTextContent("公司暂借款：待还款 2"))).not.toBeInTheDocument();
    const categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "公司暂借款 2" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "待还款 2" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
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
    expect(within(page).queryByText(/标签筛选：/)).not.toBeInTheDocument();
  });

  test("keeps pagination outside the table scroll area", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-transaction-table-container\s*\{[^}]*flex:\s*1 1 0[^}]*overflow-y:\s*auto/s);
    expect(source).toMatch(/\.bank-transaction-pagination\s*\{[^}]*flex:\s*0 0 auto[^}]*border-top:\s*1px solid var\(--bank-border-subtle\)/s);
  });

  test("uses a dense three-column grouped category filter layout", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-category-filter-icon-button\s*\{[^}]*width:\s*28px[^}]*height:\s*28px/s);
    expect(source).toMatch(/\.bank-category-filter-panel\s*\{[^}]*width:\s*min\(640px,\s*calc\(100vw - 64px\)\)/s);
    expect(source).not.toMatch(/\.bank-category-filter-panel\s*\{[^}]*max-height:/s);
    expect(source).not.toMatch(/\.bank-category-filter-list\s*\{[^}]*max-height:/s);
    expect(source).not.toMatch(/\.bank-category-filter-list\s*\{[^}]*overflow-y:\s*auto/s);
    expect(source).toMatch(/\.bank-category-filter-sections\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s);
    expect(source).not.toMatch(/\.bank-category-filter-sections\s*\{[^}]*column-count:/s);
    expect(source).toMatch(/\.bank-category-filter-group\s*\{[^}]*background:\s*var\(--bank-category-group-bg\)/s);
    expect(source).toMatch(/\.bank-category-filter-tone-0\s*\{[^}]*--bank-category-group-bg:/s);
    expect(source).toMatch(/\.bank-category-filter-label\s*\{[^}]*font-size:\s*9px/s);
    expect(source).toMatch(/\.bank-category-filter-child-row \.bank-category-filter-label\s*\{[^}]*font-size:\s*8\.5px/s);
    expect(source).toMatch(/\.bank-category-filter-count\s*\{[^}]*font-size:\s*8px/s);
    expect(source).toMatch(/\.bank-category-filter-hierarchy-group::before\s*\{/);
    expect(source).toMatch(/\.bank-category-filter-hierarchy-item::after\s*\{/);
    expect(source).not.toMatch(/\.bank-category-filter-group\s*\{[^}]*border:\s*1px[^}]*background:/s);
  });

  test("formats the internal transfer tooltip as structured rows", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-internal-transfer-tooltip\s*\{[^}]*max-width:\s*360px/s);
    expect(source).toMatch(/\.bank-internal-transfer-tooltip-grid\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*52px minmax\(0,\s*1fr\)/s);
    expect(source).toMatch(/\.bank-internal-transfer-tooltip-value\s*\{[^}]*overflow-wrap:\s*anywhere/s);
  });

  test("shows read-only auto category and keeps manual category controls out of bank details", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    const table = await findBankTransactionSurface(page);
    expect(within(table).getByRole("columnheader", { name: "类型" })).toBeInTheDocument();
    expect(await within(table).findByText("费用 / 工资")).toBeInTheDocument();
    expect(within(table).queryByLabelText("bank-detail-001 类型")).not.toBeInTheDocument();
    expect(within(table).queryByText("自动")).not.toBeInTheDocument();
    expect(within(page).queryByText(exactTextContent("公司暂借款：待还款 2"))).not.toBeInTheDocument();
    const categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "费用 1" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "工资 1" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "内部往来款 2" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "质保金 1" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "待收款 1" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(within(page).queryByText(/未保存/)).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "保存分类" })).not.toBeInTheDocument();
  });

  test("shows counterpart transaction details when hovering internal transfer tag", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.type(within(page).getByPlaceholderText("搜索流水"), "内部转账");
    const table = await findBankTransactionSurface(page);
    const internalTransferTag = (await within(table).findAllByText("内部往来款"))[0];

    await user.hover(internalTransferTag);

    const tooltip = await screen.findByRole("tooltip", { name: /对应内部往来流水/ });
    expect(within(tooltip).getByText("2026-04-03 12:00:00")).toBeInTheDocument();
    expect(within(tooltip).getByText("建设银行 1410")).toBeInTheDocument();
    expect(within(tooltip).getByText("13,000.00")).toBeInTheDocument();
    expect(within(tooltip).getByText("云南溯源科技有限公司工商银行账户")).toBeInTheDocument();
  });

  test("shows category hierarchy in the compact grouped tag filter panel", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    expect(within(page).queryByText(exactTextContent("费用 / 工资 1"))).not.toBeInTheDocument();

    let categoryPanel = await openCategoryFilterPanel(user, page);
    const feeRoot = within(categoryPanel).getByRole("menuitem", { name: "费用 1" });
    const salaryChild = within(categoryPanel).getByRole("menuitem", { name: "工资 1" });
    expect(feeRoot).toHaveAttribute("aria-current", "false");
    expect(feeRoot).toHaveAttribute("data-level", "primary");
    expect(salaryChild).toHaveAttribute("data-level", "child");
    expect(salaryChild).toHaveClass("bank-category-filter-hierarchy-item");
    const salaryGroup = salaryChild.closest(".bank-category-filter-hierarchy-group");
    expect(salaryGroup).not.toBeNull();
    expect(salaryGroup).toContainElement(feeRoot);
    expect(Array.from(salaryGroup?.classList ?? []).some((className) => className.startsWith("bank-category-filter-tone-"))).toBe(true);

    await user.click(feeRoot);

    await waitFor(() => {
      const transactionRequest = findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_primary_label") === "费用"
        && url.searchParams.get("category_code") === null
        && url.searchParams.get("page") === "1"
      ));
      expect(transactionRequest).toBeDefined();
      expect(transactionRequest?.searchParams.get("category_code")).toBeNull();
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
    });
    expect(within(page).getByRole("button", { name: /标签筛选：费用 1/ })).toBeInTheDocument();
    categoryPanel = screen.getByRole("menu", { name: "银行明细标签筛选" });
    expect(categoryPanel).toBeInTheDocument();

    const selectedFeeRoot = within(categoryPanel).getByRole("menuitem", { name: "费用 1" });
    expect(selectedFeeRoot).toHaveAttribute("aria-current", "true");
    await user.click(within(categoryPanel).getByRole("menuitem", { name: "工资 1" }));

    await waitFor(() => {
      const transactionRequest = findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_code") === "salary"
        && url.searchParams.get("category_primary_label") === null
        && url.searchParams.get("category_sub_label") === null
        && url.searchParams.get("page") === "1"
      ));
      expect(transactionRequest).toBeDefined();
      expect(transactionRequest?.searchParams.get("category_primary_label")).toBeNull();
      expect(transactionRequest?.searchParams.get("category_sub_label")).toBeNull();
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
    });
    expect(within(page).getByRole("button", { name: /标签筛选：费用 \/ 工资 1/ })).toBeInTheDocument();
    categoryPanel = screen.getByRole("menu", { name: "银行明细标签筛选" });
    expect(categoryPanel).toBeInTheDocument();

    await user.click(within(categoryPanel).getByRole("menuitem", { name: "未分类 295" }));

    await waitFor(() => {
      const transactionRequest = findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_code") === "uncategorized"
        && url.searchParams.get("category_primary_label") === null
        && url.searchParams.get("page") === "1"
      ));
      expect(transactionRequest).toBeDefined();
      expect(transactionRequest?.searchParams.get("category_primary_label")).toBeNull();
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
    });
    expect(within(page).getByRole("button", { name: /标签筛选：未分类 295/ })).toBeInTheDocument();
    expect(screen.getByRole("menu", { name: "银行明细标签筛选" })).toBeInTheDocument();
  });

  test("opens the fixed category filter icon by click only and keeps it open on pointer leave", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const trigger = getCategoryFilterTrigger(page);
    expect(trigger.closest(".bank-category-filter-float")).toBeInTheDocument();

    await user.hover(trigger);
    expect(screen.queryByRole("menu", { name: "银行明细标签筛选" })).not.toBeInTheDocument();

    await user.click(trigger);
    const panel = await screen.findByRole("menu", { name: "银行明细标签筛选" });
    expect(panel).toBeInTheDocument();

    await user.unhover(trigger);
    await user.hover(panel);
    await user.unhover(panel);
    await new Promise((resolve) => window.setTimeout(resolve, 200));
    expect(screen.getByRole("menu", { name: "银行明细标签筛选" })).toBeInTheDocument();

    await user.click(trigger);
    await waitFor(() => {
      expect(screen.queryByRole("menu", { name: "银行明细标签筛选" })).not.toBeInTheDocument();
    });
  });

  test("keeps category menu counts based on the unfiltered snapshot after selecting uncategorized", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    let categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "全部 299" })).toBeInTheDocument();
    await user.click(within(categoryPanel).getByRole("menuitem", { name: "未分类 295" }));

    await waitFor(() => {
      expect(findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_code") === "uncategorized"
      ))).toBeDefined();
    });
    expect(within(page).getByText("1-100 / 295")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /标签筛选：未分类 295/ })).toBeInTheDocument();

    categoryPanel = screen.getByRole("menu", { name: "银行明细标签筛选" });
    expect(within(categoryPanel).getByRole("menuitem", { name: "全部 299" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "未分类 295" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "工资 1" })).toBeInTheDocument();
  });

  test("filters code-only system tags by category code without derived label constraints", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    const categoryPanel = await openCategoryFilterPanel(user, page);
    await user.click(within(categoryPanel).getByRole("menuitem", { name: "内部往来款 2" }));

    await waitFor(() => {
      const transactionRequest = findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_code") === "internal_transfer"
        && url.searchParams.get("category_primary_label") === null
        && url.searchParams.get("category_sub_label") === null
        && url.searchParams.get("page") === "1"
      ));
      expect(transactionRequest).toBeDefined();
      expect(transactionRequest?.searchParams.get("category_primary_label")).toBeNull();
      expect(transactionRequest?.searchParams.get("category_sub_label")).toBeNull();
      expect(transactionRequest?.searchParams.get("page")).toBe("1");
    });
    expect(await within(page).findByText("云南溯源科技有限公司建设银行账户")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /标签筛选：内部往来款 2/ })).toBeInTheDocument();
  });

  test("opens automatic tag rules drawer from the page toolbar", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    expect(drawer).toBeInTheDocument();
    expect(screen.getByText("内部往来款").closest("tr")).toHaveTextContent("1");
    expect(screen.getByText("内部往来款")).toBeInTheDocument();
    const rulesRequest = requestUrls(fetchMock, "/api/bank-details/auto-tag-rules").at(-1);
    expect(rulesRequest?.pathname).toBe("/api/bank-details/auto-tag-rules");
  });

  test("saving automatic tag rules refreshes bank details", async () => {
    const user = userEvent.setup();
    const baseFetchMock = installMockApiFetch({
      bankDetailTransactionReadModelStatuses: ["refreshing", "refreshing", "fresh"],
    });
    let releaseBarrier: (() => void) | null = null;
    const barrierGate = new Promise<void>((resolve) => {
      releaseBarrier = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST") {
        await barrierGate;
        return new Response(JSON.stringify({
          status: "fresh",
          fresh: true,
          targets: [],
          blocked_targets: [],
          refreshing_targets: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return baseFetchMock(input, init);
    }) as ReturnType<typeof installMockApiFetch>;
    vi.stubGlobal("fetch", fetchMock);
    const autoTagRulesListener = vi.fn();
    window.addEventListener("bankAutoTagRulesUpdated", autoTagRulesListener);
    renderBankDetailsPage();

    try {
      const page = await screen.findByTestId("bank-details-page");
      await within(page).findByText("云南溯源科技有限公司");
      const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

      await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
      const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
      await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "费用", "规则刷新测试");
      await user.click(within(drawer).getByRole("button", { name: "保存" }));

      await waitFor(() => {
        expect(operationBarrierRequests(fetchMock).at(-1)).toMatchObject({
          targets: [
            { read_model_key: "bank_detail", scope_key: "2026-05" },
          ],
        });
      });
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBe(initialTransactionRequests);
      releaseBarrier?.();

      await waitFor(() => {
        expect(autoTagRulesListener).toHaveBeenCalled();
        expect(autoTagRulesListener.mock.calls[0][0].detail).toEqual(expect.objectContaining({
          version: 2,
          source: "bank_details_auto_tag_rules",
          action: "saved",
        }));
      });
      await waitFor(() => {
        expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
      });
      await waitFor(() => {
        expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests + 2);
        expect(screen.getAllByText("规则已保存，银行明细已刷新。").length).toBeGreaterThan(0);
      }, { timeout: 4000 });
      const saveCall = fetchMock.mock.calls.find(([input, init]) => (
        new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules"
        && init?.method === "PUT"
      ));
      expect(saveCall).toBeTruthy();
      expect(JSON.parse(String(saveCall?.[1]?.body || "{}")).refresh_scope).toEqual({
        date_from: "2026-01-01",
        date_to: "2026-12-31",
      });
    } finally {
      releaseBarrier?.();
      window.removeEventListener("bankAutoTagRulesUpdated", autoTagRulesListener);
    }
  });

  test("does not report saved automatic tag rules as failed when post-save freshness sync is blocked", async () => {
    const user = userEvent.setup();
    const baseFetchMock = installMockApiFetch();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { targets?: Array<Record<string, unknown>> };
        const requestedTarget = body.targets?.[0] ?? { read_model_key: "bank_detail", scope_key: "2026-05" };
        const blockedTarget = {
          read_model_key: String(requestedTarget.read_model_key ?? "bank_detail"),
          scope_type: "snapshot",
          scope_key: String(requestedTarget.scope_key ?? "2026-05"),
          status: "blocked",
          fresh: false,
          blocking: true,
          raw_status: "failed",
          reason: "read_model_dirty_scope_failed",
          last_error: "bank_detail_refresh_pending",
        };
        return new Response(JSON.stringify({
          status: "blocked",
          fresh: false,
          targets: [blockedTarget],
          blocked_targets: [blockedTarget],
          refreshing_targets: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return baseFetchMock(input, init);
    }) as ReturnType<typeof installMockApiFetch>;
    vi.stubGlobal("fetch", fetchMock);

    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "费用", "同步阻断测试");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-details/auto-tag-rules" && init?.method === "PUT";
      });
      expect(saveCall).toBeDefined();
    });
    expect(await screen.findByText("规则已保存，后台同步尚未完成，请稍后刷新。")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "操作失败" })).not.toBeInTheDocument();
  });

  test("reapplying automatic tag rules refreshes bank details without saving changes", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      bankDetailTransactionReadModelStatuses: ["refreshing", "fresh"],
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await user.click(within(drawer).getByRole("button", { name: "重新应用规则" }));

    await waitFor(() => {
      expect(
        screen.queryAllByText("已提交重新应用，银行明细正在刷新。").length
        + screen.queryAllByText("重新应用已完成，银行明细已刷新。").length,
      ).toBeGreaterThan(0);
    });
    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    await waitFor(() => {
      expect(screen.getAllByText("重新应用已完成，银行明细已刷新。").length).toBeGreaterThan(0);
    });
    const reapplyCall = fetchMock.mock.calls.find(([input, init]) => (
      new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules/reapply"
      && String(init?.method || "GET").toUpperCase() === "POST"
    ));
    const saveCall = fetchMock.mock.calls.find(([input, init]) => (
      new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules"
      && String(init?.method || "GET").toUpperCase() === "PUT"
    ));
    expect(reapplyCall).toBeTruthy();
    expect(saveCall).toBeFalsy();
  });

  test("retains the last fresh rows while read-model refresh details stay hidden", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      bankDetailAccountReadModelStatuses: ["fresh"],
      bankDetailTransactionReadModelStatuses: ["refreshing", "fresh"],
      bankDetailRefreshingTransactionsEmpty: true,
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "费用", "人员薪酬");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });

    expect(screen.queryByText("银行明细读模型正在刷新，已显示当前可用数据。")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("规则已保存，银行明细已刷新。").length).toBeGreaterThan(0);
    });
    expect(within(page).getByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).queryByText("当前时间范围内没有流水。")).not.toBeInTheDocument();
  });

  test("unmounts bank detail retry timers while away and refetches after route remount", async () => {
    const fetchMock = installMockApiFetch({
      bankDetailInitialAccountReadModelStatus: "fresh",
      bankDetailInitialTransactionReadModelStatus: "refreshing",
    });

    renderAuthenticatedAppAt("/bank-details");

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    fireEvent.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByTestId("bank-details-page")).not.toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(requestUrls(fetchMock, "/api/bank-details/transactions")).toHaveLength(initialTransactionRequests);

    vi.useRealTimers();
    fireEvent.click(screen.getByRole("link", { name: "银行明细" }));
    expect(await screen.findByTestId("bank-details-page")).toBeInTheDocument();

    expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
  });

  test("does not replace a fresh total balance with a stale post-rule-save account payload", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      bankDetailAccountReadModelStatuses: ["stale"],
      bankDetailPostSaveAccountsTotalBalance: "116395.83",
      bankDetailTransactionReadModelStatuses: ["stale", "fresh"],
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findAllByText("130,500.50");

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "费用", "人员薪酬");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input, init]) => (
        new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules"
        && String(init?.method || "GET").toUpperCase() === "PUT"
      ))).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getAllByText("规则已保存，银行明细已刷新。").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("银行明细读模型待刷新，已显示当前可用数据。")).not.toBeInTheDocument();
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);
    expect(within(page).queryAllByText("116,395.83")).toHaveLength(0);
  });

  test("shows existing bank rows while the read-model schema is being upgraded", async () => {
    installMockApiFetch({
      bankDetailInitialAccountReadModelStatus: "schema_mismatch",
      bankDetailInitialTransactionReadModelStatus: "schema_mismatch",
    });
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");

    expect(await within(page).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(page).queryByText("银行明细读模型版本正在升级，已显示当前可用数据。")).not.toBeInTheDocument();
    expect(within(page).queryByText("当前时间范围内没有流水。")).not.toBeInTheDocument();
  });

  test("uncategorized unmatched rows display manual classification choices from active auto tag rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("费用 / 工资");
    let categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "未分类 295" })).toBeInTheDocument();
    expect(within(page).queryByText("无 295")).not.toBeInTheDocument();

    await user.type(within(page).getByPlaceholderText("搜索流水"), "普通供应商");
    const table = await findBankTransactionSurface(page);
    const supplierName = await within(table).findByText("普通供应商");
    const supplierRow = supplierName.closest("tr");
    expect(supplierRow).toBeInstanceOf(HTMLElement);
    expect(within(supplierRow as HTMLElement).queryByRole("button", { name: "待确认" })).not.toBeInTheDocument();
    await user.click(within(supplierRow as HTMLElement).getByRole("button", { name: "待分类" }));

    const primaryMenu = await screen.findByRole("menu", { name: "待分类主标签" });
    const confirmationPanel = primaryMenu.closest(".bank-category-confirmation-panel");
    expect(confirmationPanel).toBeInstanceOf(HTMLElement);
    expect((supplierRow as HTMLElement).contains(confirmationPanel)).toBe(false);
    expect(confirmationPanel?.parentElement).toHaveClass("bank-category-confirmation-popper");
    expect(confirmationPanel?.parentElement?.parentElement).toBe(document.body);
    expect(within(primaryMenu).getByRole("menuitem", { name: "费用" })).toBeInTheDocument();
    expect(within(primaryMenu).queryByRole("menuitem", { name: "质保金" })).not.toBeInTheDocument();
    expect(within(primaryMenu).queryByRole("menuitem", { name: "银行往来款" })).not.toBeInTheDocument();

    await user.click(within(primaryMenu).getByRole("menuitem", { name: "费用" }));
    const childMenu = await screen.findByRole("menu", { name: "费用可选标签" });
    expect(within(childMenu).getByRole("menuitem", { name: "手续费" })).toBeInTheDocument();
    expect(within(childMenu).getByRole("menuitem", { name: "工资" })).toBeInTheDocument();

    await user.click(within(childMenu).getByRole("menuitem", { name: "工资" }));
    expect(requestUrls(fetchMock, "/api/bank-details/transactions/bank-detail-search-filler/category-assignment")).toHaveLength(0);
    const stagedButton = within(supplierRow as HTMLElement).getByRole("button", { name: "费用 / 工资" });
    expect(stagedButton).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-details/transactions/bank-detail-search-filler/category-assignment",
        expect.objectContaining({ body: JSON.stringify({ category_code: "salary" }) }),
      );
    });
    categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "未分类 1" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(within(page).queryByRole("button", { name: "保存分类" })).not.toBeInTheDocument();
  });

  test("manual classification choices update after automatic tag rules are saved", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("费用 / 工资");

    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "薪资社保福利", "人员薪酬");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-details/auto-tag-rules",
        expect.objectContaining({ method: "PUT" }),
      );
    });
    await waitFor(() => {
      expect(screen.getAllByText("规则已保存，银行明细已刷新。").length).toBeGreaterThan(0);
    });
    await user.click(within(drawer).getByRole("button", { name: "关闭自动标签规则抽屉" }));

    await user.type(within(page).getByPlaceholderText("搜索流水"), "普通供应商");
    const table = await findBankTransactionSurface(page);
    const supplierName = await within(table).findByText("普通供应商");
    const supplierRow = supplierName.closest("tr");
    expect(supplierRow).toBeInstanceOf(HTMLElement);

    await user.click(within(supplierRow as HTMLElement).getByRole("button", { name: "待分类" }));
    const primaryMenu = await screen.findByRole("menu", { name: "待分类主标签" });
    expect(within(primaryMenu).getByRole("menuitem", { name: "薪资社保福利" })).toBeInTheDocument();

    await user.click(within(primaryMenu).getByRole("menuitem", { name: "薪资社保福利" }));
    const childMenu = await screen.findByRole("menu", { name: "薪资社保福利可选标签" });
    expect(within(childMenu).getByRole("menuitem", { name: "人员薪酬" })).toBeInTheDocument();
  });

  test("needs-confirmation rows group only matched candidates by primary tag", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.type(within(page).getByPlaceholderText("搜索流水"), "候选供应商");
    const table = await findBankTransactionSurface(page);
    const counterpartyName = await within(table).findByText("候选供应商", { exact: true });
    const row = counterpartyName.closest("tr");
    expect(row).toBeInstanceOf(HTMLElement);

    await user.click(within(row as HTMLElement).getByRole("button", { name: "待确认" }));

    const primaryMenu = await screen.findByRole("menu", { name: "待确认主标签" });
    expect(within(primaryMenu).getByRole("menuitem", { name: "费用" })).toBeInTheDocument();
    expect(within(primaryMenu).queryByRole("menuitem", { name: "质保金" })).not.toBeInTheDocument();

    await user.click(within(primaryMenu).getByRole("menuitem", { name: "费用" }));
    const childMenu = await screen.findByRole("menu", { name: "费用候选标签" });
    expect(within(childMenu).getByRole("menuitem", { name: "手续费" })).toBeInTheDocument();
    expect(within(childMenu).getByRole("menuitem", { name: "工资" })).toBeInTheDocument();
    expect(within(childMenu).queryByRole("menuitem", { name: "待收款" })).not.toBeInTheDocument();

    await user.click(within(childMenu).getByRole("menuitem", { name: "工资" }));
    expect(requestUrls(fetchMock, "/api/bank-details/transactions/bank-detail-needs-confirmation/category-confirmation")).toHaveLength(0);
    expect(within(row as HTMLElement).getByRole("button", { name: "费用 / 工资" })).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("menu", { name: "费用候选标签" })).not.toBeInTheDocument();
    expect(requestUrls(fetchMock, "/api/bank-details/transactions/bank-detail-needs-confirmation/category-confirmation")).toHaveLength(0);

    await user.click(within(row as HTMLElement).getByRole("button", { name: "待确认" }));
    const reopenedPrimaryMenu = await screen.findByRole("menu", { name: "待确认主标签" });
    await user.click(within(reopenedPrimaryMenu).getByRole("menuitem", { name: "费用" }));
    const reopenedChildMenu = await screen.findByRole("menu", { name: "费用候选标签" });
    await user.click(within(reopenedChildMenu).getByRole("menuitem", { name: "工资" }));
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-details/transactions/bank-detail-needs-confirmation/category-confirmation",
        expect.objectContaining({ body: JSON.stringify({ category_code: "salary" }) }),
      );
    });
  });

  test("external turnover confirmation submits the selected third-level label", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.type(within(page).getByPlaceholderText("搜索流水"), "外部候选");
    const table = await findBankTransactionSurface(page);
    expect(await within(table).findByText("外部候选供应商")).toBeInTheDocument();

    await user.click(within(table).getByRole("button", { name: "待确认" }));
    const primaryMenu = await screen.findByRole("menu", { name: "待确认主标签" });
    await user.click(within(primaryMenu).getByRole("menuitem", { name: "外部往来款付款" }));
    const childMenu = await screen.findByRole("menu", { name: "外部往来款付款候选标签" });
    expect(within(childMenu).getByRole("menuitem", { name: "借出款" })).toBeInTheDocument();
    expect(within(childMenu).getByRole("menuitem", { name: "归还借款" })).toBeInTheDocument();
    expect(within(childMenu).queryByRole("menuitem", { name: "借出款 / 公司往来" })).not.toBeInTheDocument();

    await user.click(within(childMenu).getByRole("menuitem", { name: "归还借款" }));
    const repaymentThirdMenu = await screen.findByRole("menu", { name: "归还借款候选业务类型" });
    expect(within(repaymentThirdMenu).getByRole("menuitem", { name: "个人往来" })).toBeInTheDocument();
    expect(within(repaymentThirdMenu).getByRole("menuitem", { name: "公司往来" })).toBeInTheDocument();
    expect(within(repaymentThirdMenu).getByRole("menuitem", { name: "银行往来" })).toBeInTheDocument();
    expect(within(repaymentThirdMenu).getByRole("menuitem", { name: "业务往来" })).toBeInTheDocument();

    await user.click(within(childMenu).getByRole("menuitem", { name: "借出款" }));
    const thirdMenu = await screen.findByRole("menu", { name: "借出款候选业务类型" });
    expect(within(thirdMenu).getByRole("menuitem", { name: "个人往来" })).toBeInTheDocument();
    expect(within(thirdMenu).getByRole("menuitem", { name: "公司往来" })).toBeInTheDocument();
    expect(within(thirdMenu).getByRole("menuitem", { name: "银行往来" })).toBeInTheDocument();
    expect(within(thirdMenu).getByRole("menuitem", { name: "业务往来" })).toBeInTheDocument();
    expect(within(thirdMenu).queryByRole("menuitem", { name: "借出款" })).not.toBeInTheDocument();

    await user.click(within(thirdMenu).getByRole("menuitem", { name: "公司往来" }));
    expect(requestUrls(fetchMock, "/api/bank-details/transactions/bank-detail-external-turnover-needs-confirmation/category-confirmation")).toHaveLength(0);
    expect(within(table).getByRole("button", { name: "外部往来款付款 / 借出款 / 公司往来" })).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-details/transactions/bank-detail-external-turnover-needs-confirmation/category-confirmation",
        expect.objectContaining({ body: JSON.stringify({ category_code: "external_payment", category_third_label: "公司往来" }) }),
      );
    });
  });

  test("external turnover manual classification chooses primary, sub tag, then third-level label", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await user.type(within(page).getByPlaceholderText("搜索流水"), "普通供应商");
    const table = await findBankTransactionSurface(page);
    const supplierName = await within(table).findByText("普通供应商");
    const row = supplierName.closest("tr");
    expect(row).toBeInstanceOf(HTMLElement);

    await user.click(within(row as HTMLElement).getByRole("button", { name: "待分类" }));
    const primaryMenu = await screen.findByRole("menu", { name: "待分类主标签" });
    await user.click(within(primaryMenu).getByRole("menuitem", { name: "外部往来款付款" }));
    const childMenu = await screen.findByRole("menu", { name: "外部往来款付款可选标签" });
    expect(within(childMenu).getByRole("menuitem", { name: "借出款" })).toBeInTheDocument();
    expect(within(childMenu).queryByRole("menuitem", { name: "借出款 / 业务往来" })).not.toBeInTheDocument();

    await user.click(within(childMenu).getByRole("menuitem", { name: "借出款" }));
    const thirdMenu = await screen.findByRole("menu", { name: "借出款可选业务类型" });
    await user.click(within(thirdMenu).getByRole("menuitem", { name: "业务往来" }));
    expect(requestUrls(fetchMock, "/api/bank-details/transactions/bank-detail-search-filler/category-assignment")).toHaveLength(0);
    expect(within(row as HTMLElement).getByRole("button", { name: "外部往来款付款 / 借出款 / 业务往来" })).not.toBeDisabled();

    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-details/transactions/bank-detail-search-filler/category-assignment",
        expect.objectContaining({
          body: JSON.stringify({
            category_code: "external_payment",
            category_primary_label: "外部往来款付款",
            category_sub_label: "借出款",
            category_third_label: "业务往来",
            category_label_path: ["外部往来款付款", "借出款", "业务往来"],
            turnover_action_type: "pending_collection",
            turnover_family: "business",
          }),
        }),
      );
    });
  });

  test("shows primary and sub tag labels in bank transaction rows", async () => {
    installMockApiFetch();
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    const table = await findBankTransactionSurface(page);

    expect(await within(table).findByText("费用 / 工资")).toBeInTheDocument();
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

    await user.click(within(page).getByRole("button", { name: /时间选择 2026年/ }));
    let datePicker = screen.getByRole("dialog", { name: "银行明细时间选择面板" });
    await user.click(within(datePicker).getByRole("button", { name: "2025年" }));
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBe("2025-01-01");
      expect(accountRequest?.searchParams.get("date_to")).toBe("2025-12-31");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2025-01-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2025-12-31");
    });
    expect(within(page).getAllByText("130,500.50").length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: /时间选择 2025年/ }));
    datePicker = screen.getByRole("dialog", { name: "银行明细时间选择面板" });
    await user.click(within(datePicker).getByRole("button", { name: "按月" }));
    await user.click(within(datePicker).getByRole("button", { name: "2026年" }));
    await user.click(within(datePicker).getByRole("button", { name: "3月" }));
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBe("2026-03-01");
      expect(accountRequest?.searchParams.get("date_to")).toBe("2026-03-31");
      expect(transactionRequest?.searchParams.get("date_from")).toBe("2026-03-01");
      expect(transactionRequest?.searchParams.get("date_to")).toBe("2026-03-31");
    });

    await user.click(within(page).getByRole("button", { name: "全部" }));
    await waitFor(() => {
      const accountRequest = requestUrls(fetchMock, "/api/bank-details/accounts").at(-1);
      const transactionRequest = requestUrls(fetchMock, "/api/bank-details/transactions").at(-1);
      expect(accountRequest?.searchParams.get("date_from")).toBeNull();
      expect(accountRequest?.searchParams.get("date_to")).toBeNull();
      expect(transactionRequest?.searchParams.get("date_from")).toBeNull();
      expect(transactionRequest?.searchParams.get("date_to")).toBeNull();
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

    await user.click(within(page).getByRole("button", { name: /时间选择 2026年/ }));
    const datePicker = screen.getByRole("dialog", { name: "银行明细时间选择面板" });
    await user.click(within(datePicker).getByRole("button", { name: "按月" }));
    await user.click(within(datePicker).getByRole("button", { name: "4月" }));

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
    const categoryPanel = await openCategoryFilterPanel(user, page);
    expect(within(categoryPanel).getByRole("menuitem", { name: "费用 1" })).toBeInTheDocument();
    expect(within(categoryPanel).getByRole("menuitem", { name: "手续费 1" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(within(page).queryByText("费用 / 工资 1")).not.toBeInTheDocument();
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
    const categoryPanel = await openCategoryFilterPanel(user, page);
    await user.click(within(categoryPanel).getByRole("menuitem", { name: "费用 1" }));
    await waitFor(() => {
      const transactionRequest = findTransactionRequest(fetchMock, (url) => (
        url.searchParams.get("category_primary_label") === "费用"
        && url.searchParams.get("category_code") === null
      ));
      expect(transactionRequest).toBeDefined();
      expect(transactionRequest?.searchParams.get("category_code")).toBeNull();
    });
    await user.click(within(page).getByRole("button", { name: "导出" }));
    await user.click(await screen.findByRole("menuitem", { name: "导出当前账户" }));

    await waitFor(() => {
      const exportRequest = requestUrls(fetchMock, "/api/bank-details/transactions/export").at(-1);
      expect(exportRequest?.searchParams.get("mode")).toBe("account");
      expect(exportRequest?.searchParams.get("account_key")).toBe("icbc:6386");
      expect(exportRequest?.searchParams.get("keyword")).toBe("跨页目标");
      expect(exportRequest?.searchParams.get("category_primary_label")).toBe("费用");
      expect(exportRequest?.searchParams.get("category_code")).toBeNull();
    });

    clickSpy.mockRestore();
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: originalCreateObjectUrl });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectUrl });
  });

  test("shows backend export row-limit messages without starting a download", async () => {
    const user = userEvent.setup();
    const baseFetch = installMockApiFetch();
    const originalCreateObjectUrl = window.URL.createObjectURL;
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: vi.fn() });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-details/transactions/export") {
        return new Response(JSON.stringify({
          error: "bank_detail_export_row_limit_exceeded",
          details: { total: 20001, limit: 20000 },
        }), { status: 400, headers: { "Content-Type": "application/json" } });
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderBankDetailsPage();

    const page = await screen.findByTestId("bank-details-page");
    await within(page).findByText("云南溯源科技有限公司");
    await user.click(within(page).getByRole("button", { name: "导出" }));
    await user.click(await screen.findByRole("menuitem", { name: "导出全部银行" }));

    expect(await within(page).findByText("当前筛选命中流水过多，请缩小日期范围、选择具体银行或增加搜索条件后再导出。")).toBeInTheDocument();
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();

    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: originalCreateObjectUrl });
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
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    expect(requestUrls(fetchMock, "/api/bank-details/accounts").length).toBe(initialAccountRequests);
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
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    expect(requestUrls(fetchMock, "/api/bank-details/accounts").length).toBe(initialAccountRequests);
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

  test("saving auto tag rules refreshes transactions without refetching account balances", async () => {
    const fetchMock = installMockApiFetch({
      bankDetailAccountReadModelStatuses: ["fresh", "fresh"],
      bankDetailPostSaveAccountsTotalBalance: "999999.99",
      bankDetailPostSaveTransactionLabel: "规则保存后流水",
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderBankDetailsPage();
    const page = await screen.findByTestId("bank-details-page");
    const initialAccountRequests = requestUrls(fetchMock, "/api/bank-details/accounts").length;
    const initialTransactionRequests = requestUrls(fetchMock, "/api/bank-details/transactions").length;

    await within(page).findByText("云南溯源科技有限公司");
    await user.click(within(page).getByRole("button", { name: /自动标签规则/ }));
    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await editRuleLabelInDrawer(user, drawer, "费用 / 工资", "费用", "网银证书服务费");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(requestUrls(fetchMock, "/api/bank-details/transactions").length).toBeGreaterThan(initialTransactionRequests);
    });
    expect(requestUrls(fetchMock, "/api/bank-details/accounts").length).toBe(initialAccountRequests);
    expect(screen.queryByText("999,999.99")).not.toBeInTheDocument();
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
