import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import AppDrawer from "../components/common/AppDrawer";

describe("AppDrawer explicit dismissal", () => {
  it("keeps edits after outside pointer interaction and Escape, and closes only from X", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<AppDrawer open title="编辑" onClose={onClose}><input aria-label="内容" defaultValue="未保存" /></AppDrawer>);
    const input = screen.getByRole("textbox", { name: "内容" });
    await user.type(input, "修改");
    const backdrop = document.querySelector(".finance-drawer__backdrop")!;
    fireEvent.pointerDown(backdrop);
    fireEvent.pointerUp(backdrop);
    fireEvent.click(backdrop);
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    expect(input).toHaveValue("未保存修改");
    await user.click(screen.getByRole("button", { name: "关闭抽屉" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("allows keyboard activation of X", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<AppDrawer open title="详情" onClose={onClose}>详情内容</AppDrawer>);
    screen.getByRole("button", { name: "关闭抽屉" }).focus();
    await user.keyboard("{Enter}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("preserves the caller's close protection", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<AppDrawer open closeDisabled title="提交中" onClose={onClose}>正在保存</AppDrawer>);
    await user.click(screen.getByRole("button", { name: "关闭抽屉" }));
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("replaces a completed form and footer without closing or permitting a duplicate submit", async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    const close = vi.fn();
    function Editor() {
      const [completed, setCompleted] = useState(false);
      return <AppDrawer open title="录入" onClose={close} completion={completed ? "已保存" : undefined}
        footer={<button onClick={() => { save(); setCompleted(true); }}>保存</button>}>
        <input aria-label="金额" />
      </AppDrawer>;
    }
    render(<Editor />);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(screen.getByRole("status")).toHaveTextContent("已保存");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    expect(save).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "关闭抽屉" }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("does not dismiss a parent drawer when the nested drawer requests closing", async () => {
    const user = userEvent.setup();
    const parentClose = vi.fn();
    const childClose = vi.fn();
    function Nested() {
      const [open, setOpen] = useState(false);
      return <AppDrawer open title="父层" onClose={parentClose}>
        <button onClick={() => setOpen(true)}>打开子层</button>
        <AppDrawer open={open} title="子层" onClose={childClose}>子层内容</AppDrawer>
      </AppDrawer>;
    }
    render(<Nested />);
    await user.click(screen.getByRole("button", { name: "打开子层" }));
    await user.keyboard("{Escape}");
    await user.click(within(screen.getByRole("dialog", { name: "子层" })).getByRole("button", { name: "关闭抽屉" }));
    expect(childClose).toHaveBeenCalledTimes(1);
    expect(parentClose).not.toHaveBeenCalled();
  });

  it("keeps the non-modal workflow while background controls are used", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const backgroundAction = vi.fn();
    render(<><button onClick={backgroundAction}>背景选票</button>
      <AppDrawer modal={false} open title="反提 OA" onClose={onClose}>工作流</AppDrawer></>);
    await user.click(screen.getByRole("button", { name: "背景选票" }));
    await user.keyboard("{Escape}");
    expect(backgroundAction).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "关闭抽屉" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
