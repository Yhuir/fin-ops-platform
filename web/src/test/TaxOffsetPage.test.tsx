import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import App from "../app/App";
import { installMockApiFetch } from "./apiMock";
import { taxCertificationFixture } from "./taxCertificationFixture";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); window.sessionStorage.clear(); window.localStorage?.clear(); });
function open(options: Parameters<typeof installMockApiFetch>[0] = {}) {
  window.history.pushState({}, "", "/tax-offset"); const fetch = installMockApiFetch(options); render(<App />); return fetch;
}
function requestUrl(input: RequestInfo | URL) { return new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost"); }
test("shows a single canonical table and compact statistics with no plan controls", async () => {
  const fetch = open();
  expect(await screen.findByRole("heading", { name: "专票认证情况" })).toBeInTheDocument();
  expect(await screen.findByText("11203490")).toBeInTheDocument();
  expect(screen.getByRole("grid", { name: "专票认证明细" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /保存.*计划/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(screen.getByLabelText("已认证统计")).toHaveTextContent("0 张");
  expect(fetch.mock.calls.some(([input]) => /calculate|tax-offset\/plans/.test(String(input)))).toBe(false);
});
test("search and status use server filters and reset pagination", async () => {
  const user = userEvent.setup(); const fetch = open(); await screen.findByText("11203490");
  await user.type(screen.getByRole("searchbox", { name: "搜索专票" }), "材料");
  await user.click(within(document.querySelector(".tax-certification-page") as HTMLElement).getByRole("button", { name: "查询" }));
  await waitFor(() => expect(screen.queryByText("11203490")).not.toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: /认证状态/ }));
  await user.click(await screen.findByRole("option", { name: "未认证", exact: true }));
  await waitFor(() => expect(screen.queryByLabelText("已认证统计")).not.toBeInTheDocument());
  const urls = fetch.mock.calls.map(([input]) => requestUrl(input)).filter(url => url.pathname === "/api/tax-offset");
  expect(urls.at(-1)?.searchParams.get("search")).toBe("材料");
  expect(urls.at(-1)?.searchParams.get("status")).toBe("uncertified");
  expect(urls.at(-1)?.searchParams.get("page")).toBe("1");
});
test("sorts through the server and allows empty results without disabling import", async () => {
  const user = userEvent.setup(); const fetch = open(); await screen.findByText("11203490");
  await user.click(screen.getByRole("columnheader", { name: /勾选时间/ }));
  await waitFor(() => expect(fetch.mock.calls.some(([input]) => requestUrl(input).searchParams.get("sort_by") === "selection_time")).toBe(true));
  await user.type(screen.getByRole("searchbox"), "不存在"); await user.click(within(document.querySelector(".tax-certification-page") as HTMLElement).getByRole("button", { name: "查询" }));
  expect(await screen.findByText("暂无专票")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "导出专票清单", exact: true })).toBeDisabled();
  expect(within(document.querySelector(".tax-certification-page") as HTMLElement).getByRole("button", { name: "导入认证记录", exact: true })).toBeEnabled();
});
test("export uses API defaults, collapses extra columns, and closing keeps the parent search", async () => {
  const user = userEvent.setup(); open(); await screen.findByText("11203490");
  await user.type(screen.getByRole("searchbox"), "设备"); await user.click(within(document.querySelector(".tax-certification-page") as HTMLElement).getByRole("button", { name: "查询" }));
  await waitFor(() => expect(screen.queryByText("材料供应商")).not.toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: "导出专票清单", exact: true }));
  const drawer = await screen.findByRole("dialog", { name: "导出专票清单" });
  expect(within(drawer).getAllByRole("checkbox").filter(box => (box as HTMLInputElement).checked)).toHaveLength(8);
  expect(within(drawer).queryByRole("checkbox", { name: "勾选时间" })).not.toBeInTheDocument();
  await user.click(within(drawer).getByRole("button", { name: "更多字段" }));
  expect(within(drawer).getByRole("checkbox", { name: "勾选时间" })).toBeInTheDocument();
  await user.click(within(drawer).getByRole("button", { name: "关闭抽屉" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("searchbox")).toHaveValue("设备");
});
test("surfaces query failure and explicit retry restores data", async () => {
  let fail = true;
  open({ taxQueryHandler: ({ url }) => fail ? { status: 503, body: { message: "查询失败" } } : { body: taxCertificationFixture(url.searchParams) } });
  expect(await screen.findByRole("alert")).toHaveTextContent("查询失败");
  fail = false; fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByText("11203490")).toBeInTheDocument();
});
