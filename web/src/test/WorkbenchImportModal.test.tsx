import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

const WORKBENCH_RENDER_TIMEOUT = 3000;

async function openWorkbenchImportMenu(user: ReturnType<typeof userEvent.setup>) {
  const trigger = await screen.findByRole("button", { name: "导入中心" }, { timeout: WORKBENCH_RENDER_TIMEOUT });
  await user.hover(trigger);
  return trigger;
}

describe("Workbench import modal", () => {
  test("keeps the import modal open when clicking the backdrop and closes from the close button", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "银行流水导入" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水导入" });

    const backdrop = document.querySelector(".export-center-modal-backdrop");
    expect(backdrop).toBeInTheDocument();

    fireEvent.click(backdrop as Element);
    expect(screen.getByRole("dialog", { name: "银行流水导入" })).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "银行流水导入" })).not.toBeInTheDocument();
  });

  test("bank import uses concrete bank account mapping options and sends mapping fields in preview payload", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "银行流水导入" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水导入" });
    const input = within(dialog).getByLabelText("上传银行流水文件") as HTMLInputElement;
    const bankFile = new File(["bank-demo"], "historydetail14080.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });

    await user.upload(input, [bankFile]);

    const bankSelect = within(dialog).getByLabelText("对应账户 historydetail14080.xlsx");
    expect(within(bankSelect).getByRole("option", { name: "建设银行 8826" })).toBeInTheDocument();

    const previewButton = within(dialog).getByRole("button", { name: "开始预览" });
    expect(previewButton).toBeDisabled();

    await user.selectOptions(bankSelect, "bank_mapping_8826");
    expect(previewButton).toBeEnabled();

    await user.click(previewButton);

    expect(await within(dialog).findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();
    const previewCall = fetchMock.mock.calls.find(([url]) => String(url) === "/imports/files/preview");
    expect(previewCall).toBeTruthy();
    const formData = (previewCall?.[1] as RequestInit).body as FormData;
    expect(JSON.parse(String(formData.get("file_overrides")))).toEqual([
      {
        file_name: "historydetail14080.xlsx",
        batch_type: "bank_transaction",
        bank_mapping_id: "bank_mapping_8826",
        bank_name: "建设银行",
        bank_short_name: "建行",
        last4: "8826",
      },
    ]);
  });

  test("bank import blocks confirm behind a conflict dialog when selected mapping mismatches detected account", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "银行流水导入" }));
    const dialog = await screen.findByRole("dialog", { name: "银行流水导入" });
    const input = within(dialog).getByLabelText("上传银行流水文件") as HTMLInputElement;
    const bankFile = new File(["bank-demo"], "2026-01-01至2026-01-31交易明细.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 1,
    });

    await user.upload(input, [bankFile]);
    await user.selectOptions(within(dialog).getByLabelText("对应账户 2026-01-01至2026-01-31交易明细.xlsx"), "bank_mapping_8826");
    await user.click(within(dialog).getByRole("button", { name: "开始预览" }));

    expect(await within(dialog).findByText("已完成 1 个文件的预览识别。")).toBeInTheDocument();
    expect(within(dialog).getByText("银行选择为建设银行，系统识别为平安银行；后四位选择为8826，系统识别为0093")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认导入" }));

    const conflictDialog = await screen.findByRole("dialog", { name: "银行账户冲突确认" });
    expect(within(conflictDialog).getByText("2026-01-01至2026-01-31交易明细.xlsx")).toBeInTheDocument();
    expect(within(conflictDialog).getByText("建设银行 8826")).toBeInTheDocument();
    expect(within(conflictDialog).getByText("平安银行 0093")).toBeInTheDocument();
    expect(within(conflictDialog).getByRole("button", { name: "仍按所选账户 建设银行 8826 导入" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/imports/files/confirm",
      expect.anything(),
    );

    await user.click(within(conflictDialog).getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog", { name: "银行账户冲突确认" })).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "确认导入" }));
    const nextConflictDialog = await screen.findByRole("dialog", { name: "银行账户冲突确认" });
    await user.click(within(nextConflictDialog).getByRole("button", { name: "仍按所选账户 建设银行 8826 导入" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/imports/files/confirm",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  test("workbench import dropzone accepts dragged files", async () => {
    const user = userEvent.setup();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "发票导入" }));
    const dialog = await screen.findByRole("dialog", { name: "发票导入" });
    const dropzone = within(dialog).getByLabelText("上传发票文件");
    const invoiceFile = new File(["invoice"], "拖拽发票.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      lastModified: 3,
    });

    fireEvent.dragEnter(dropzone, {
      dataTransfer: { files: [invoiceFile] },
    });
    fireEvent.dragOver(dropzone, {
      dataTransfer: { files: [invoiceFile] },
    });
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [invoiceFile] },
    });

    expect(await within(dialog).findByText("拖拽发票.xlsx")).toBeInTheDocument();
  });

  test("workbench import dropzone rejects non-excel files with an immediate message", async () => {
    const user = userEvent.setup();
    renderAppAt("/");

    await openWorkbenchImportMenu(user);
    await user.click(await screen.findByRole("button", { name: "发票导入" }));
    const dialog = await screen.findByRole("dialog", { name: "发票导入" });
    const dropzone = within(dialog).getByLabelText("上传发票文件");
    const invalidFile = new File(["text"], "说明.txt", {
      type: "text/plain",
      lastModified: 4,
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

    expect(await within(dialog).findByText("仅支持 .xls/.xlsx")).toBeInTheDocument();
    expect(within(dialog).queryByText("说明.txt")).not.toBeInTheDocument();
  });
});
