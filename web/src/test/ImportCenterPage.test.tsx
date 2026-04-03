import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderAppAt } from "./renderHelpers";
import { installMockApiFetch } from "./apiMock";

function hasExactTextContent(text: string) {
  return (_content: string, element: Element | null) => element?.textContent?.trim() === text;
}

describe("Import center", () => {
  test("uploads multiple files for preview and shows recognized template results", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    expect(screen.getByRole("heading", { name: "导入中心" })).toBeInTheDocument();

    const input = screen.getByLabelText("上传文件") as HTMLInputElement;
    const invoiceFile = new File(["invoice-demo"], "全量发票查询导出结果-2026年1月.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const badFile = new File(["bad-demo"], "README.md", { type: "text/markdown" });

    await user.upload(input, [invoiceFile, bankFile, badFile]);
    expect(screen.getByText("已选择 3 个文件，等待预览")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByText("全量发票查询导出结果-2026年1月.xlsx")).toBeInTheDocument();
    expect(screen.getAllByText("已完成 3 个文件的预览识别。").length).toBeGreaterThan(0);
    expect(screen.getByText("historydetail14080.xlsx")).toBeInTheDocument();
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getAllByText("发票导出").length).toBeGreaterThan(0);
    expect(screen.getAllByText("工商银行流水").length).toBeGreaterThan(0);
    expect(screen.getByText("无法识别文件模板。")).toBeInTheDocument();

    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
    expect(previewCall).toBeTruthy();
    const init = previewCall?.[1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    const formData = init.body as FormData;
    expect(formData.get("imported_by")).toBe("web_finance_user");
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "全量发票查询导出结果-2026年1月.xlsx",
      "historydetail14080.xlsx",
      "README.md",
    ]);
  });

  test("appends files across multiple selections instead of overwriting earlier picks", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    const input = screen.getByLabelText("上传文件") as HTMLInputElement;
    const invoiceFile = new File(["invoice-demo"], "全量发票查询导出结果-2026年1月.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 2,
    });
    const badFile = new File(["bad-demo"], "README.md", { type: "text/markdown", lastModified: 3 });

    await user.upload(input, [invoiceFile, bankFile]);
    expect(screen.getByText(hasExactTextContent("当前已选择 2 个文件"))).toBeInTheDocument();
    expect(screen.getByText("已选择 2 个文件，等待预览")).toBeInTheDocument();

    await user.upload(input, [badFile]);
    expect(screen.getByText(hasExactTextContent("当前已选择 3 个文件"))).toBeInTheDocument();
    expect(screen.getByText("已选择 3 个文件，等待预览")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "开始预览" }));

    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
    expect(previewCall).toBeTruthy();
    const init = previewCall?.[1] as RequestInit;
    const formData = init.body as FormData;
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "全量发票查询导出结果-2026年1月.xlsx",
      "historydetail14080.xlsx",
      "README.md",
    ]);
  });

  test("confirms only selected preview files", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    const input = screen.getByLabelText("上传文件") as HTMLInputElement;
    const invoiceFile = new File(["invoice-demo"], "全量发票查询导出结果-2026年1月.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(input, [invoiceFile, bankFile]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByText("全量发票查询导出结果-2026年1月.xlsx")).toBeInTheDocument();

    await user.click(screen.getByLabelText("选择 historydetail14080.xlsx"));
    await user.click(screen.getByRole("button", { name: "确认导入选中文件" }));

    await waitFor(() => {
      expect(screen.getByText("已确认导入")).toBeInTheDocument();
    });
    expect(screen.getByText("已跳过")).toBeInTheDocument();

    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/confirm");
    expect(confirmCall).toBeTruthy();
    const confirmBody = JSON.parse(String((confirmCall?.[1] as RequestInit).body));
    expect(confirmBody.selected_file_ids).toEqual(["import_file_0001"]);
  });

  test("loads templates and allows retry with invoice batch override", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    expect(await screen.findByRole("heading", { name: "模板库" })).toBeInTheDocument();
    expect(screen.getAllByText("发票导出").length).toBeGreaterThan(0);
    expect(screen.getAllByText("建设银行流水").length).toBeGreaterThan(0);

    const input = screen.getByLabelText("上传文件") as HTMLInputElement;
    const invoiceFile = new File(["invoice-demo"], "全量发票查询导出结果-2026年1月.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(input, [invoiceFile]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByText("全量发票查询导出结果-2026年1月.xlsx")).toBeInTheDocument();
    expect(screen.getAllByText("进项发票").length).toBeGreaterThan(0);

    await user.selectOptions(
      screen.getByLabelText("票据方向 全量发票查询导出结果-2026年1月.xlsx"),
      "output_invoice",
    );
    await user.click(screen.getByRole("button", { name: "重新识别 全量发票查询导出结果-2026年1月.xlsx" }));

    await waitFor(() => {
      expect(screen.getAllByText("销项发票").length).toBeGreaterThan(0);
    });

    const retryCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/retry");
    expect(retryCall).toBeTruthy();
    const retryBody = JSON.parse(String((retryCall?.[1] as RequestInit).body));
    expect(retryBody.selected_file_ids).toEqual(["import_file_0001"]);
    expect(retryBody.overrides).toEqual({
      import_file_0001: {
        batch_type: "output_invoice",
        template_code: "invoice_export",
      },
    });
  });

  test("shows matching feedback and supports batch download plus revert", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    const input = screen.getByLabelText("上传文件") as HTMLInputElement;
    const invoiceFile = new File(["invoice-demo"], "全量发票查询导出结果-2026年1月.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.upload(input, [invoiceFile]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));
    expect(await screen.findByText("全量发票查询导出结果-2026年1月.xlsx")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确认导入选中文件" }));

    expect(await screen.findByRole("heading", { name: "导入闭环结果" })).toBeInTheDocument();
    const automaticCard = screen.getByText("自动匹配").closest(".stat-card");
    expect(automaticCard).not.toBeNull();
    expect(within(automaticCard as HTMLElement).getByText("1")).toBeInTheDocument();

    const downloadLink = screen.getByRole("link", { name: "下载批次 import_file_0001" });
    expect(downloadLink).toHaveAttribute("href", "/imports/batches/batch_import_4444/download");

    await user.click(screen.getByRole("button", { name: "撤销导入 import_file_0001" }));

    await waitFor(() => {
      expect(screen.getByText("已撤销")).toBeInTheDocument();
    });

    const revertCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/batches/batch_import_4444/revert");
    expect(revertCall).toBeTruthy();
  });
});
