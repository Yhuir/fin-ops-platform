import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../app/App";
import { installMockApiFetch } from "./apiMock";

describe("OperationHistoryPage", () => {
  test("only loads for an administrator and shows the durable event detail", async () => {
    window.history.pushState({}, "", "/operations/history");
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "权限管理员",
    });
    render(<App />);

    expect(await screen.findByRole("heading", { name: "操作历史" })).toBeInTheDocument();
    const table = await screen.findByRole("grid", { name: "操作历史" });
    expect(table).toHaveTextContent("权限管理员");
    expect(table).toHaveTextContent("YNSYLP005");
    expect(table).toHaveTextContent("关联台");
    expect(table).toHaveTextContent("关联关系");
    expect(table).not.toHaveTextContent("workbench_relation");
    expect(table).toHaveTextContent("确认关联");

    await userEvent.click(within(table).getByRole("button", { name: "查看确认关联详情" }));
    const drawer = await screen.findByRole("dialog", { name: "操作详情" });
    expect(drawer).toHaveTextContent("关联台");
    expect(drawer).not.toHaveTextContent("/api/workbench/actions/confirm-link");
    expect(drawer).toHaveTextContent("将所选 OA、流水和发票确认关联。");
    expect(drawer).toHaveTextContent("1 条银行流水");
    expect(drawer).toHaveTextContent("未配对");
    expect(drawer).toHaveTextContent("已配对");
    expect(drawer).not.toHaveTextContent("request:request-1");
    expect(drawer).not.toHaveTextContent("request-1");
    expect(drawer).not.toHaveTextContent("event-1");
    expect(drawer).not.toHaveTextContent("internal-relation-1");
    expect(drawer).not.toHaveTextContent("trace-1");
    expect(drawer).not.toHaveTextContent("操作标识");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/history/request%3Arequest-1"))).toBe(true);
    });
  });

  test("redirects a non-admin away before loading audit data", async () => {
    window.history.pushState({}, "", "/operations/history");
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "full_access",
      sessionUsername: "YNSYLP006",
    });
    render(<App />);

    expect(await screen.findByRole("heading", { name: "关联台" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "操作历史" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/operations/history"))).toBe(false);
  });

  test("shows the exact relation, invoice fields, and authenticated file preview", async () => {
    window.history.pushState({}, "", "/operations/history");
    const baseFetch = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "权限管理员",
    });
    const createObjectUrl = vi.fn(() => "blob:operation-proof");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    global.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === "/api/operations/history/request%3Arequest-1") {
        return Promise.resolve(new Response(JSON.stringify({
          operation: {
            operation_key: "request:request-1",
            actor_id: "005",
            actor_name: "权限管理员",
            actor_account: "YNSYLP005",
            page_key: "reconciliation-workbench",
            action_code: "workbench.oa_invoice.document_upload",
            action_label: "上传 OA 补充凭证",
            action_description: "上传不进入统一发票池的补充凭证并关联到指定 OA 子付款项。",
            object_type: "oa_supporting_document",
            object_label: "OA 补充凭证",
            started_at: "2026-08-19T01:00:00+08:00",
            completed_at: "2026-08-19T01:00:01+08:00",
            occurred_at: "2026-08-19T01:00:01+08:00",
            outcome: "success",
            detail: {
              schema_version: 1,
              target: {
                kind: "oa_expense_item_relation",
                title: "关联关系 CASE-1",
                fields: [
                  { label: "关联关系", value: "CASE-1" },
                  { label: "OA 子付款项", value: "oa-1:item:0" },
                ],
              },
              artifacts: [{
                artifact_key: "document-1",
                kind: "file",
                title: "voucher.png",
                media_type: "image/png",
                size_bytes: 2048,
                preview_url: "/api/workbench/oa-invoice-supplements/documents/document-1/content",
                availability: "available",
              }],
              records: [{
                record_key: "invoice-1",
                kind: "invoice",
                title: "26117000001052654674",
                fields: [
                  { label: "销方名称", value: "云南供应商有限公司" },
                  { label: "购方名称", value: "云南溯源科技有限公司" },
                ],
              }],
              changes: [{ label: "补充凭证", before: "未上传", after: "已关联 1 个文件" }],
              failure: null,
              legacy_evidence_missing: false,
            },
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.pathname === "/api/workbench/oa-invoice-supplements/documents/document-1/content") {
        return Promise.resolve(new Response(new Blob(["png"]), { status: 200, headers: { "Content-Type": "image/png" } }));
      }
      return baseFetch(input, init);
    });

    render(<App />);
    const table = await screen.findByRole("grid", { name: "操作历史" });
    await userEvent.click(within(table).getByRole("button", { name: "查看确认关联详情" }));
    const drawer = await screen.findByRole("dialog", { name: "操作详情" });

    expect(await within(drawer).findByText("关联关系 CASE-1")).toBeInTheDocument();
    expect(drawer).toHaveTextContent("voucher.png");
    expect(drawer).toHaveTextContent("云南供应商有限公司");
    expect(drawer).toHaveTextContent("云南溯源科技有限公司");
    expect(await within(drawer).findByRole("img", { name: "voucher.png 预览" })).toHaveAttribute("src", "blob:operation-proof");
    expect(createObjectUrl).toHaveBeenCalledTimes(1);

    await userEvent.click(within(drawer).getByRole("button", { name: "关闭抽屉" }));
    await waitFor(() => expect(revokeObjectUrl).toHaveBeenCalledWith("blob:operation-proof"));
  });

  test("keeps the newest filter result when an older request finishes later", async () => {
    window.history.pushState({}, "", "/operations/history");
    const baseFetch = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      sessionDisplayName: "权限管理员",
    });
    let resolveOlder: ((response: Response) => void) | undefined;
    const olderResponse = new Promise<Response>((resolve) => {
      resolveOlder = resolve;
    });
    const rowResponse = (label: string) => new Response(JSON.stringify({
      rows: [{
        operation_key: `request:${label}`,
        actor_id: "005",
        actor_name: "权限管理员",
        actor_account: "YNSYLP005",
        page_key: "reconciliation-workbench",
        action_code: "workbench.operation",
        action_label: label,
        action_description: `${label}的用户可读说明`,
        object_type: "reconciliation_case",
        object_label: "关联关系",
        started_at: "2026-08-09T12:00:00+08:00",
        occurred_at: "2026-08-09T12:00:00+08:00",
        outcome: "success",
      }],
      next_cursor: null,
      limit: 50,
    }), { status: 200, headers: { "Content-Type": "application/json" } });
    global.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === "/api/operations/history" && url.searchParams.get("search") === "较早请求") {
        return olderResponse;
      }
      if (url.pathname === "/api/operations/history" && url.searchParams.get("search") === "最新请求") {
        return Promise.resolve(rowResponse("最新结果"));
      }
      return baseFetch(input, init);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "操作历史" })).toBeInTheDocument();
    const search = screen.getByRole("searchbox", { name: "搜索操作历史" });
    const query = screen.getByRole("button", { name: "查询" });
    await userEvent.clear(search);
    await userEvent.type(search, "较早请求");
    await userEvent.click(query);
    await userEvent.clear(search);
    await userEvent.type(search, "最新请求");
    await userEvent.click(query);

    const table = await screen.findByRole("grid", { name: "操作历史" });
    expect(await within(table).findByText("最新结果")).toBeInTheDocument();
    await act(async () => {
      resolveOlder?.(rowResponse("过期结果"));
      await olderResponse;
    });
    expect(table).toHaveTextContent("最新结果");
    expect(table).not.toHaveTextContent("过期结果");
  });
});
