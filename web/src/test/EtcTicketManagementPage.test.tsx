import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ETC ticket management page", () => {
  test("refreshes batch list when ETC import background job completes", async () => {
    const fetchMock = installMockApiFetch({
      backgroundJobs: [
        {
          job_id: "job_etc_import_0001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "导入 ETC发票完成 4/4",
          status: "succeeded",
          phase: "complete",
          current: 4,
          total: 4,
          percent: 100,
          message: "ETC发票导入完成。",
          result_summary: { created: 1, imported: 1, updated: 1, attachments_completed: 1, duplicates: 1, failed: 1, total: 4 },
          error: null,
          created_at: "2026-05-03T10:00:00+00:00",
          updated_at: "2026-05-03T10:00:04+00:00",
          finished_at: "2026-05-03T10:00:04+00:00",
        },
      ],
    });
    renderAppAt("/etc-tickets");

    await screen.findByTestId("etc-ticket-management-page");

    await waitFor(() => {
      const batchListCalls = fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/etc/batches?"));
      expect(batchListCalls.length).toBeGreaterThanOrEqual(2);
    });
  });

  test("unsubmitted mode shows batch list and whole-batch OA submit action", async () => {
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).getByRole("heading", { name: "ETC票据管理" })).toBeInTheDocument();
    expect(await within(page).findByRole("button", { name: "未提交 2" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("list", { name: "ETC批次列表" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-01")).toHaveTextContent("ETC-2026-03-A");
    expect(within(page).getByRole("button", { name: "提交OA支付申请" })).toBeEnabled();
    expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1);
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches?status=unsubmitted&page=1&page_size=100",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/etc/invoices?"))).toBe(false);
  });

  test("submitted mode hides submit action and shows OA information", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByRole("button", { name: "已提交 1" }));

    await waitFor(() => expect(within(page).getAllByText("ETC-HIST-2026-01").length).toBeGreaterThanOrEqual(1));
    expect(within(page).queryByRole("button", { name: "提交OA支付申请" })).not.toBeInTheDocument();
    expect(within(page).getAllByText(/刘树刚 \/ 2026-02-02 \/ OA 31.80/).length).toBeGreaterThanOrEqual(1);
    expect(within(page).getByRole("button", { name: "撤销提交状态" })).toBeEnabled();
  });

  test("clicking a batch updates the detail grid", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(await within(page).findByText("ETC-2026-001")).toBeInTheDocument();
    expect(within(page).queryByText("ETC-2026-003")).not.toBeInTheDocument();

    await user.click(within(within(page).getByTestId("etc-batch-row-etc-batch-unsubmitted-02")).getByRole("button"));

    await waitFor(() => expect(within(page).getAllByText("ETC-2026-03-B").length).toBeGreaterThanOrEqual(1));
    await waitFor(() => {
      expect(within(page).getByText("ETC-2026-003")).toBeInTheDocument();
      expect(within(page).queryByText("ETC-2026-001")).not.toBeInTheDocument();
    });
  });

  test("removes basket wording and old partial-selection actions", async () => {
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await within(page).findByRole("list", { name: "ETC批次列表" });

    expect(within(page).queryByText("提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("加入提交篮子")).not.toBeInTheDocument();
    expect(within(page).queryByText("移回未提交")).not.toBeInTheDocument();
    expect(within(page).queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("creates OA draft through the selected batch endpoint and refreshes after confirmation", async () => {
    const user = userEvent.setup();
    const openedWindow = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
      opener: {},
    };
    const openMock = vi.fn(() => openedWindow);
    vi.stubGlobal("open", openMock);
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await waitFor(() => expect(within(page).getAllByText("ETC-2026-03-A").length).toBeGreaterThanOrEqual(1));
    await user.click(within(page).getByRole("button", { name: "提交OA支付申请" }));

    const dialog = await screen.findByRole("dialog", { name: "创建OA支付申请草稿" });
    expect(dialog).toHaveTextContent("将为当前 ETC 批次创建 OA 支付申请草稿");
    expect(dialog).toHaveTextContent("当前批次：ETC-2026-03-A");
    await user.click(within(dialog).getByRole("button", { name: "确认创建草稿" }));

    expect(openMock).toHaveBeenCalledWith("about:blank", "_blank");
    await waitFor(() => expect(openedWindow.location.href).toContain("https://oa.example.test/oa/#/normal/forms/form/2"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc-batch-unsubmitted-01/draft",
      expect.objectContaining({ method: "POST" }),
    );

    const resultDialog = await screen.findByRole("dialog", { name: "OA提交结果确认" });
    expect(resultDialog).toHaveTextContent("批次号：ETC-2026-03-A");
    await user.click(within(resultDialog).getByRole("button", { name: "确认已提交OA" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc-batch-unsubmitted-01/confirm-submitted",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await within(page).findByRole("button", { name: "未提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 2" })).toBeInTheDocument();
  });
});
