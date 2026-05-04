import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderAppAt } from "./renderHelpers";
import { installMockApiFetch } from "./apiMock";

function hasExactTextContent(text: string) {
  return (_content: string, element: Element | null) => element?.textContent?.trim() === text;
}

describe("Import center", () => {
  test("renders the shared MUI file dropzone controls", async () => {
    installMockApiFetch();

    renderAppAt("/imports?intent=bank_transaction");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上传文件" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "浏览文件" })).toBeInTheDocument();
    expect(screen.getByText(hasExactTextContent("当前已选择 0 个文件"))).toBeInTheDocument();
  });

  test("renders ETC invoice import without generic template workflow or unsupported notice", async () => {
    installMockApiFetch();

    renderAppAt("/imports?intent=etc_invoice");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    expect(screen.getByText("仅支持 zip，先预览再确认导入 ETC票据管理。")).toBeInTheDocument();
    expect(screen.queryByText("当前入口已保留")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "模板库" })).not.toBeInTheDocument();
    expect(screen.queryByText("模板改判")).not.toBeInTheDocument();
  });

  test("rejects non-zip files for ETC import and keeps preview unavailable", async () => {
    const user = userEvent.setup({ applyAccept: false });
    installMockApiFetch();

    renderAppAt("/imports?intent=etc_invoice");

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
    await user.upload(input, [
      new File(["not zip"], "README.md", { type: "text/markdown" }),
      new File(["xlsx"], "etc.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(screen.getAllByText("ETC发票导入仅支持 zip 文件，已拒绝 2 个非 zip 文件。").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
    expect(screen.getByText(hasExactTextContent("当前已选择 0 个文件"))).toBeInTheDocument();
  });

  test("previews multiple ETC zip files with ETC endpoint and does not confirm", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports?intent=etc_invoice");

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
    await user.upload(input, [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
      new File(["zip-b"], "etc-2026-04.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
    expect(screen.getByText("etc_import_session_0001")).toBeInTheDocument();
    expect(screen.getByText("ETC-2026-005")).toBeInTheDocument();
    expect(screen.getAllByText("etc-2026-03.zip").length).toBeGreaterThan(0);
    expect(screen.getByText("新发票待导入")).toBeInTheDocument();
    expect(screen.getAllByText("附件补齐").length).toBeGreaterThan(0);

    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "etc-2026-03.zip",
      "etc-2026-04.zip",
    ]);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/etc/import/confirm")).toBe(false);
  });

  test("confirms ETC preview session and shows background job feedback", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports?intent=etc_invoice");

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
    await user.upload(input, [new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" })]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认导入 ETC票据管理" }));

    await waitFor(() => {
      expect(screen.getAllByText("已开始后台导入").length).toBeGreaterThan(0);
    });
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/confirm");
    expect(confirmCall).toBeTruthy();
    expect(JSON.parse(String((confirmCall?.[1] as RequestInit).body))).toEqual({
      sessionId: "etc_import_session_0001",
    });
  });

  test("uploads multiple files for preview and shows recognized template results", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports");

    expect(await screen.findByRole("heading", { name: "导入中心" })).toBeInTheDocument();

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

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
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

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
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

    const input = (await screen.findByLabelText("上传文件")) as HTMLInputElement;
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
