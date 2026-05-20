import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

function installSettingsTagFetch() {
  const baseFetch = installMockApiFetch();
  let settingsVersion = 4;
  const settingsPayload = () => ({
    projects: { active: [], completed: [], completed_project_ids: [] },
    bank_account_mappings: [],
    access_control: { allowed_usernames: [], readonly_export_usernames: [], admin_usernames: [], full_access_usernames: [] },
    workbench_column_layouts: { oa: [], bank: [], invoice: [] },
    oa_retention: { cutoff_date: "2026-01-01" },
    oa_import: { form_types: ["payment_request"], statuses: ["completed"] },
    oa_invoice_offset: { applicant_names: [] },
    bank_transaction_tags: {
      version: settingsVersion,
      tags: [
        { code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" },
        { code: "salary", label: "工资", path: ["自动识别", "工资"], status: "active", source: "system" },
        { code: "internal_transfer", label: "内部往来款", path: ["自动识别", "内部往来款"], status: "active", source: "system" },
      ],
    },
    pending_invoice_tag_groups: {
      requires_invoice: ["fee"],
      bank_statement_as_invoice: [],
      no_invoice_required: ["salary"],
    },
  });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/workbench/settings") {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        settingsVersion = 5;
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body.bank_transaction_tags).toMatchObject({
          definitions: expect.arrayContaining([
            expect.objectContaining({ code: "fee" }),
          ]),
        });
        expect(body.bank_transaction_tags).not.toHaveProperty("tags");
        expect(body.pending_invoice_tag_groups).toMatchObject({
          groups: {
            requires_invoice: { tag_codes: expect.arrayContaining(["fee", "internal_transfer"]) },
          },
        });
      }
      return new Response(JSON.stringify(settingsPayload()), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Settings page", () => {
  test("renders as a tree-and-panel page without an extra page header title", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "关联台设置" })).not.toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    expect(tree).toHaveClass("MuiList-root");
    expect(within(tree).getByRole("treeitem", { name: /项目状态/ })).toHaveAttribute("aria-selected", "true");

    expect(screen.getByRole("region", { name: "项目状态管理" })).toBeInTheDocument();
  });

  test("switches the content panel when selecting another settings section", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /银行账户/ }));

    expect(screen.getByRole("region", { name: "银行账户映射" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "项目状态管理" })).not.toBeInTheDocument();
  });

  test("keeps workbench-only header actions out of standalone settings", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
  });

  test("keeps read-only settings users from saving changes", async () => {
    installMockApiFetch({
      sessionAccessTier: "read_export_only",
      sessionUsername: "READONLY001",
    });
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.getByText("当前账号仅支持查看和导出，不能保存设置。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
  });

  test("keeps data reset behind impact confirmation, OA password review, and job progress", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      dataResetJobPollsBeforeComplete: 1,
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /数据重置/ }));
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "确认数据重置" });
    expect(confirmDialog).toBeInTheDocument();
    expect(within(confirmDialog).getByText("已导入银行流水会被清空")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "继续" }));
    expect(await screen.findByRole("dialog", { name: "OA 密码复核" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("当前 OA 用户密码"), "oa-password");
    await user.click(screen.getByRole("button", { name: "确认清理" }));

    expect(await within(settingsPage).findByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/data-reset/jobs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"oa_password\":\"oa-password\""),
      }),
    );
  });

  test("manages pending invoice tag mappings and broadcasts saved tag version", async () => {
    const user = userEvent.setup();
    const fetchMock = installSettingsTagFetch();
    const listener = vi.fn();
    window.addEventListener("finops:bank-transaction-tags-updated", listener);
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = within(settingsPage).getByRole("tree", { name: "设置分类" });
    expect(within(tree).getByRole("treeitem", { name: /银行流水标签/ })).toBeInTheDocument();
    await user.click(within(tree).getByRole("treeitem", { name: /待找发票筛选/ }));

    const region = within(settingsPage).getByRole("region", { name: "待找发票筛选" });
    expect(within(region).getByText("需要开票")).toBeInTheDocument();
    expect(within(region).getByText("流水代替发票")).toBeInTheDocument();
    expect(within(region).getByText("无需开票")).toBeInTheDocument();
    await user.click(within(region).getByRole("button", { name: "选择现有标签" }));
    await user.click(await screen.findByRole("menuitem", { name: "内部往来款" }));
    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/workbench/settings" && (init?.method ?? "GET").toUpperCase() === "POST";
      })).toBe(true);
      expect(listener).toHaveBeenCalledWith(expect.objectContaining({ detail: { version: 5 } }));
    });

    window.removeEventListener("finops:bank-transaction-tags-updated", listener);
  });
});
