import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

describe("Settings page", () => {
  test("renders as a tree-and-panel page without an extra page header title", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "关联台设置" })).not.toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    expect(within(tree).getByRole("treeitem", { name: /项目状态/ })).toHaveAttribute("aria-selected", "true");

    expect(screen.getByRole("region", { name: "项目状态管理" })).toBeInTheDocument();
  });

  test("switches the content panel when selecting another settings section", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /银行账户/ }));

    expect(screen.getByRole("region", { name: "银行账户映射" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "项目状态管理" })).not.toBeInTheDocument();
  });

  test("opens the workbench search modal in one click from settings", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByRole("button", { name: "搜索" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "搜索" }));

    expect(await screen.findByRole("dialog", { name: "关联台搜索" })).toBeInTheDocument();
  });
});
