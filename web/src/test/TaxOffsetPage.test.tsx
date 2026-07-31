import { readFileSync } from "node:fs";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

const ROUTE_RENDER_TIMEOUT = 5000;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  if (typeof window.localStorage?.clear === "function") {
    window.localStorage.clear();
  }
});

function getStatCard(label: string) {
  const card = screen
    .getAllByText(label)
    .map((element) => element.closest(".stat-card"))
    .find((element): element is HTMLElement => Boolean(element));
  if (!card) {
    throw new Error(`Stat card not found for ${label}`);
  }
  return card;
}

function getTaxFinanceGrid(name: string) {
  const grid = screen.getByRole("grid", { name });
  expect(grid.closest(".finance-table")).not.toBeNull();
  return grid;
}

function getModalFinanceGrid(modal: HTMLElement, name: RegExp | string) {
  const grid = within(modal).getByRole("grid", { name });
  expect(grid.closest(".finance-table")).not.toBeNull();
  return grid;
}

async function expectFinanceColumnRoles(grid: HTMLElement, expectedRoles: string[]) {
  await waitFor(() => {
    const headerRoles = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.getAttribute("data-column-role"));
    expect(headerRoles).toEqual(expectedRoles);
  });
}

function expectProjectDialogContract(dialog: HTMLElement) {
  expect(dialog).toHaveClass("finance-dialog");
  expect(dialog.closest(".MuiDialog-root")).toBeNull();
}

function requestUrl(input: RequestInfo | URL) {
  return new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
}

function taxOffsetMonthRequests(fetchMock: ReturnType<typeof installMockApiFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => requestUrl(input))
    .filter((url) => url.pathname === "/api/tax-offset" && url.searchParams.get("month") === "2026-03");
}

function operationBarrierRequests(fetchMock: ReturnType<typeof installMockApiFetch>) {
  return fetchMock.mock.calls.filter(([input]) => requestUrl(input).pathname === "/api/operation-barrier/status");
}

