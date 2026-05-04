import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

function getUploadInput(...labels: string[]) {
  for (const label of labels) {
    const input = screen.queryByLabelText(label);
    if (input) {
      return input as HTMLInputElement;
    }
  }
  throw new Error(`Missing upload input for labels: ${labels.join(", ")}`);
}

function getPreviewFormData(fetchMock: ReturnType<typeof installMockApiFetch>) {
  const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
  expect(previewCall).toBeTruthy();
  return (previewCall?.[1] as RequestInit).body as FormData;
}

function getFileOverrides(formData: FormData) {
  return JSON.parse(String(formData.get("file_overrides")));
}

describe("Import pages", () => {
  test("bank transaction import uses the standalone route and sends bank mapping overrides", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/bank-transactions");

    expect(await screen.findByRole("heading", { name: "银行流水导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "银行流水导入" })).not.toBeInTheDocument();

    await user.upload(getUploadInput("上传银行流水文件", "上传文件"), [
      new File(["bank-demo"], "historydetail14080.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["bank-demo-2"], "2026-01-01至2026-01-31交易明细.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("对应账户 historydetail14080.xlsx"), "bank_mapping_8826");
    await user.selectOptions(screen.getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    expect(previewButton).toBeEnabled();
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
    const formData = getPreviewFormData(fetchMock);
    expect((formData.getAll("files") as File[]).map((file) => file.name)).toEqual([
      "historydetail14080.xlsx",
      "2026-01-01至2026-01-31交易明细.xlsx",
    ]);
    expect(getFileOverrides(formData)).toEqual([
      {
        file_name: "historydetail14080.xlsx",
        batch_type: "bank_transaction",
        bank_mapping_id: "bank_mapping_8826",
        bank_name: "建设银行",
        bank_short_name: "建行",
        last4: "8826",
      },
      {
        file_name: "2026-01-01至2026-01-31交易明细.xlsx",
        batch_type: "bank_transaction",
        bank_mapping_id: "bank_mapping_8826",
        bank_name: "建设银行",
        bank_short_name: "建行",
        last4: "8826",
      },
    ]);
  });

  test("invoice import uses the standalone route and sends per-file directions", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/invoices");

    expect(await screen.findByRole("heading", { name: "发票导入" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "销项发票导入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "进项发票导入" })).not.toBeInTheDocument();

    await user.upload(getUploadInput("上传发票文件", "上传文件"), [
      new File(["invoice-output"], "一月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 1,
      }),
      new File(["invoice-input"], "二月发票.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        lastModified: 2,
      }),
    ]);
    const previewButton = screen.getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("票据方向 一月发票.xlsx"), "output_invoice");
    await user.selectOptions(screen.getByLabelText("票据方向 二月发票.xlsx"), "input_invoice");
    await user.click(previewButton);

    expect(await screen.findByText("已完成 2 个文件的预览识别。")).toBeInTheDocument();
    expect(getFileOverrides(getPreviewFormData(fetchMock))).toEqual([
      {
        file_name: "一月发票.xlsx",
        template_code: "invoice_export",
        batch_type: "output_invoice",
      },
      {
        file_name: "二月发票.xlsx",
        template_code: "invoice_export",
        batch_type: "input_invoice",
      },
    ]);
  });

  test("ETC invoice import rejects non-zip files on the standalone route", async () => {
    const user = userEvent.setup({ applyAccept: false });
    installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["not zip"], "README.md", { type: "text/markdown" }),
      new File(["xlsx"], "etc.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    ]);

    expect(screen.getAllByText("ETC发票导入仅支持 zip 文件，已拒绝 2 个非 zip 文件。").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
  });

  test("ETC invoice import previews zip files with the ETC API and skips generic preview", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
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

  test("ETC invoice import confirms the preview session and shows background job feedback", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    renderAppAt("/imports/etc-invoices");

    expect(await screen.findByRole("heading", { name: "ETC发票导入" })).toBeInTheDocument();
    await user.upload(getUploadInput("上传ETC zip", "上传文件"), [
      new File(["zip-a"], "etc-2026-03.zip", { type: "application/zip" }),
    ]);
    await user.click(screen.getByRole("button", { name: "开始预览" }));

    expect(await screen.findByRole("heading", { name: "ETC导入预览" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /确认导入/ }));

    await waitFor(() => {
      expect(screen.getAllByText("已开始后台导入").length).toBeGreaterThan(0);
    });
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/etc/import/confirm");
    expect(confirmCall).toBeTruthy();
    expect(JSON.parse(String((confirmCall?.[1] as RequestInit).body))).toEqual({
      sessionId: "etc_import_session_0001",
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/imports/files/preview")).toBe(false);
  });
});
