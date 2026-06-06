import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import AppDialog from "../components/common/AppDialog";
import ConfirmActionDialog from "../components/common/ConfirmActionDialog";
import FileDropzone from "../components/common/FileDropzone";
import PermissionNotice from "../components/common/PermissionNotice";
import StatePanel from "../components/common/StatePanel";

function renderWithMui(ui: React.ReactElement) {
  return render(<MuiProviders>{ui}</MuiProviders>);
}

describe("common MUI components", () => {
  test("renders state panels with accessible roles and loading affordances", () => {
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
    expect(screen.getByLabelText("加载中")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "加载进度" })).toBeInTheDocument();
  });

  test("keeps compact loading state concise", () => {
    renderWithMui(
      <StatePanel tone="loading" title="正在加载" compact>
        请稍候
      </StatePanel>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("正在加载");
    expect(screen.getByLabelText("加载中")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar", { name: "加载进度" })).not.toBeInTheDocument();
  });

  test("renders permission notice as a warning status", () => {
    renderWithMui(<PermissionNotice>当前账号没有审核权限。</PermissionNotice>);

    expect(screen.getByRole("status")).toHaveTextContent("当前账号没有审核权限。");
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

  test("renders app dialog with name, description, body, and actions", () => {
    renderWithMui(
      <AppDialog
        actions={<button type="button">保存</button>}
        description="用于确认本次操作。"
        onClose={vi.fn()}
        open
        title="共享弹窗"
      >
        <p>弹窗正文</p>
      </AppDialog>,
    );

    const dialog = screen.getByRole("dialog", { name: "共享弹窗" });
    expect(dialog).toHaveAccessibleDescription("用于确认本次操作。");
    expect(dialog).toHaveTextContent("弹窗正文");
    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
  });

  test("closes app dialog with escape unless disabled", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    const { rerender } = renderWithMui(<AppDialog onClose={onClose} open title="可关闭弹窗" />);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    onClose.mockClear();
    rerender(
      <MuiProviders>
        <AppDialog disableEscapeClose onClose={onClose} open title="不可按 Esc 关闭弹窗" />
      </MuiProviders>,
    );

    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  test("disables confirm dialog actions while loading", () => {
    renderWithMui(
      <ConfirmActionDialog
        destructive
        loading
        open
        title="确认删除"
        description="删除后不可恢复。"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "处理中..." })).toBeDisabled();
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