describe("Tax offset workbench", () => {
  test("shows the unified page Audit control to admins", async () => {
    window.history.pushState({}, "", "/tax-offset");
    installMockApiFetch({ sessionAccessTier: "admin" });
    render(<App />);

    expect(await screen.findByRole("heading", { name: "税金抵扣计划与试算" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Audit 税金抵扣" })).toBeInTheDocument();
  });

  test("keeps tax offset premium visual polish scoped to project primitives", () => {
    const styles = readFileSync("src/app/styles.css", "utf8");
    const summarySource = readFileSync("src/components/tax/TaxSummaryCards.tsx", "utf8");
    const certifiedDrawerSource = readFileSync("src/components/tax/CertifiedResultsDrawer.tsx", "utf8");

    expect(summarySource).toContain("tax-summary-strip");
    expect(summarySource).toContain("tax-summary-card");
    expect(styles).toMatch(/\.tax-summary-card\.stat-card\s*\{/);
    expect(styles).toMatch(/\.tax-result-panel\s*\{[\s\S]*border-left:\s*3px solid var\(--fp-primary\)/);
    expect(styles).toMatch(/\.tax-panel-header\s*\{[\s\S]*background:\s*var\(--fp-surface-muted\)/);
    expect(styles).toMatch(/\.tax-certified-drawer\s*\{[\s\S]*border-radius:\s*var\(--fp-radius-md\)/);
    expect(styles).toMatch(/\.tax-certified-drawer-body\s*\{[^}]*transition:[^}]*opacity[^}]*transform/s);
    expect(styles).toMatch(/\.tax-certified-drawer\.collapsed \.tax-certified-drawer-body\s*\{[^}]*opacity:\s*0[^}]*transform:\s*translateX\(100%\)[^}]*pointer-events:\s*none/s);
    expect(certifiedDrawerSource).toContain("inert={isCollapsed ? true : undefined}");
    expect(certifiedDrawerSource).toContain("aria-hidden={isCollapsed}");
    expect(certifiedDrawerSource).not.toContain("{!isCollapsed ? (");
    expect(styles).toMatch(/\.tax-status-tag,[\s\S]*\.tax-date-tag,[\s\S]*\.tax-rate-tag\s*\{[\s\S]*height:\s*var\(--fp-tag-height-table\)/);
  });

  test("clears the initial loading state when the active tax month request is aborted", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const abortControllers: AbortController[] = [];
    const NativeAbortController = globalThis.AbortController;

    class RecordingAbortController extends NativeAbortController {
      constructor() {
        super();
        abortControllers.push(this);
      }
    }

    vi.stubGlobal("AbortController", RecordingAbortController);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(
          JSON.stringify({
            user: {
              user_id: "101",
              username: "liuji",
              nickname: "刘际涛",
              display_name: "刘际涛",
            },
            roles: ["finance"],
            permissions: ["finops:app:view"],
            allowed: true,
            access_tier: "full_access",
            can_access_app: true,
            can_mutate_data: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url === "/api/tax-offset?month=2026-03") {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("signal is aborted without reason", "AbortError")));
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByText(
        "正在加载 2026-03 的税金抵扣计划与已认证结果...",
        {},
        { timeout: ROUTE_RENDER_TIMEOUT },
      ),
    ).toBeInTheDocument();
    act(() => {
      abortControllers.forEach((controller) => controller.abort());
    });

    await waitFor(() => {
      expect(screen.queryByText("正在加载 2026-03 的税金抵扣计划与已认证结果...")).not.toBeInTheDocument();
    });
  });

  test("renders read-only output invoices, editable input plan, and certified drawer", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "返回关联台" })).not.toBeInTheDocument();

    const outputTable = getTaxFinanceGrid("销项票开票情况");
    await expectFinanceColumnRoles(outputTable, ["identity", "amount", "account", "amount"]);
    expect(within(outputTable).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(outputTable).queryByText("发票类型")).not.toBeInTheDocument();
    expect(within(outputTable).getByText("销")).toBeInTheDocument();
    expect(within(outputTable).getAllByRole("columnheader").map((header) => header.textContent?.trim())).toEqual([
      "发票编号",
      "税额",
      "对方名称",
      "金额（税率）",
    ]);
    expect(within(outputTable).queryByText("开票日期")).not.toBeInTheDocument();
    expect(within(outputTable).getAllByText("2026-03-25").length).toBeGreaterThan(0);
    expect(within(outputTable).getByText("(13%)")).toBeInTheDocument();
    const outputInvoiceMetaRow = within(outputTable).getAllByText("2026-03-25")[0]?.closest(".tax-invoice-meta-row");
    expect(outputInvoiceMetaRow).not.toBeNull();
    expect(within(outputInvoiceMetaRow as HTMLElement).getByText("销")).toBeInTheDocument();
    expect(within(outputInvoiceMetaRow as HTMLElement).queryByText("进")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("销项票开票情况横向滚动")).not.toBeInTheDocument();

    const inputTable = getTaxFinanceGrid("进项票认证计划");
    await expectFinanceColumnRoles(inputTable, ["selection", "identity", "amount", "account", "amount"]);
    expect(within(inputTable).getByRole("checkbox", { name: /11203490/ })).not.toBeDisabled();
    expect(within(inputTable).getByRole("checkbox", { name: /11203491/ })).not.toBeDisabled();
    expect(within(inputTable).queryByText("发票类型")).not.toBeInTheDocument();
    expect(within(inputTable).getAllByText("进").length).toBeGreaterThan(0);
    expect(within(inputTable).getAllByRole("columnheader").map((header) => header.textContent?.trim())).toEqual([
      "选择",
      "发票编号",
      "税额",
      "对方名称",
      "金额（税率）",
    ]);
    expect(within(inputTable).queryByText("状态")).not.toBeInTheDocument();
    expect(within(inputTable).queryByText("开票日期")).not.toBeInTheDocument();
    expect(within(inputTable).getAllByText("待认证").length).toBeGreaterThan(0);
    expect(within(inputTable).getAllByText("2026-03-22").length).toBeGreaterThan(0);
    expect(within(inputTable).getByText("(13%)")).toBeInTheDocument();
    expect(within(inputTable).getByText("(6%)")).toBeInTheDocument();
    const invoiceMetaRow = within(inputTable).getAllByText("待认证")[0]?.closest(".tax-invoice-meta-row");
    expect(invoiceMetaRow).not.toBeNull();
    expect(within(invoiceMetaRow as HTMLElement).getByText("进")).toBeInTheDocument();
    expect(within(invoiceMetaRow as HTMLElement).getByText("2026-03-22")).toBeInTheDocument();
    expect(screen.queryByLabelText("进项票认证计划横向滚动")).not.toBeInTheDocument();
    expect(screen.getByLabelText("税金抵扣表格横向滚动")).toBeInTheDocument();

    const certifiedRail = screen.getByRole("complementary", { name: "已认证结果" });
    const certifiedBody = certifiedRail.querySelector("#tax-certified-results-body");
    expect(certifiedBody).not.toBeNull();
    expect(screen.getByText("已匹配计划")).toBeInTheDocument();
    expect(screen.getByText("已认证但未进入计划")).toBeInTheDocument();
    expect(screen.getByText("税金抵扣计划与试算")).toBeInTheDocument();
    expect(screen.getByText("税金抵扣试算")).toBeInTheDocument();
    expect(screen.queryByText("提交认证")).not.toBeInTheDocument();
    expect(screen.queryByText("正式申报")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /已认证结果/ }));
    const expandCertifiedRail = screen.getByRole("button", { name: /展开已认证结果/ });
    expect(expandCertifiedRail).toHaveAttribute("aria-expanded", "false");
    expect(certifiedBody).toHaveAttribute("aria-hidden", "true");
    expect(certifiedBody).toHaveAttribute("inert");
    expect(within(certifiedBody as HTMLElement).getByText("已匹配计划")).toBeInTheDocument();

    await user.click(expandCertifiedRail);
    expect(screen.getByRole("button", { name: /收起已认证结果/ })).toHaveAttribute("aria-expanded", "true");
    expect(certifiedBody).toHaveAttribute("aria-hidden", "false");
    expect(certifiedBody).not.toHaveAttribute("inert");
  });

  test("remounts the tax offset page and revalidates without restoring data snapshots", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    let resolveSecondTaxFetch: ((response: Response) => void) | null = null;
    let taxFetchCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(JSON.stringify({
          user: {
            user_id: "101",
            username: "liuji",
            nickname: "刘际涛",
            display_name: "刘际涛",
          },
          roles: ["finance"],
          permissions: ["finops:app:view"],
          allowed: true,
          can_access_app: true,
          can_mutate_data: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/settings") {
        return new Response(JSON.stringify({
          projects: [],
          reimbursementAccounts: [],
          bankAccounts: [],
          bankTransactionTags: [],
          bankTransactionAutoTagRules: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset?month=2026-03") {
        taxFetchCount += 1;
        const payload = {
          month: "2026-03",
          canonical_snapshot_version: "tax-offset-v1:initial",
          output_items: [
            {
              id: "to-202603-001",
              buyer_name: "华东项目甲方",
              issue_date: "2026-03-25",
              invoice_no: "90342011",
              tax_amount: "41,600.00",
              total_with_tax: "361,600.00",
              invoice_type: "销项专票",
            },
          ],
          input_plan_items: [
            {
              id: "ti-202603-001",
              seller_name: "设备供应商",
              issue_date: "2026-03-22",
              invoice_no: "11203490",
              tax_amount: "12,480.00",
              total_with_tax: "108,480.00",
              risk_level: "低",
              certified_status: "待认证",
              is_locked_certified: false,
            },
          ],
          certified_items: [],
          certified_matched_rows: [],
          certified_outside_plan_rows: [],
          locked_certified_input_ids: [],
          default_selected_output_ids: ["to-202603-001"],
          default_selected_input_ids: ["ti-202603-001"],
          summary: {
            output_tax: "41,600.00",
            certified_input_tax: "0.00",
            planned_input_tax: "12,480.00",
            input_tax: "12,480.00",
            deductible_tax: "12,480.00",
            result_label: "本月应纳税额",
            result_amount: "29,120.00",
          },
        };
        if (taxFetchCount === 1) {
          return new Response(JSON.stringify(payload), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Promise<Response>((resolve) => {
          resolveSecondTaxFetch = resolve;
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("本月应纳税额")).getByText("29,120.00")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByTestId("tax-offset-page")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "税金抵扣" }));

    expect(await screen.findByRole("heading", { name: "税金抵扣计划与试算" })).toBeInTheDocument();
    expect(screen.getByText("正在加载 2026-03 的税金抵扣计划与已认证结果...")).toBeInTheDocument();
    await waitFor(() => expect(taxFetchCount).toBe(2));

    resolveSecondTaxFetch?.(new Response(JSON.stringify({
      month: "2026-03",
      canonical_snapshot_version: "tax-offset-v1:empty",
      output_items: [],
      input_plan_items: [],
      certified_items: [],
      certified_matched_rows: [],
      certified_outside_plan_rows: [],
      locked_certified_input_ids: [],
      default_selected_output_ids: [],
      default_selected_input_ids: [],
      summary: {
        output_tax: "0.00",
        certified_input_tax: "0.00",
        planned_input_tax: "0.00",
        input_tax: "0.00",
        deductible_tax: "0.00",
        result_label: "本月留抵税额",
        result_amount: "0.00",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    expect(await screen.findByText("当前月份没有可用于计划与试算的发票数据。")).toBeInTheDocument();
  });

  test("read-only export users can view tax offset data but cannot import certified invoices", async () => {
    window.history.pushState({}, "", "/tax-offset");
    installMockApiFetch({
      sessionAccessTier: "read_export_only",
      sessionUsername: "READONLY001",
    });
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "已认证发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存计划" })).not.toBeInTheDocument();
  });

  test("previews and confirms certified invoice import inside the page modal, then refreshes plan and summary", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));

    const modal = screen.getByRole("dialog", { name: "已认证发票导入" });
    expect(modal).toBeInTheDocument();
    expectProjectDialogContract(modal);
    expect(window.location.pathname).toBe("/tax-offset");
    expect(screen.queryByRole("heading", { name: "导入中心" })).not.toBeInTheDocument();

    const certifiedFile = new File(["mock-xlsx"], "2026年3月 进项认证结果  用途确认信息.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const certifiedDropzone = within(modal).getByLabelText("选择已认证发票文件");
    expect(certifiedDropzone.closest(".finance-file-dropzone")).not.toBeNull();
    await user.upload(certifiedDropzone, certifiedFile);

    expect(within(modal).getByText(/2026年3月.*用途确认信息\.xlsx/)).toBeInTheDocument();

    await user.click(within(modal).getByRole("button", { name: "预览识别结果" }));

    expect(await within(modal).findByText(/识别记录\s*2\s*条/)).toBeInTheDocument();
    expect(within(modal).getAllByText(/匹配计划\s*1\s*条/).length).toBeGreaterThan(0);
    expect(within(modal).getAllByText(/未进入计划\s*1\s*条/).length).toBeGreaterThan(0);
    expect(within(modal).getByText(/无效记录\s*0\s*条/)).toBeInTheDocument();
    const previewRowTable = getModalFinanceGrid(modal, /行级预览结果/);
    await expectFinanceColumnRoles(previewRowTable, ["quantity", "identity", "account", "amount", "status", "status", "description"]);
    expect(within(previewRowTable).getByText("11203490")).toBeInTheDocument();
    expect(within(previewRowTable).getByText("11203999")).toBeInTheDocument();
    expect(within(previewRowTable).getByText("匹配计划")).toBeInTheDocument();
    expect(within(previewRowTable).getByText("未进入计划")).toBeInTheDocument();
    expect(within(previewRowTable).getAllByText("新记录").length).toBeGreaterThan(0);

    await user.click(within(modal).getByRole("button", { name: "确认导入" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "已认证发票导入" })).not.toBeInTheDocument();
    });

    expect(await screen.findByText("已导入 2 条已认证记录，并已刷新当前税金抵扣页面。")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("14,080.00")).toBeInTheDocument();

    const inputTable = getTaxFinanceGrid("进项票认证计划");
    expect(within(inputTable).getByRole("checkbox", { name: /11203490/ })).toBeDisabled();

    const drawer = screen.getByRole("complementary", { name: "已认证结果" });
    expect(within(drawer).getByText("11203490")).toBeInTheDocument();
    expect(within(drawer).getByText("11203999")).toBeInTheDocument();
  });

  test("certified invoice import accepts dragged files in the upload area", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));

    const modal = screen.getByRole("dialog", { name: "已认证发票导入" });
    const dropzone = within(modal).getByLabelText("选择已认证发票文件");
    const certifiedFile = new File(["mock-xlsx"], "拖拽认证结果.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    fireEvent.dragEnter(dropzone, {
      dataTransfer: { files: [certifiedFile] },
    });
    fireEvent.dragOver(dropzone, {
      dataTransfer: { files: [certifiedFile] },
    });
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [certifiedFile] },
    });

    expect(await within(modal).findByText("拖拽认证结果.xlsx")).toBeInTheDocument();
  });

  test("certified invoice import dropzone rejects non-excel files with an immediate message", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));

    const modal = screen.getByRole("dialog", { name: "已认证发票导入" });
    const dropzone = within(modal).getByLabelText("选择已认证发票文件");
    const invalidFile = new File(["text"], "说明.txt", {
      type: "text/plain",
    });

    fireEvent.dragEnter(dropzone, {
      dataTransfer: { files: [invalidFile] },
    });
    fireEvent.dragOver(dropzone, {
      dataTransfer: { files: [invalidFile] },
    });
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [invalidFile] },
    });

    expect(await within(modal).findByText("仅支持 .xls/.xlsx")).toBeInTheDocument();
    expect(within(modal).queryByText("说明.txt")).not.toBeInTheDocument();
  });

  test("recalculates using certified invoices plus selected uncertified plan rows", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("销项税额")).getByText("41,600.00")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();
    expect(within(getStatCard("计划进项税额")).getByText("18,240.00")).toBeInTheDocument();
    expect(within(getStatCard("本月抵扣额")).getByText("18,240.00")).toBeInTheDocument();
    expect(within(getStatCard("本月应纳税额")).getByText("23,360.00")).toBeInTheDocument();

    await user.click(await screen.findByRole("checkbox", { name: /11203491/ }));

    expect(await within(getStatCard("计划进项税额")).findByText("12,480.00")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();
    expect(within(getStatCard("本月抵扣额")).getByText("12,480.00")).toBeInTheDocument();
    expect(within(getStatCard("本月应纳税额")).getByText("29,120.00")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tax-offset/calculate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "2026-03",
          selected_output_ids: ["to-202603-001"],
          selected_input_ids: ["ti-202603-001"],
        }),
      }),
    );
  });

  test("saves the current tax offset plan with a canonical snapshot version", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    await user.click(await screen.findByRole("checkbox", { name: /11203491/ }));
    expect(await within(getStatCard("计划进项税额")).findByText("12,480.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存计划" }));

    expect(await screen.findByText("已保存本月税金抵扣计划。")).toBeInTheDocument();
    const saveCall = fetchMock.mock.calls.find(([input]) => input === "/api/tax-offset/plans");
    expect(saveCall).toBeDefined();
    expect(saveCall?.[1]).toEqual(expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({
      month: "2026-03",
      selected_output_ids: ["to-202603-001"],
      selected_input_ids: ["ti-202603-001"],
      expected_canonical_snapshot_version: "mock-tax-offset:2026-03",
      idempotency_key: "tax-offset-plan:2026-03:mock-tax-offset:2026-03:ti-202603-001",
    });
  });

  test("reloads the current tax page directly after plan save without a cross-page barrier", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    await user.click(await screen.findByRole("checkbox", { name: /11203491/ }));
    expect(await within(getStatCard("计划进项税额")).findByText("12,480.00")).toBeInTheDocument();
    const initialTaxReads = taxOffsetMonthRequests(fetchMock).length;

    await user.click(screen.getByRole("button", { name: "保存计划" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => input === "/api/tax-offset/plans")).toBe(true));
    expect(operationBarrierRequests(fetchMock)).toHaveLength(0);
    expect(await screen.findByText("已保存本月税金抵扣计划。")).toBeInTheDocument();
    await waitFor(() => expect(taxOffsetMonthRequests(fetchMock).length).toBeGreaterThan(initialTaxReads));
  });

  test("does not trigger duplicate calculate on first load when server summary already matches default selection", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    expect(
      fetchMock.mock.calls.some(([input]) => input === "/api/tax-offset/calculate"),
    ).toBe(false);
  });

  test("supports select all and clear actions for the input plan table", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    const inputTable = getTaxFinanceGrid("进项票认证计划");
    const firstCheckbox = await within(inputTable).findByRole("checkbox", { name: /11203490/ }) as HTMLInputElement;
    const secondCheckbox = await within(inputTable).findByRole("checkbox", { name: /11203491/ }) as HTMLInputElement;

    expect(firstCheckbox.checked).toBe(true);
    expect(secondCheckbox.checked).toBe(true);

    await user.click(screen.getByRole("button", { name: "清空" }));

    expect(firstCheckbox.checked).toBe(false);
    expect(secondCheckbox.checked).toBe(false);

    await user.click(screen.getByRole("button", { name: "全选" }));

    expect(firstCheckbox.checked).toBe(true);
    expect(secondCheckbox.checked).toBe(true);
  });

  test("supports inline search, time sorting, and counterparty filters in both tax invoice tables", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();

    const monthPayload = {
      month: "2026-03",
      canonical_snapshot_version: "tax-offset-v1:table-controls",
      output_items: [
        {
          id: "to-filter-001",
          buyer_name: "华东项目甲方",
          issue_date: "2026-03-25",
          invoice_no: "90342011",
          tax_rate: "13%",
          tax_amount: "41,600.00",
          total_with_tax: "361,600.00",
          invoice_type: "销项专票",
        },
        {
          id: "to-filter-002",
          buyer_name: "西南项目客户",
          issue_date: "2026-03-05",
          invoice_no: "90342012",
          tax_rate: "6%",
          tax_amount: "2,400.00",
          total_with_tax: "42,400.00",
          invoice_type: "销项普票",
        },
      ],
      input_plan_items: [
        {
          id: "ti-filter-001",
          seller_name: "设备供应商",
          issue_date: "2026-03-22",
          invoice_no: "11203490",
          tax_rate: "13%",
          tax_amount: "12,480.00",
          total_with_tax: "108,480.00",
          risk_level: "低",
          certified_status: "待认证",
          is_locked_certified: false,
        },
        {
          id: "ti-filter-002",
          seller_name: "集成服务商",
          issue_date: "2026-03-24",
          invoice_no: "11203491",
          tax_rate: "6%",
          tax_amount: "5,760.00",
          total_with_tax: "101,760.00",
          risk_level: "中",
          certified_status: "待认证",
          is_locked_certified: false,
        },
      ],
      certified_items: [],
      certified_matched_rows: [],
      certified_outside_plan_rows: [],
      locked_certified_input_ids: [],
      default_selected_output_ids: ["to-filter-001", "to-filter-002"],
      default_selected_input_ids: ["ti-filter-001", "ti-filter-002"],
      summary: {
        output_tax: "44,000.00",
        certified_input_tax: "0.00",
        planned_input_tax: "18,240.00",
        input_tax: "18,240.00",
        deductible_tax: "18,240.00",
        result_label: "本月应纳税额",
        result_amount: "25,760.00",
      },
    };

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(
          JSON.stringify({
            user: {
              user_id: "101",
              username: "liuji",
              nickname: "刘际涛",
              display_name: "刘际涛",
              dept_id: "88",
              dept_name: "财务部",
            },
            roles: ["finance"],
            permissions: ["finops:app:view"],
            allowed: true,
            access_tier: "full_access",
            can_access_app: true,
            can_mutate_data: true,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url === "/api/tax-offset?month=2026-03") {
        return new Response(JSON.stringify(monthPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/tax-offset/calculate") {
        return new Response(JSON.stringify({ month: "2026-03", summary: monthPayload.summary }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    const outputTable = getTaxFinanceGrid("销项票开票情况");
    await user.click(screen.getByRole("button", { name: "搜索 销项票开票情况" }));
    await user.type(screen.getByRole("searchbox", { name: "搜索 销项票开票情况" }), "西南");
    expect(within(outputTable).queryByText("90342011")).not.toBeInTheDocument();
    expect(within(outputTable).getByText("90342012")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清空搜索 销项票开票情况" }));
    expect(within(outputTable).getByText("90342011")).toBeInTheDocument();

    await user.click(within(outputTable.closest(".tax-panel") as HTMLElement).getByRole("button", { name: "销项票开票情况按时间降序" }));
    const outputRowsDesc = within(outputTable).getAllByRole("row");
    expect(outputRowsDesc[1]).toHaveTextContent("90342011");
    await user.click(within(outputTable.closest(".tax-panel") as HTMLElement).getByRole("button", { name: "销项票开票情况按时间升序" }));
    const outputRowsAsc = within(outputTable).getAllByRole("row");
    expect(outputRowsAsc[1]).toHaveTextContent("90342012");

    await user.click(within(outputTable).getByRole("button", { name: "筛选 对方名称" }));
    const outputFilterDialog = screen.getByRole("dialog", { name: "筛选 对方名称" });
    await user.click(within(outputFilterDialog).getByLabelText("华东项目甲方"));
    expect(within(outputTable).getByText("90342011")).toBeInTheDocument();
    expect(within(outputTable).queryByText("90342012")).not.toBeInTheDocument();
    await user.click(within(outputFilterDialog).getByRole("button", { name: "清空" }));
    expect(within(outputTable).getByText("90342012")).toBeInTheDocument();
    await user.keyboard("{Escape}");

    const inputTable = getTaxFinanceGrid("进项票认证计划");
    await user.click(screen.getByRole("button", { name: "搜索 进项票认证计划" }));
    await user.type(screen.getByRole("searchbox", { name: "搜索 进项票认证计划" }), "集成");
    expect(within(inputTable).queryByText("11203490")).not.toBeInTheDocument();
    expect(within(inputTable).getByText("11203491")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清空搜索 进项票认证计划" }));

    await user.click(within(inputTable.closest(".tax-panel") as HTMLElement).getByRole("button", { name: "进项票认证计划按时间降序" }));
    const inputRowsDesc = within(inputTable).getAllByRole("row");
    expect(inputRowsDesc[1]).toHaveTextContent("11203491");

    await user.click(within(inputTable).getByRole("button", { name: "筛选 对方名称" }));
    const inputFilterDialog = screen.getByRole("dialog", { name: "筛选 对方名称" });
    await user.click(within(inputFilterDialog).getByLabelText("设备供应商"));
    expect(within(inputTable).getByText("11203490")).toBeInTheDocument();
    expect(within(inputTable).queryByText("11203491")).not.toBeInTheDocument();
    await user.click(within(inputFilterDialog).getByRole("button", { name: "清空" }));
    expect(within(inputTable).getByText("11203491")).toBeInTheDocument();
  });

  test("renders output invoice rows with 销 tag even when invoice type text does not contain 销", async () => {
    window.history.pushState({}, "", "/tax-offset");

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(
          JSON.stringify({
            user: {
              user_id: "101",
              username: "liuji",
              nickname: "刘际涛",
              display_name: "刘际涛",
            },
            roles: ["finance"],
            permissions: ["finops:app:view"],
            allowed: true,
            access_tier: "full_access",
            can_access_app: true,
            can_mutate_data: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url === "/api/tax-offset?month=2026-03") {
        return new Response(
          JSON.stringify({
            month: "2026-03",
            canonical_snapshot_version: "tax-offset-v1:output-tag",
            output_items: [
              {
                id: "to-real-001",
                buyer_name: "云南鸿云锅炉有限责任公司",
                issue_date: "2026-03-16",
                invoice_no: "26532000000395086336",
                tax_rate: "13%",
                tax_amount: "26,091.00",
                total_with_tax: "226,791.00",
                invoice_type: "数电发票（增值税专用发票）",
              },
            ],
            input_plan_items: [],
            certified_items: [],
            certified_matched_rows: [],
            certified_outside_plan_rows: [],
            locked_certified_input_ids: [],
            default_selected_output_ids: ["to-real-001"],
            default_selected_input_ids: [],
            summary: {
              output_tax: "26,091.00",
              certified_input_tax: "0.00",
              planned_input_tax: "0.00",
              input_tax: "0.00",
              deductible_tax: "0.00",
              result_label: "本月应纳税额",
              result_amount: "26,091.00",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url === "/api/tax-offset/calculate") {
        return new Response(
          JSON.stringify({
            month: "2026-03",
            summary: {
              output_tax: "26,091.00",
              certified_input_tax: "0.00",
              planned_input_tax: "0.00",
              input_tax: "0.00",
              deductible_tax: "0.00",
              result_label: "本月应纳税额",
              result_amount: "26,091.00",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    const outputTable = getTaxFinanceGrid("销项票开票情况");
    const outputInvoiceMetaRow = (await within(outputTable).findByText("2026-03-16")).closest(".tax-invoice-meta-row");
    expect(outputInvoiceMetaRow).not.toBeNull();
    expect(within(outputInvoiceMetaRow as HTMLElement).getByText("销")).toBeInTheDocument();
    expect(within(outputInvoiceMetaRow as HTMLElement).queryByText("进")).not.toBeInTheDocument();
  });

  test("clicking a matched certified row highlights the corresponding input plan row", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();
    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));
    const modal = screen.getByRole("dialog", { name: "已认证发票导入" });
    const certifiedFile = new File(["mock-xlsx"], "2026年3月 进项认证结果  用途确认信息.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await user.upload(within(modal).getByLabelText("选择已认证发票文件"), certifiedFile);
    await user.click(within(modal).getByRole("button", { name: "预览识别结果" }));
    await screen.findByText(/识别记录\s*2\s*条/);
    await user.click(within(modal).getByRole("button", { name: "确认导入" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "已认证发票导入" })).not.toBeInTheDocument();
    });

    const drawer = screen.getByRole("complementary", { name: "已认证结果" });
    await user.click(within(drawer).getByRole("button", { name: /11203490/ }));

    const inputTable = getTaxFinanceGrid("进项票认证计划");
    const highlightedRow = within(inputTable).getByRole("row", { name: /11203490/ });
    expect(highlightedRow).toHaveAttribute("data-certified-highlighted", "true");
  });

  test("shows an empty state when the selected month has no tax invoices", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "年月选择" }));
    await user.click(screen.getByRole("radio", { name: "2026" }));
    await user.click(screen.getByRole("radio", { name: "五月" }));

    expect(await screen.findByText("当前月份没有可用于计划与试算的发票数据。")).toBeInTheDocument();
  });

  test("does not refresh tax data when the page regains focus", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const responses = [
      {
        month: "2026-03",
        canonical_snapshot_version: "tax-offset-v1:focus-initial",
        output_items: [
          {
            id: "to-202603-001",
            buyer_name: "华东项目甲方",
            issue_date: "2026-03-25",
            invoice_no: "90342011",
            tax_amount: "41,600.00",
            total_with_tax: "361,600.00",
            invoice_type: "销项专票",
          },
        ],
        input_plan_items: [
          {
            id: "ti-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            risk_level: "低",
            certified_status: "待认证",
            is_locked_certified: false,
          },
          {
            id: "ti-202603-002",
            seller_name: "集成服务商",
            issue_date: "2026-03-24",
            invoice_no: "11203491",
            tax_amount: "5,760.00",
            total_with_tax: "101,760.00",
            risk_level: "中",
            certified_status: "待认证",
            is_locked_certified: false,
          },
        ],
        certified_items: [],
        certified_matched_rows: [],
        certified_outside_plan_rows: [],
        locked_certified_input_ids: [],
        default_selected_output_ids: ["to-202603-001"],
        default_selected_input_ids: ["ti-202603-001", "ti-202603-002"],
        summary: {
          output_tax: "41,600.00",
          certified_input_tax: "0.00",
          planned_input_tax: "18,240.00",
          input_tax: "18,240.00",
          deductible_tax: "18,240.00",
          result_label: "本月应纳税额",
          result_amount: "23,360.00",
        },
      },
      {
        month: "2026-03",
        canonical_snapshot_version: "tax-offset-v1:focus-next",
        output_items: [
          {
            id: "to-202603-001",
            buyer_name: "华东项目甲方",
            issue_date: "2026-03-25",
            invoice_no: "90342011",
            tax_amount: "41,600.00",
            total_with_tax: "361,600.00",
            invoice_type: "销项专票",
          },
        ],
        input_plan_items: [
          {
            id: "ti-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            risk_level: "低",
            certified_status: "已认证",
            is_locked_certified: true,
          },
          {
            id: "ti-202603-002",
            seller_name: "集成服务商",
            issue_date: "2026-03-24",
            invoice_no: "11203491",
            tax_amount: "5,760.00",
            total_with_tax: "101,760.00",
            risk_level: "中",
            certified_status: "待认证",
            is_locked_certified: false,
          },
        ],
        certified_items: [
          {
            id: "tc-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            status: "已认证",
          },
          {
            id: "tc-202603-099",
            seller_name: "物业服务商",
            issue_date: "2026-03-28",
            invoice_no: "11203999",
            tax_amount: "1,600.00",
            total_with_tax: "13,600.00",
            status: "已认证",
          },
        ],
        certified_matched_rows: [
          {
            id: "tc-202603-001",
            seller_name: "设备供应商",
            issue_date: "2026-03-22",
            invoice_no: "11203490",
            tax_amount: "12,480.00",
            total_with_tax: "108,480.00",
            status: "已认证",
            matched_input_id: "ti-202603-001",
          },
        ],
        certified_outside_plan_rows: [
          {
            id: "tc-202603-099",
            seller_name: "物业服务商",
            issue_date: "2026-03-28",
            invoice_no: "11203999",
            tax_amount: "1,600.00",
            total_with_tax: "13,600.00",
            status: "已认证",
            matched_input_id: null,
          },
        ],
        locked_certified_input_ids: ["ti-202603-001"],
        default_selected_output_ids: ["to-202603-001"],
        default_selected_input_ids: ["ti-202603-002"],
        summary: {
          output_tax: "41,600.00",
          certified_input_tax: "14,080.00",
          planned_input_tax: "5,760.00",
          input_tax: "19,840.00",
          deductible_tax: "19,840.00",
          result_label: "本月应纳税额",
          result_amount: "21,760.00",
        },
      },
    ];
    let currentSnapshot = responses[0];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(
          JSON.stringify({
            user: {
              user_id: "101",
              username: "liuji",
              nickname: "刘际涛",
              display_name: "刘际涛",
              dept_id: "88",
              dept_name: "财务部",
            },
            roles: ["finance"],
            permissions: ["finops:app:view"],
            allowed: true,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url === "/api/tax-offset?month=2026-03") {
        currentSnapshot = responses.length > 1 ? responses.shift() ?? responses[0] : responses[0];
        return new Response(JSON.stringify(currentSnapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/tax-offset/calculate") {
        const jsonBody =
          typeof init?.body === "string" && init.body.length > 0
            ? (JSON.parse(init.body) as { selected_input_ids?: string[] })
            : {};
        const selectedInputIds = new Set(jsonBody.selected_input_ids ?? []);
        const lockedIds = new Set(currentSnapshot.locked_certified_input_ids);
        const selectedPlanTax = currentSnapshot.input_plan_items
          .filter((item) => selectedInputIds.has(item.id) && !lockedIds.has(item.id))
          .reduce((sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")), 0);
        const certifiedTax = currentSnapshot.certified_items.reduce(
          (sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")),
          0,
        );
        const outputTax = currentSnapshot.output_items.reduce(
          (sum, item) => sum + Number(item.tax_amount.replace(/,/g, "")),
          0,
        );
        const deductibleTax = Math.min(outputTax, certifiedTax + selectedPlanTax);
        const resultAmount = outputTax - deductibleTax;
        return new Response(
          JSON.stringify({
            month: "2026-03",
            summary: {
              output_tax: outputTax.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
              certified_input_tax: certifiedTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              planned_input_tax: selectedPlanTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              input_tax: (certifiedTax + selectedPlanTax).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              deductible_tax: deductibleTax.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
              result_label: "本月应纳税额",
              result_amount: resultAmount.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }),
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /11203490/ })).not.toBeDisabled();
    expect(screen.getAllByText("当前分组暂无记录")).toHaveLength(2);
    const countTaxOffsetLoads = () => fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/api/tax-offset?month=2026-03"
    )).length;
    const initialRequestCount = countTaxOffsetLoads();

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      await Promise.resolve();
    });

    expect(countTaxOffsetLoads()).toBe(initialRequestCount);
    expect(within(getStatCard("已认证结果进项税额")).getByText("0.00")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /11203490/ })).not.toBeDisabled();
    expect(screen.queryByRole("button", { name: /11203999/ })).not.toBeInTheDocument();
  });

  test("treats a canonical empty response as final and never starts legacy refresh polling", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(JSON.stringify({
          user: { user_id: "101", username: "liuji", display_name: "刘际涛" },
          roles: ["finance"],
          permissions: ["finops:app:view"],
          allowed: true,
          can_access_app: true,
          can_mutate_data: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset?month=2026-03") {
        return new Response(JSON.stringify({
          month: "2026-03",
          canonical_snapshot_version: "tax-offset-v1:empty",
          summary: {
            output_tax: "0.00",
            certified_input_tax: "0.00",
            planned_input_tax: "0.00",
            input_tax: "0.00",
            deductible_tax: "0.00",
            result_label: "本月留抵税额",
            result_amount: "0.00",
          },
          output_items: [],
          input_plan_items: [],
          certified_items: [],
          certified_matched_rows: [],
          certified_outside_plan_rows: [],
          locked_certified_input_ids: [],
          default_selected_output_ids: [],
          default_selected_input_ids: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "税金抵扣计划与试算" })).toBeInTheDocument();
    expect(await screen.findByText("当前月份没有可用于计划与试算的发票数据。")).toBeInTheDocument();
    expect(screen.queryByText(/读模型正在刷新/)).not.toBeInTheDocument();
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 1100));
    });
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/tax-offset?month=2026-03"),
    ).toHaveLength(1);
  });

  test("keeps certified import modal processing while queued import job completes", async () => {
    window.history.pushState({}, "", "/tax-offset");
    const user = userEvent.setup();
    let taxFetchCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url === "/api/session/me") {
        return new Response(JSON.stringify({
          user: { user_id: "101", username: "liuji", display_name: "刘际涛" },
          roles: ["finance"],
          permissions: ["finops:app:view"],
          allowed: true,
          can_access_app: true,
          can_mutate_data: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset?month=2026-03") {
        taxFetchCount += 1;
        const certified = taxFetchCount > 1;
        return new Response(JSON.stringify({
          month: "2026-03",
          canonical_snapshot_version: certified
            ? "tax-offset-v1:queued-certified"
            : "tax-offset-v1:queued-initial",
          output_items: [],
          input_plan_items: [],
          certified_items: certified ? [{ id: "tc-queued-1", invoice_no: "11203490", seller_name: "设备供应商", issue_date: "2026-03-22", tax_amount: "12,480.00", total_with_tax: "108,480.00", status: "已认证" }] : [],
          certified_matched_rows: [],
          certified_outside_plan_rows: certified ? [{ id: "tc-queued-1", invoice_no: "11203490", seller_name: "设备供应商", issue_date: "2026-03-22", tax_amount: "12,480.00", total_with_tax: "108,480.00", status: "已认证" }] : [],
          locked_certified_input_ids: [],
          default_selected_output_ids: [],
          default_selected_input_ids: [],
          summary: {
            output_tax: "0.00",
            certified_input_tax: certified ? "12,480.00" : "0.00",
            planned_input_tax: "0.00",
            input_tax: certified ? "12,480.00" : "0.00",
            deductible_tax: "0.00",
            result_label: "本月留抵税额",
            result_amount: certified ? "12,480.00" : "0.00",
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset/certified-import/preview") {
        return new Response(JSON.stringify({
          session: { id: "tax-certified-session-queued", imported_by: "liuji", file_count: 1, status: "preview_ready" },
          files: [{
            id: "tax-certified-file-0001",
            file_name: "queued.xlsx",
            month: "2026-03",
            recognized_count: 1,
            invalid_count: 0,
            matched_plan_count: 0,
            outside_plan_count: 1,
            rows: [{ id: "tc-queued-1", month: "2026-03", invoice_no: "11203490", seller_name: "设备供应商", issue_date: "2026-03-22", tax_amount: "12,480.00", deductible_tax_amount: "12,480.00", source_file_name: "queued.xlsx", source_row_number: 4 }],
          }],
          summary: { recognized_count: 1, invalid_count: 0, matched_plan_count: 0, outside_plan_count: 1 },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset/certified-import/confirm") {
        expect(JSON.parse(String(init?.body))).toEqual({ session_id: "tax-certified-session-queued" });
        return new Response(JSON.stringify({
          status: "queued",
          import_job: {
            import_job_id: "import-job-tax-1",
            import_type: "tax_certified_import.confirm",
            status: "queued",
            stage: "queued",
            priority: "normal",
            attempt_count: 0,
            max_attempts: 5,
          },
        }), { status: 202, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/tax-offset/certified-import/jobs/import-job-tax-1") {
        return new Response(JSON.stringify({
          import_job: {
            import_job_id: "import-job-tax-1",
            import_type: "tax_certified_import.confirm",
            status: "succeeded",
            stage: "succeeded",
            priority: "normal",
            attempt_count: 1,
            max_attempts: 5,
            result_payload: {
              success: true,
              batch: {
                id: "tax-certified-batch-queued",
                session_id: "tax-certified-session-queued",
                imported_by: "liuji",
                file_count: 1,
                months: ["2026-03"],
                persisted_record_count: 1,
              },
            },
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("销项税额")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已认证发票导入" }));
    const modal = screen.getByRole("dialog", { name: "已认证发票导入" });
    await user.upload(within(modal).getByLabelText("选择已认证发票文件"), new File(["mock"], "queued.xlsx"));
    await user.click(within(modal).getByRole("button", { name: "预览识别结果" }));
    expect(await within(modal).findByText(/识别记录\s*1\s*条/)).toBeInTheDocument();
    await user.click(within(modal).getByRole("button", { name: "确认导入" }));

    expect(await within(modal).findByText("已提交导入任务，正在等待后台确认结果...")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "已认证发票导入" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText("已导入 1 条已认证记录，并已刷新当前税金抵扣页面。")).toBeInTheDocument();
    expect(within(getStatCard("已认证结果进项税额")).getByText("12,480.00")).toBeInTheDocument();
  });
});
