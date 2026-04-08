import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

describe("Finance operations shell", () => {
  test("loads the workbench as an all-time view and keeps the month picker scoped to tax offset", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华")).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "OA & 银行流水 & 进销项发票关联台",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
    expect(await screen.findByText("王青")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "税金抵扣" }));

    expect(
      screen.getByRole("heading", { name: "税金抵扣计划与试算" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "年月选择" })).toHaveTextContent("2026年3月");
    expect(fetchMock).toHaveBeenCalledWith("/api/workbench?month=all", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/tax-offset?month=2026-03", expect.any(Object));
  });

  test("hides the global workbench title block while a zone is expanded", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华")).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /放大 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(true);

    await user.click(screen.getByRole("button", { name: /恢复 未配对/ }));

    expect(document.body.classList.contains("workbench-focus-mode")).toBe(false);
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "年月选择" })).not.toBeInTheDocument();
  });

  test("keeps the shell header visible inside the OA iframe", async () => {
    window.history.pushState({}, "", "/?embedded=oa");
    installMockApiFetch();

    render(<App />);

    expect(await screen.findByText("赵华")).toBeInTheDocument();
    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("溯源办公系统")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关联台" })).toBeInTheDocument();
    expect(document.querySelector(".app-shell.embedded-shell")).not.toBeNull();
    expect(document.querySelector(".page-body.embedded")).not.toBeNull();
  });
});
