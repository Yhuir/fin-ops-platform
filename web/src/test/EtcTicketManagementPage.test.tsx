import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ETC ticket management page", () => {
  test("navigation opens ETC page and displays status and current list counts", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/");

    await user.click(await screen.findByRole("link", { name: "ETC票据管理" }));

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).getByRole("heading", { name: "ETC票据管理" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "未提交 3" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(within(page).getByRole("heading", { name: "未提交发票 3 张" })).toBeInTheDocument();
    expect(within(page).getByRole("heading", { name: "待提交 0 张" })).toBeInTheDocument();
  });

  test("adds unsubmitted invoices to basket once, totals amount, and moves selected items back", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByLabelText("选择发票 ETC-2026-001"));
    await user.click(within(page).getByRole("button", { name: "加入提交篮子" }));
    await user.click(within(page).getByRole("button", { name: "加入提交篮子" }));

    expect(within(page).getByRole("heading", { name: "待提交 1 张" })).toBeInTheDocument();
    expect(within(page).getByText("合计金额 13.07")).toBeInTheDocument();

    await user.click(within(page).getByLabelText("从提交篮子选择发票 ETC-2026-001"));
    await user.click(within(page).getByRole("button", { name: "移回未提交" }));

    expect(within(page).getByRole("heading", { name: "待提交 0 张" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "提交OA支付申请" })).toBeDisabled();
  });

  test("submitted invoices are muted, cannot enter basket, and can be revoked after confirmation", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(within(page).getByRole("button", { name: "已提交 1" }));

    expect(within(page).getByRole("heading", { name: "已提交发票 1 张" })).toBeInTheDocument();
    expect(within(page).getByTestId("etc-invoice-row-etc-inv-004")).toHaveClass("submitted");
    expect(within(page).queryByRole("button", { name: "加入提交篮子" })).not.toBeInTheDocument();

    await user.click(within(page).getByLabelText("选择发票 ETC-2026-004"));
    await user.click(within(page).getByRole("button", { name: "撤销提交状态" }));
    expect(await screen.findByRole("dialog", { name: "撤销提交状态" })).toHaveTextContent("只修改 fin-ops 内部 ETC 发票状态");
    await user.click(screen.getByRole("button", { name: "确认撤销" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/invoices/revoke-submitted",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ invoiceIds: ["etc-inv-004"] }),
      }),
    );
    expect(await within(page).findByRole("button", { name: "未提交 4" })).toBeInTheDocument();
  });

  test("links to import center instead of importing ETC zip files directly", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    expect(within(page).queryByLabelText("导入ETC zip")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "导入zip" })).not.toBeInTheDocument();
    expect(within(page).queryByRole("region", { name: "导入摘要" })).not.toBeInTheDocument();

    await user.click(within(page).getByRole("link", { name: "去导入中心导入 ETC 发票" }));

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/etc/import",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
  });

  test("creates OA draft, opens draft URL, and refreshes after result confirmation", async () => {
    const user = userEvent.setup();
    const openMock = vi.fn();
    vi.stubGlobal("open", openMock);
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByLabelText("选择发票 ETC-2026-001"));
    await user.click(within(page).getByRole("button", { name: "加入提交篮子" }));
    await user.click(within(page).getByRole("button", { name: "提交OA支付申请" }));

    const dialog = await screen.findByRole("dialog", { name: "创建OA支付申请草稿" });
    expect(dialog).toHaveTextContent("将创建 OA 支付申请草稿");
    expect(dialog).toHaveTextContent("将跳转 OA 页面");
    expect(dialog).toHaveTextContent("app 不会自动提交 OA");
    expect(dialog).toHaveTextContent("需要在 OA 中检查并手动提交");
    await user.click(within(dialog).getByRole("button", { name: "确认创建草稿" }));

    expect(openMock).toHaveBeenCalledWith("https://oa.example.test/etc-draft-001", "_blank", "noopener,noreferrer");
    const resultDialog = await screen.findByRole("dialog", { name: "OA提交结果确认" });
    expect(within(resultDialog).getByRole("button", { name: "确认已提交OA" })).toBeInTheDocument();
    expect(within(resultDialog).getByRole("button", { name: "未提交OA" })).toBeInTheDocument();

    await user.click(within(resultDialog).getByRole("button", { name: "确认已提交OA" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc_batch_001/confirm-submitted",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await within(page).findByRole("button", { name: "未提交 2" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 2" })).toBeInTheDocument();
  });

  test("marking the OA draft as not submitted keeps invoice unsubmitted", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("open", vi.fn());
    const fetchMock = installMockApiFetch();
    renderAppAt("/etc-tickets");

    const page = await screen.findByTestId("etc-ticket-management-page");
    await user.click(await within(page).findByLabelText("选择发票 ETC-2026-002"));
    await user.click(within(page).getByRole("button", { name: "加入提交篮子" }));
    await user.click(within(page).getByRole("button", { name: "提交OA支付申请" }));
    await user.click(within(await screen.findByRole("dialog", { name: "创建OA支付申请草稿" })).getByRole("button", { name: "确认创建草稿" }));
    await user.click(within(await screen.findByRole("dialog", { name: "OA提交结果确认" })).getByRole("button", { name: "未提交OA" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/etc/batches/etc_batch_001/mark-not-submitted",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await within(page).findByRole("button", { name: "未提交 3" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
  });
});
