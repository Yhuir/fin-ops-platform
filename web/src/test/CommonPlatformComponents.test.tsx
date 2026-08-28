import { readFileSync } from "node:fs";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { vi } from "vitest";

import AppDrawer from "../components/common/AppDrawer";
import AppDialog from "../components/common/AppDialog";
import ConfirmActionDialog from "../components/common/ConfirmActionDialog";
import FileDropzone from "../components/common/FileDropzone";
import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import PermissionNotice from "../components/common/PermissionNotice";
import StatePanel from "../components/common/StatePanel";

function renderWithProject(ui: React.ReactElement) {
  return render(ui);
}

describe("common platform components", () => {
  const appDrawerSource = readFileSync("src/components/common/AppDrawer.tsx", "utf8");
  const appStyles = readFileSync("src/app/styles.css", "utf8");
  const workbenchDetailDrawerSource = readFileSync("src/components/workbench/DetailDrawer.tsx", "utf8");

  test("renders state panels with accessible roles and loading affordances", () => {
    renderWithProject(
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
    renderWithProject(
      <StatePanel tone="loading" title="正在加载" compact>
        请稍候
      </StatePanel>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("正在加载");
    expect(screen.getByLabelText("加载中")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar", { name: "加载进度" })).not.toBeInTheDocument();
  });

  test("renders permission notice as a warning status", () => {
    renderWithProject(<PermissionNotice>当前账号没有审核权限。</PermissionNotice>);

    expect(screen.getByRole("status")).toHaveTextContent("当前账号没有审核权限。");
  });

  test("confirms and cancels actions through the shared dialog", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    renderWithProject(
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
    renderWithProject(
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

    const { rerender } = renderWithProject(<AppDialog onClose={onClose} open title="可关闭弹窗" />);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    onClose.mockClear();
    rerender(
      <AppDialog disableEscapeClose onClose={onClose} open title="不可按 Esc 关闭弹窗" />,
    );

    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  test("disables confirm dialog actions while loading", () => {
    renderWithProject(
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

  test("renders app drawer as a right side dialog with body and footer", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    renderWithProject(
      <AppDrawer
        footer={<button type="button">保存设置</button>}
        onClose={onClose}
        open
        title="规则详情"
      >
        <p>抽屉正文</p>
      </AppDrawer>,
    );

    const drawer = screen.getByRole("dialog", { name: "规则详情" });
    expect(drawer).toHaveTextContent("抽屉正文");
    expect(screen.getByRole("button", { name: "保存设置" })).toBeInTheDocument();
    expect(drawer.closest("[data-placement='right']")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭抽屉" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("can expose drawer busy state and disable the close button", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    renderWithProject(
      <AppDrawer
        ariaBusy
        closeDisabled
        closeLabel="关闭处理抽屉"
        onClose={onClose}
        open
        title="处理抽屉"
      >
        <p>正在处理</p>
      </AppDrawer>,
    );

    const drawer = screen.getByRole("dialog", { name: "处理抽屉" });
    expect(drawer).toHaveAttribute("aria-busy", "true");
    const closeButton = screen.getByRole("button", { name: "关闭处理抽屉" });
    expect(closeButton).toBeDisabled();

    await user.click(closeButton);
    expect(onClose).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    expect(appDrawerSource).toContain("isDismissable={!closeDisabled}");
    expect(appDrawerSource).toContain("isKeyboardDismissDisabled={closeDisabled}");
  });

  test("retains the last open modal content throughout its exit", async () => {
    let finishAnimation!: () => void;
    const animationFinished = new Promise<void>((resolve) => {
      finishAnimation = resolve;
    });
    const originalGetAnimations = HTMLElement.prototype.getAnimations;
    vi.stubGlobal("CSSTransition", class {});
    Object.defineProperty(HTMLElement.prototype, "getAnimations", {
      configurable: true,
      value: () => [{ finished: animationFinished }],
    });

    try {
      const { rerender } = renderWithProject(
        <AppDrawer onClose={vi.fn()} open title="OA详情">
          <p>原 OA 正文</p>
        </AppDrawer>,
      );

      rerender(
        <AppDrawer onClose={vi.fn()} open={false} title="详情">
          <p>空正文</p>
        </AppDrawer>,
      );

      const exitingDialog = screen.getByRole("dialog", { name: "OA详情" });
      expect(exitingDialog).toHaveTextContent("原 OA 正文");
      expect(exitingDialog).not.toHaveTextContent("空正文");
      await waitFor(() => {
        expect(exitingDialog.closest(".finance-drawer__content")).toHaveAttribute("data-exiting", "true");
      });

      await act(async () => finishAnimation());
      await waitFor(() => expect(screen.queryByRole("dialog", { name: "OA详情" })).not.toBeInTheDocument());
    } finally {
      if (originalGetAnimations) {
        Object.defineProperty(HTMLElement.prototype, "getAnimations", {
          configurable: true,
          value: originalGetAnimations,
        });
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "getAnimations");
      }
    }
  });

  test("keeps persistent app drawer mounted for its exit motion", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame"] });
    const onClose = vi.fn();

    try {
      const { rerender } = renderWithProject(
        <AppDrawer modal={false} onClose={onClose} open title="非模态抽屉">
          <p>持久抽屉正文</p>
        </AppDrawer>,
      );

      expect(screen.getByText("持久抽屉正文")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(16);
      });
      expect(screen.getByText("持久抽屉正文").closest(".finance-drawer__content")).toHaveAttribute("data-entering", "true");

      rerender(
        <AppDrawer modal={false} onClose={onClose} open={false} title="非模态抽屉">
          <p>持久抽屉正文</p>
        </AppDrawer>,
      );

      const exitingDrawer = screen.getByText("持久抽屉正文").closest(".finance-drawer__content");
      expect(exitingDrawer).toHaveAttribute("data-exiting", "true");
      expect(appDrawerSource).toContain("persistentDrawerExitMs");

      act(() => {
        vi.advanceTimersByTime(180);
      });

      expect(screen.queryByText("持久抽屉正文")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  test("cancels a pending persistent exit when the drawer reopens", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame"] });
    const onClose = vi.fn();

    try {
      const { rerender } = renderWithProject(
        <AppDrawer modal={false} onClose={onClose} open title="非模态抽屉">
          <p>快速切换正文</p>
        </AppDrawer>,
      );
      act(() => {
        vi.advanceTimersByTime(16);
      });

      rerender(
        <AppDrawer modal={false} onClose={onClose} open={false} title="非模态抽屉">
          <p>快速切换正文</p>
        </AppDrawer>,
      );
      expect(screen.getByText("快速切换正文").closest(".finance-drawer__content")).toHaveAttribute("data-exiting", "true");

      rerender(
        <AppDrawer modal={false} onClose={onClose} open title="非模态抽屉">
          <p>快速切换正文</p>
        </AppDrawer>,
      );
      act(() => {
        vi.advanceTimersByTime(16);
      });

      expect(screen.getByText("快速切换正文").closest(".finance-drawer__content")).not.toHaveAttribute("data-exiting");
    } finally {
      vi.useRealTimers();
    }
  });

  test("makes persistent exit inert and restores focus across a rapid reopen", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame"] });
    const inertDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "inert");
    if (!inertDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "inert", {
        configurable: true,
        get() {
          return this.hasAttribute("inert");
        },
        set(value: boolean) {
          this.toggleAttribute("inert", value);
        },
      });
    }

    try {
      const { rerender } = renderWithProject(
        <>
          <button type="button">打开抽屉</button>
          <AppDrawer modal={false} onClose={vi.fn()} open={false} title="持久抽屉">
            <button type="button">抽屉操作</button>
          </AppDrawer>
        </>,
      );
      const opener = screen.getByRole("button", { name: "打开抽屉" });
      opener.focus();

      rerender(
        <>
          <button type="button">打开抽屉</button>
          <AppDrawer modal={false} onClose={vi.fn()} open title="持久抽屉">
            <button type="button">抽屉操作</button>
          </AppDrawer>
        </>,
      );
      act(() => vi.advanceTimersByTime(16));
      screen.getByRole("button", { name: "抽屉操作" }).focus();

      rerender(
        <>
          <button type="button">打开抽屉</button>
          <AppDrawer modal={false} onClose={vi.fn()} open={false} title="持久抽屉">
            <button type="button">抽屉操作</button>
          </AppDrawer>
        </>,
      );
      const exitingDrawer = screen.getByText("持久抽屉").closest(".finance-drawer__content") as HTMLElement & { inert: boolean };
      expect(exitingDrawer.inert).toBe(true);
      expect(document.activeElement).toBe(opener);

      rerender(
        <>
          <button type="button">打开抽屉</button>
          <AppDrawer modal={false} onClose={vi.fn()} open title="持久抽屉">
            <button type="button">抽屉操作</button>
          </AppDrawer>
        </>,
      );
      act(() => vi.advanceTimersByTime(16));
      expect(screen.getByText("持久抽屉").closest(".finance-drawer__content")).not.toHaveAttribute("data-exiting");

      rerender(
        <>
          <button type="button">打开抽屉</button>
          <AppDrawer modal={false} onClose={vi.fn()} open={false} title="持久抽屉">
            <button type="button">抽屉操作</button>
          </AppDrawer>
        </>,
      );
      act(() => vi.advanceTimersByTime(180));
      expect(screen.queryByText("持久抽屉")).not.toBeInTheDocument();
      expect(document.activeElement).toBe(opener);
    } finally {
      if (inertDescriptor) {
        Object.defineProperty(HTMLElement.prototype, "inert", inertDescriptor);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "inert");
      }
      vi.useRealTimers();
    }
  });

  test("uses HeroUI right translate motion without the legacy child transform animation", () => {
    expect(appStyles).toMatch(/\.finance-drawer\s*\{[^}]*display:\s*flex/s);
    expect(appStyles).toMatch(/\.finance-drawer\s*\{[^}]*flex-direction:\s*column/s);
    expect(appStyles).toMatch(/\.finance-drawer\s*\{[^}]*max-height:\s*100vh/s);
    expect(appStyles).toMatch(/\.finance-drawer__body\s*\{[^}]*overflow:\s*auto/s);
    expect(appStyles).toMatch(/\.finance-drawer__header\s*\{[^}]*flex-direction:\s*row/s);
    expect(appStyles).toMatch(/--finance-drawer-enter-duration:\s*240ms;/);
    expect(appStyles).toMatch(/--finance-drawer-exit-duration:\s*180ms;/);
    expect(appStyles).toMatch(/\.finance-drawer\s*\{[^}]*transition-property:\s*translate/s);
    expect(appStyles).toMatch(/\.finance-drawer__content\[data-exiting\] \.finance-drawer\s*\{[^}]*transition-duration:\s*var\(--finance-drawer-exit-duration\)/s);
    expect(appStyles).toMatch(/\.finance-drawer__content--persistent\s*\{[^}]*transition-property:\s*translate/s);
    expect(appStyles).toMatch(/\.finance-drawer__content--persistent\[data-entering\]\s*\{[^}]*translate:\s*0/s);
    expect(appStyles).toMatch(/\.finance-drawer__content--persistent\[data-exiting\]\s*\{[^}]*translate:\s*100%\s+0/s);
    expect(appStyles).not.toContain("@keyframes finance-drawer-slide-in");
    expect(appStyles).not.toContain("@keyframes finance-drawer-slide-out");
    expect(appStyles).not.toContain("translate3d(28px, 0, 0)");
    expect(appStyles).not.toContain("translate3d(22px, 0, 0)");
    expect(appStyles).not.toMatch(/\.finance-drawer\s*\{[^}]*will-change/s);
    expect(appStyles).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(appStyles).toMatch(/\[data-reduce-motion="true"\] \.finance-drawer/);
    expect(workbenchDetailDrawerSource).not.toContain('window.addEventListener("keydown"');
  });

  test("renders optional drawer header actions without changing the title or close control", () => {
    renderWithProject(
      <AppDrawer
        headerActions={<button type="button">切换视图</button>}
        onClose={vi.fn()}
        open
        title="成本人工分配"
      >
        抽屉内容
      </AppDrawer>,
    );

    expect(screen.getByRole("heading", { name: "成本人工分配" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "切换视图" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭抽屉" })).toBeInTheDocument();
  });

  test("renders page scaffold heading, description, actions, and children", () => {
    renderWithProject(
      <PageScaffold
        actions={<button type="button">新增</button>}
        description="页面说明"
        title="页面标题"
      >
        <section>页面内容</section>
      </PageScaffold>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "页面标题" })).toBeInTheDocument();
    expect(screen.getByText("页面说明")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新增" })).toBeInTheDocument();
    expect(screen.getByText("页面内容")).toBeInTheDocument();
  });

  test("renders page toolbar groups and children fallback", () => {
    const { rerender } = renderWithProject(
      <PageToolbar left={<button type="button">筛选</button>} right={<button type="button">导出</button>} />,
    );

    expect(screen.getByRole("button", { name: "筛选" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出" })).toBeInTheDocument();

    rerender(
      <PageToolbar>
        <button type="button">刷新</button>
      </PageToolbar>,
    );

    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
  });

  test("emits dropped files from the shared dropzone", () => {
    const onFiles = vi.fn();
    const file = new File(["a,b"], "bank.csv", { type: "text/csv" });

    renderWithProject(<FileDropzone label="上传银行流水" onFiles={onFiles} />);

    fireEvent.drop(screen.getByRole("button", { name: "上传银行流水" }), {
      dataTransfer: {
        files: [file],
      },
    });

    expect(onFiles).toHaveBeenCalledWith([file]);
  });
});
