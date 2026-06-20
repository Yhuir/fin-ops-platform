import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { GlobalOperationOverlayProvider, useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function OperationButton({
  onAction,
  blockOnError,
}: {
  onAction: (helpers: { setMessage: (message: string) => void }) => Promise<unknown>;
  blockOnError?: boolean;
}) {
  const { runOperation } = useGlobalOperationOverlay();
  return (
    <button
      type="button"
      onClick={() => {
        void runOperation({
          loadingMessage: "正在保存操作...",
          action: onAction,
          blockOnError,
        });
      }}
    >
      执行操作
    </button>
  );
}

describe("GlobalOperationOverlayProvider", () => {
  test("keeps the full-screen overlay visible until the operation promise settles", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    render(
      <GlobalOperationOverlayProvider>
        <OperationButton
          onAction={async ({ setMessage }) => {
            setMessage("正在等待真实同步...");
            return pending.promise;
          }}
        />
      </GlobalOperationOverlayProvider>,
    );

    await user.click(screen.getByRole("button", { name: "执行操作" }));

    expect(await screen.findByRole("dialog", { name: "全局操作进度" })).toBeInTheDocument();
    expect(screen.getByText("正在等待真实同步...")).toBeInTheDocument();

    pending.resolve("ok");

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "全局操作进度" })).not.toBeInTheDocument();
    });
  });

  test("keeps failures blocking until the user acknowledges the error", async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <GlobalOperationOverlayProvider>
        <OperationButton
          onAction={async () => {
            throw new Error("后端刷新失败");
          }}
        />
      </GlobalOperationOverlayProvider>,
    );

    await user.click(screen.getByRole("button", { name: "执行操作" }));

    const overlay = await screen.findByRole("dialog", { name: "全局操作进度" });
    expect(overlay).toHaveTextContent("后端刷新失败");
    expect(screen.getByRole("button", { name: "确定" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "确定" }));

    expect(screen.queryByRole("dialog", { name: "全局操作进度" })).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  test("can clear failures immediately when the caller owns local error feedback", async () => {
    const user = userEvent.setup();
    render(
      <GlobalOperationOverlayProvider>
        <OperationButton
          blockOnError={false}
          onAction={async () => {
            throw new Error("抽屉内联失败");
          }}
        />
      </GlobalOperationOverlayProvider>,
    );

    await user.click(screen.getByRole("button", { name: "执行操作" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "全局操作进度" })).not.toBeInTheDocument();
    });
    expect(screen.queryByText("抽屉内联失败")).not.toBeInTheDocument();
  });
});
