import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import ConfirmActionDialog from "../components/common/ConfirmActionDialog";
import FileDropzone from "../components/common/FileDropzone";
import StatePanel from "../components/common/StatePanel";

function renderWithMui(ui: React.ReactElement) {
  return render(<MuiProviders>{ui}</MuiProviders>);
}

describe("common MUI components", () => {
  test("renders loading and error state panels with accessible roles", () => {
    renderWithMui(
      <>
        <StatePanel tone="loading" title="正在加载">
          请稍候
        </StatePanel>
        <StatePanel tone="error" title="保存失败">
          后端拒绝了请求
        </StatePanel>
      </>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("正在加载");
    expect(screen.getByRole("alert")).toHaveTextContent("保存失败");
  });

  test("confirms and cancels actions through the shared dialog", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    renderWithMui(
      <ConfirmActionDialog
        open
        title="确认撤销"
        description="撤销后会重新回到待处理状态。"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByRole("button", { name: "确认" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  test("emits dropped files from the shared dropzone", () => {
    const onFiles = vi.fn();
    const file = new File(["a,b"], "bank.csv", { type: "text/csv" });

    renderWithMui(<FileDropzone label="上传银行流水" onFiles={onFiles} />);

    fireEvent.drop(screen.getByRole("button", { name: "上传银行流水" }), {
      dataTransfer: {
        files: [file],
      },
    });

    expect(onFiles).toHaveBeenCalledWith([file]);
  });
});
