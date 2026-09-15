import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type ManualBankTransactionBatchEditor from "../components/imports/ManualBankTransactionBatchEditor";
import ManualBankTransactionEntryDrawer from "../components/imports/ManualBankTransactionEntryDrawer";
import { discardImportSession } from "../features/imports/api";

vi.mock("../features/imports/api", async () => ({
  ...await vi.importActual<typeof import("../features/imports/api")>("../features/imports/api"),
  discardImportSession: vi.fn(),
}));
vi.mock("../components/imports/ManualBankTransactionBatchEditor", () => ({
  default: (props: ComponentProps<typeof ManualBankTransactionBatchEditor>) => <>
    <input aria-label="测试草稿" defaultValue="保留录入" />
    <button onClick={() => props.onPreviewSessionChange("synthetic-preview")}>建立预览</button>
    <button onClick={() => props.onBusyChange?.(true)}>开始处理</button>
    <button onClick={() => props.onBusyChange?.(false)}>完成处理</button>
  </>,
}));

afterEach(() => vi.resetAllMocks());

describe("bank entry drawer owner", () => {
  test("retains the draft on cleanup failure and retries cleanup only after another X", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    vi.mocked(discardImportSession).mockRejectedValueOnce(new Error("清理预览失败")).mockResolvedValueOnce();
    render(<ManualBankTransactionEntryDrawer bankAccounts={[]} open onClose={close} onImportAccepted={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "建立预览" }));
    await user.keyboard("{Escape}");
    expect(discardImportSession).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "关闭流水录入" }));
    expect(await screen.findByText("清理预览失败")).toBeVisible();
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "测试草稿" })).toHaveValue("保留录入");
    await user.click(screen.getByRole("button", { name: "关闭流水录入" }));
    await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
    expect(discardImportSession).toHaveBeenCalledTimes(2);
    expect(discardImportSession).toHaveBeenLastCalledWith("synthetic-preview");
  });

  test("blocks X while the editor is busy and releases it when processing finishes", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<ManualBankTransactionEntryDrawer bankAccounts={[]} open onClose={close} onImportAccepted={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "开始处理" }));
    const x = screen.getByRole("button", { name: "关闭流水录入" });
    expect(x).toBeDisabled();
    await user.click(x);
    expect(close).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "完成处理" }));
    expect(x).toBeEnabled();
    await user.click(x);
    expect(close).toHaveBeenCalledTimes(1);
    expect(discardImportSession).not.toHaveBeenCalled();
  });
});
