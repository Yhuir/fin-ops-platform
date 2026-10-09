import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import InputInvoiceUsageDetailDrawer, {
  type InputInvoiceUsageDetailPayload,
  type InputInvoiceUsageDetailTarget,
} from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import InputInvoiceUsageFilterMenu from "../components/inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import OaReverseWorkspaceDrawer, {
  type OaReversePreviewPayload,
} from "../components/inputInvoiceUsage/OaReverseWorkspaceDrawer";
import PaymentStatusRulesDrawer, {
  type PaymentStatusRulesPayload,
} from "../components/inputInvoiceUsage/PaymentStatusRulesDrawer";
import {
  createInputInvoiceUsageOaReverseDraftFromSelection,
  fetchInputInvoiceUsageOaDetail,
  fetchInputInvoiceUsageRowRelationDetail,
  fetchInputInvoiceUsageOaReverseStagedDrafts,
  fetchInputInvoiceUsageOaReverseSubmittedHistory,
  previewInputInvoiceUsageOaReverse,
} from "../features/inputInvoiceUsage/api";

const inputInvoiceUsageWorkflowSourceFiles = [
  "src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx",
  "src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx",
  "src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx",
] as const;

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Input invoice usage workflow primitive targets", () => {
  test("targets project menu and right drawer primitives without MUI overlay surfaces", () => {
    const forbiddenMuiImports = inputInvoiceUsageWorkflowSourceFiles.flatMap((path) => {
      const source = readWebSource(path);
      const hasMuiImport = /from ["']@mui\/|import\s+[^;]*@mui\//.test(source);
      return hasMuiImport ? [path] : [];
    });
    const forbiddenMuiSelectors = inputInvoiceUsageWorkflowSourceFiles.flatMap((path) => {
      const source = readWebSource(path);
      const hasMuiSelector = /\.Mui[A-Z][A-Za-z-]*/.test(source);
      return hasMuiSelector ? [path] : [];
    });
    const sourceByPath = Object.fromEntries(inputInvoiceUsageWorkflowSourceFiles.map((path) => [path, readWebSource(path)]));
    const missingPrimitiveTargets = [
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("Checkbox.Control")
        && sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemradio\"")
        ? null
        : "InputInvoiceUsageFilterMenu.tsx should use HeroUI Checkbox and preserve radio menu semantics",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageDetailDrawer.tsx should use AppDrawer",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx"].includes("FilteredExportDrawer") ? null : "InputInvoiceUsageExportDrawer.tsx should use AppDrawer",
      sourceByPath["src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx"].includes("AppDrawer") ? null : "PaymentStatusRulesDrawer.tsx should use AppDrawer",
      sourceByPath["src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx"].includes("AppDrawer") ? null : "OaReverseWorkspaceDrawer.tsx should use AppDrawer",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      missingPrimitiveTargets: [],
    });
  });
});

describe("InputInvoiceUsageFilterMenu", () => {
  test("supports API-provided multi-select options, select all, clear, and both sort directions", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    const onClear = vi.fn();
    const onSort = vi.fn();

    render(
      <InputInvoiceUsageFilterMenu
        fieldConfig={{ field: "payment_status", label: "支付状态", mode: "enum_multi" }}
        currentFilter={{ field: "payment_status", operator: "in", values: ["pending"] }}
        options={[
          { value: "pending", label: "待处理", count: 8 },
          { value: "cash", label: "现金往来", count: 2 },
        ]}
        onApply={onApply}
        onClear={onClear}
        onSort={onSort}
      />,
    );

    await user.click(screen.getByRole("button", { name: "筛选 支付状态" }));
    const menu = await screen.findByRole("menu", { name: "支付状态筛选与排序" });

    expect(within(menu).getByRole("checkbox", { name: "待处理 8" })).toBeChecked();
    expect(within(menu).getByRole("checkbox", { name: "现金往来 2" })).not.toBeChecked();
    expect(within(menu).queryByText("已付款")).not.toBeInTheDocument();

    await user.click(within(menu).getByRole("menuitem", { name: "全选" }));
    expect(onApply).toHaveBeenLastCalledWith({ field: "payment_status", operator: "in", values: ["pending", "cash"] });

    await user.click(within(menu).getByRole("menuitem", { name: "清空" }));
    expect(onClear).toHaveBeenLastCalledWith("payment_status");

    await user.click(within(menu).getByRole("menuitem", { name: "升序排序" }));
    expect(onSort).toHaveBeenLastCalledWith("asc");

    await user.click(within(menu).getByRole("menuitem", { name: "降序排序" }));
    expect(onSort).toHaveBeenLastCalledWith("desc");
  });

  test("uses radio-style selection for single-select fields", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();

    render(
      <InputInvoiceUsageFilterMenu
        fieldConfig={{ field: "oa_application_type", label: "报销/支付", mode: "enum_single" }}
        currentFilter={{ field: "oa_application_type", operator: "equals", value: "reimbursement" }}
        options={[
          { value: "reimbursement", label: "报销" },
          { value: "payment", label: "支付" },
        ]}
        onApply={onApply}
        onClear={() => undefined}
        onSort={() => undefined}
      />,
    );

    await user.click(screen.getByRole("button", { name: "筛选 报销/支付" }));
    const menu = await screen.findByRole("menu", { name: "报销/支付筛选与排序" });
    await user.click(within(menu).getByRole("menuitemradio", { name: "支付" }));

    expect(onApply).toHaveBeenLastCalledWith({ field: "oa_application_type", operator: "equals", value: "payment" });
  });
});

describe("InputInvoiceUsageDetailDrawer", () => {
  test("switches source targets without retaining previous detail on loading or error", async () => {
    const first: InputInvoiceUsageDetailTarget = { kind: "invoice", id: "first" };
    const second: InputInvoiceUsageDetailTarget = { kind: "invoice", id: "second" };
    let rejectSecond!: (error: Error) => void;
    const loadDetail = vi.fn()
      .mockResolvedValueOnce({ sections: [{ title: "基本信息", fields: [{ label: "备注", value: "第一张来源" }] }] })
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectSecond = reject; }));
    const { rerender } = render(<InputInvoiceUsageDetailDrawer open target={first} loadDetail={loadDetail} onClose={() => undefined} />);
    expect(await screen.findByText("第一张来源")).toBeInTheDocument();
    rerender(<InputInvoiceUsageDetailDrawer open target={second} loadDetail={loadDetail} onClose={() => undefined} />);
    expect(screen.queryByText("第一张来源")).not.toBeInTheDocument();
    expect(screen.getByLabelText("正在加载详情")).toBeInTheDocument();
    rejectSecond(new Error("第二张来源不可用"));
    expect(await screen.findByText("第二张来源不可用")).toBeInTheDocument();
    expect(screen.queryByText("第一张来源")).not.toBeInTheDocument();
  });

  test("lazy-loads full invoice detail after opening and shows a loading state", async () => {
    const target: InputInvoiceUsageDetailTarget = { kind: "invoice", id: "inv-001", rowId: "row-001" };
    const loadDetail = vi.fn<[], Promise<InputInvoiceUsageDetailPayload>>(() => new Promise(() => undefined));

    render(
      <InputInvoiceUsageDetailDrawer
        open
        target={target}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );

    expect(within(screen.getByLabelText("正在加载详情")).getByRole("status")).toBeInTheDocument();
    await waitFor(() => expect(loadDetail).toHaveBeenCalledWith(target, expect.any(AbortSignal)));
  });

  test("supports invoice, bank, OA and relation-list detail payloads without faking unavailable OA detail", async () => {
    const detailByKind: Record<InputInvoiceUsageDetailTarget["kind"], InputInvoiceUsageDetailPayload> = {
      invoice: {
        title: "发票详情",
        subtitle: "inv-001",
        sections: [{ title: "发票主信息", fields: [{ label: "发票号码", value: "INV-2026-001" }] }],
      },
      bank: {
        title: "银行流水详情",
        subtitle: "bank-001",
        sections: [{ title: "流水主信息", fields: [{ label: "对方户名", value: "上海供应商" }] }],
      },
      oa: {
        title: "OA详情",
        subtitle: "oa-001",
        detailAvailable: false,
        unavailableReason: "后端未提供 OA 完整详情",
        sections: [],
      },
      relationList: {
        title: "关联明细",
        subtitle: "row-001",
        sections: [
          { title: "OA 1", fields: [{ label: "申请人", value: "张三" }] },
          { title: "OA 2", fields: [{ label: "申请人", value: "李四" }] },
        ],
      },
    };
    const loadDetail = vi.fn((target: InputInvoiceUsageDetailTarget) => Promise.resolve(detailByKind[target.kind]));
    const { rerender } = render(
      <InputInvoiceUsageDetailDrawer
        open
        target={{ kind: "invoice", id: "inv-001" }}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText("INV-2026-001")).toBeInTheDocument();

    rerender(
      <InputInvoiceUsageDetailDrawer
        open
        target={{ kind: "bank", id: "bank-001" }}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );
    expect(await screen.findByText("上海供应商")).toBeInTheDocument();

    rerender(
      <InputInvoiceUsageDetailDrawer
        open
        target={{ kind: "oa", id: "oa-001" }}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );
    expect(await screen.findByText("详情暂不可用")).toBeInTheDocument();
    expect(screen.getByText("后端未提供 OA 完整详情")).toBeInTheDocument();
    expect(screen.queryByText("模拟 OA 明细")).not.toBeInTheDocument();

    rerender(
      <InputInvoiceUsageDetailDrawer
        open
        target={{ kind: "relationList", id: "row-001" }}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );
    expect(await screen.findByRole("heading", { name: "OA 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "OA 2" })).toBeInTheDocument();
    expect(await screen.findByText("张三")).toBeInTheDocument();
    expect(await screen.findByText("李四")).toBeInTheDocument();
    expect(screen.queryByText("关系数量")).not.toBeInTheDocument();
  });

  test("hides raw App fields and keeps the title beside the close control", async () => {
    const loadDetail = vi.fn(() => Promise.resolve<InputInvoiceUsageDetailPayload>({
      title: "OA详情",
      sections: [
        {
          title: "OA主信息",
          fields: [
            { label: "申请人", value: "樊租芳" },
            { label: "金额", value: "362590.00" },
            { label: "发票行 ID", value: "row-internal-001" },
            { label: "workflow_request_id", value: "2025" },
          ],
        },
        {
          title: "OA原始字段",
          fields: [
            { label: "付款方式", value: "Bank_transfer" },
            { label: "票据类型", value: "VAT_ordinary_invoice" },
            { label: "Mongo文档ID", value: "6a13b7953bb8164165d8c631" },
          ],
        },
      ],
    }));

    render(
      <InputInvoiceUsageDetailDrawer
        open
        target={{ kind: "oa", id: "oa-internal-row-id" }}
        loadDetail={loadDetail}
        onClose={() => undefined}
      />,
    );

    const title = await screen.findByText("OA详情");
    const header = title.closest(".finance-drawer__header");
    expect(header).toContainElement(screen.getByRole("button", { name: "关闭详情抽屉" }));

    expect(await screen.findByText("申请人")).toBeInTheDocument();
    expect(screen.getByText("樊租芳")).toBeInTheDocument();
    expect(screen.queryByText("发票行 ID")).not.toBeInTheDocument();
    expect(screen.queryByText("workflow_request_id")).not.toBeInTheDocument();
    expect(screen.queryByText("OA原始字段")).not.toBeInTheDocument();
    expect(screen.queryByText("Bank_transfer")).not.toBeInTheDocument();
    expect(screen.queryByText("VAT_ordinary_invoice")).not.toBeInTheDocument();
    expect(screen.queryByText("oa-internal-row-id")).not.toBeInTheDocument();
  });
});

describe("Input invoice usage workflow drawers", () => {
  test("OA detail mapper uses source workflow status rather than business or relation status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      oaId: "oa-completed",
      detailAvailable: true,
      applicantName: "樊祖芳",
      workflowStatus: "completed",
      status: "unpaired",
      detailFields: { "流程状态": "in_progress" },
      sections: [{title: "单据信息", fields: [{label: "流程状态", value: "in_progress"}]}],
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })));

    const detail = await fetchInputInvoiceUsageOaDetail("oa-completed");

    expect(detail.sections[0].fields).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "流程状态", value: "in_progress" }),
    ]));
    expect(detail.sections[0].fields).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ value: "unpaired" }),
    ]));
    expect(detail.sections[0].fields).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ value: "completed" }),
    ]));
  });

  test("relation detail mapper renders the direct canonical relation response", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      expect(url.pathname).toBe("/api/input-invoice-usage/rows/row-refreshing/relation-details");
      expect(url.searchParams.get("kind")).toBe("oa");
      expect(url.searchParams.get("month")).toBe("2026-05");
      return new Response(JSON.stringify({
        row_id: "row-refreshing",
        kind: "oa",
        title: "OA关联明细",
        relationCount: 1,
        sections: [{ title: "OA 1", fields: [
          { label: "申请人", value: "樊祖芳" },
          { label: "金额", value: "100.00" },
          { label: "流程状态", value: "completed" },
        ] }],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    const detail = await fetchInputInvoiceUsageRowRelationDetail({
      kind: "relationList",
      id: "row-refreshing",
      rowId: "row-refreshing",
      relationKind: "oa",
      scopeKey: "2026-05",
    });

    expect(detail.title).toBe("OA详情");
    expect(detail.detailAvailable).toBe(true);
    expect(detail.sections).toHaveLength(1);
    expect(detail.sections[0].title).toBe("OA 1");
    expect(detail.sections[0].fields).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "申请人", value: "樊祖芳" }),
      expect.objectContaining({ label: "金额", value: "100.00" }),
      expect.objectContaining({ label: "流程状态", value: "completed" }),
    ]));
  });

  test("OA preview browsing sends its inherited scope, while selection sends precise IDs", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      const count = Object.hasOwn(body, "invoiceIds") ? body.invoiceIds.length : 385;
      return new Response(JSON.stringify({ invoiceCount: count, totalWithTax: "0", groups: [], pagination: { page: 1, pageSize: 50, total: count } }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    const all = await previewInputInvoiceUsageOaReverse({ selectedInvoiceIds: [], page: 1, pageSize: 50, keyword: "销方", month: "2026-09", invoiceDateFrom: "2026-09-01", invoiceDateTo: "2026-09-30", filters: [{ field: "seller_name", operator: "contains", value: "销方" }] });
    expect(all.invoiceCount).toBe(385);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).not.toHaveProperty("invoiceIds");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({ keyword: "销方", month: "2026-09", invoiceDateFrom: "2026-09-01", invoiceDateTo: "2026-09-30", filters: [{ field: "seller_name", operator: "contains", value: "销方" }] });
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).not.toHaveProperty("bankRelation");
    const selected = await previewInputInvoiceUsageOaReverse({ selectedInvoiceIds: ["inv-1", "inv-2"] });
    expect(selected.invoiceCount).toBe(2);
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({ invoiceIds: ["inv-1", "inv-2"] });
  });

  test("staged API preserves recovery capabilities and sends the requested batch limit", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [{ batchId: "failed-1", version: 3, status: "oa_draft_failed", invoiceIds: ["inv-1"], invoiceRows: [], draftRequestState: "unknown", canRelease: true, canConfirmSubmission: false, oaDetectionError: "OA 超时" }] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const payload = await fetchInputInvoiceUsageOaReverseStagedDrafts(100);
    expect(String(fetchMock.mock.calls[0][0])).toContain("staged-drafts?limit=100");
    expect(payload.items[0]).toMatchObject({ draftRequestState: "unknown", canRelease: true, canConfirmSubmission: false, oaDetectionError: "OA 超时" });
  });

  test("OA reverse API mapper uses one-step draft and submitted history contracts", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        if (url.pathname === "/api/input-invoice-usage/oa-reverse/preview") {
          return new Response(JSON.stringify({
            previewId: "oa_reverse_preview_backend",
            previewHash: "hash-backend",
            targetApplicantCode: "chen_xiuyun",
            targetApplicantName: "陈秀云",
            targetApplicants: [{ code: "chen_xiuyun", name: "陈秀云" }],
            invoiceCount: 1,
          totalWithTax: "88.00",
          invoiceRows: [{
            invoiceId: "inv-backend-1",
            invoiceNo: "INV-BACKEND-1",
            displayNo: "SD-BACKEND-1",
            sellerName: "后端供应商",
            invoiceDate: "2026-05-20",
            totalWithTax: "88.00",
            paymentStatus: { label: "未付" },
          }],
          groups: [{
            targetApplicantCode: "chen_xiuyun",
            targetApplicantName: "陈秀云",
            invoiceCount: 1,
            totalWithTax: "88.00",
            candidateInvoiceIds: ["inv-backend-1"],
            invoiceRows: [{
              invoiceId: "inv-backend-1",
              invoiceNo: "INV-BACKEND-1",
              displayNo: "SD-BACKEND-1",
              sellerName: "后端供应商",
              invoiceDate: "2026-05-20",
              totalWithTax: "88.00",
              paymentStatus: { label: "未付" },
            }],
            rejectedInvoices: [{
              invoiceId: "inv-linked-backend",
              invoiceNo: "INV-LINKED-BACKEND",
              sellerName: "已关联后端供应商",
              invoiceDate: "2026-05-21",
              totalWithTax: "66.00",
              paymentStatus: { label: "已关联 OA" },
              oaRelationStatus: "linked",
              reasonCode: "already_has_active_oa",
              reason: "发票已有 active OA 关系",
            }],
          }],
          rejectedInvoices: [{
            invoiceId: "inv-linked-backend",
            invoiceNo: "INV-LINKED-BACKEND",
            sellerName: "已关联后端供应商",
            invoiceDate: "2026-05-21",
            totalWithTax: "66.00",
            paymentStatus: { label: "已关联 OA" },
            oaRelationStatus: "linked",
            reasonCode: "already_has_active_oa",
            reason: "发票已有 active OA 关系",
          }],
          canCreateDraft: true,
          nextAction: "create_batch",
          permissions: { canCreateDraft: true },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/input-invoice-usage/oa-reverse/oa-draft") {
        return new Response(JSON.stringify({
          batchId: "batch-backend",
          version: 1,
          status: "oa_draft_created",
          invoiceIds: ["inv-backend-1"],
          selectedInvoiceIds: ["inv-backend-1"],
          targetApplicantCode: "chen_xiuyun",
          targetApplicantName: "陈秀云",
          totalWithTax: "88.00",
          oaDraftId: "oa-draft-backend",
          oaDraftUrl: "https://oa.example.test/draft/backend",
          invoiceRows: [{
            invoiceId: "inv-backend-1",
            invoiceNo: "INV-BACKEND-1",
            displayNo: "SD-BACKEND-1",
            sellerName: "后端供应商",
            invoiceDate: "2026-05-20",
            totalWithTax: "88.00",
            paymentStatus: { label: "未付" },
          }],
          previewSummary: { invoiceCount: 1, totalWithTax: "88.00" },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/input-invoice-usage/oa-reverse/submitted-history") {
        return new Response(JSON.stringify({
          items: [{
            targetApplicantName: "陈秀云",
            submittedAt: "2026-06-10T10:00:00+08:00",
            totalWithTax: "88.00",
            invoiceCount: 1,
            invoices: [{
              invoiceNo: "INV-BACKEND-1",
              invoiceDate: "2026-05-20",
              sellerName: "后端供应商",
              totalWithTax: "88.00",
            }],
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/input-invoice-usage/oa-reverse/staged-drafts") {
        return new Response(JSON.stringify({
          items: [{
            batchId: "batch-staged-backend",
            version: 2,
            status: "oa_draft_created",
            invoiceIds: ["inv-backend-1"],
            targetApplicantCode: "chen_xiuyun",
            targetApplicantName: "陈秀云",
            totalWithTax: "88.00",
            oaDraftId: "draft-hidden-from-ui",
            oaDraftUrl: "https://oa.example.test/draft/hidden",
            invoiceRows: [{
              invoiceId: "inv-backend-1",
              invoiceNo: "INV-BACKEND-1",
              displayNo: "SD-BACKEND-1",
              sellerName: "后端供应商",
              invoiceDate: "2026-05-20",
              totalWithTax: "88.00",
              paymentStatus: { label: "未付" },
            }],
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({}), { status: 404, headers: { "Content-Type": "application/json" } });
    }));

    const preview = await previewInputInvoiceUsageOaReverse({
      source: "explicitSelection",
      selectedInvoiceIds: ["inv-backend-1"],
    });
    const batch = await createInputInvoiceUsageOaReverseDraftFromSelection({
      previewId: preview.previewId ?? "",
      expectedPreviewHash: preview.previewHash,
      idempotencyKey: "create-backend-mapper",
      selectedInvoiceIds: ["inv-backend-1"],
      targetApplicantCode: "chen_xiuyun",
    });
    const history = await fetchInputInvoiceUsageOaReverseSubmittedHistory();
    const staged = await fetchInputInvoiceUsageOaReverseStagedDrafts();

    expect(preview.invoiceRows?.[0].invoiceId).toBe("inv-backend-1");
    expect(preview.targetApplicants).toEqual([{ code: "chen_xiuyun", name: "陈秀云", remark: "" }]);
    expect(preview.groups[0].invoiceRows?.[0].paymentStatusLabel).toBe("未付");
    expect(preview.rejectedInvoices[0]).toMatchObject({
      invoiceId: "inv-linked-backend",
      invoiceNumber: "INV-LINKED-BACKEND",
      displayNo: "INV-LINKED-BACKEND",
      sellerName: "已关联后端供应商",
      issueDate: "2026-05-21",
      totalWithTax: "66.00",
      paymentStatusLabel: "已关联 OA",
      oaRelationStatus: "linked",
      reasonCode: "already_has_active_oa",
    });
    expect(preview.groups[0].rejectedInvoices?.[0].paymentStatusLabel).toBe("已关联 OA");
    expect(preview.permissions?.canCreateDraft).toBe(true);
    expect(batch.invoiceIds).toEqual(["inv-backend-1"]);
    expect(batch.invoiceRows[0].displayNo).toBe("SD-BACKEND-1");
    expect(batch.previewSummary?.totalWithTax).toBe("88.00");
    expect(batch.oaDraftUrl).toBe("https://oa.example.test/draft/backend");
    expect(history.items[0].targetApplicantName).toBe("陈秀云");
    expect(history.items[0].invoices[0].sellerName).toBe("后端供应商");
    expect(staged.items[0].batchId).toBe("batch-staged-backend");
    expect(staged.items[0].status).toBe("oa_draft_created");
    expect(staged.items[0].invoiceRows[0].displayNo).toBe("SD-BACKEND-1");
  });

  const previewPayload: OaReversePreviewPayload = {
    previewId: "oa_reverse_preview_001",
    previewHash: "preview-hash-001",
    source: "explicitSelection",
    targetApplicantCode: "chen_xiuyun",
    targetApplicantName: "陈秀云",
    targetApplicants: [
      { code: "chen_xiuyun", name: "陈秀云" },
      { code: "zhou_jieying", name: "周洁莹" },
    ],
    invoiceCount: 2,
    totalWithTax: "99.72",
    groups: [
      {
        targetApplicantCode: "chen_xiuyun",
        targetApplicantName: "陈秀云",
        invoiceCount: 2,
        totalWithTax: "99.72",
        invoiceRows: [
          {
            invoiceId: "inv-001",
            invoiceNumber: "INV-001",
            displayNo: "SD-INV-001",
            sellerName: "昆明供应商一",
            issueDate: "2026-05-01",
            totalWithTax: "49.86",
            paymentStatusLabel: "待处理",
          },
          {
            invoiceId: "inv-002",
            invoiceNumber: "INV-002",
            displayNo: "SD-INV-002",
            sellerName: "昆明供应商二",
            issueDate: "2026-05-02",
            totalWithTax: "49.86",
            paymentStatusLabel: "待处理",
          },
        ],
        candidateInvoiceIds: ["inv-001", "inv-002"],
        rejectedInvoices: [
          { invoiceId: "inv-reject-001", reasonCode: "missing_target_account", reason: "缺少目标 OA 账号" },
        ],
      },
    ],
    warnings: [],
    canCreateDraft: false,
    nextAction: "create_batch",
  };
  const createReadyPreviewPayload: OaReversePreviewPayload = {
    ...previewPayload,
    canCreateDraft: true,
    permissions: { canCreateDraft: true },
    groups: previewPayload.groups.map((group) => ({
      ...group,
      invoiceRows: group.invoiceRows?.map((invoice) => ({ ...invoice, sellerName: "昆明供应商一" })),
    })),
  };

  test("OA reverse drawer calls loadPreview after opening and hides rejected invoice reasons to keep the workspace compact", async () => {
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    const createDraftFromSelection = vi.fn();

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByRole("dialog", { name: "以发票反提 OA" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "正在加载反提 OA 预览" })).toBeInTheDocument();
    expect(screen.queryByText("候选数、合计、拒绝原因和目标申请人均以后端返回为准")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(loadPreview).toHaveBeenCalledWith(expect.objectContaining({
        selectedInvoiceIds: [],
        targetApplicantCode: null,
      }));
    });
    expect(await screen.findByText("2 张")).toBeInTheDocument();
    expect(screen.getAllByText("99.72").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("陈秀云").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("chen_xiuyun")).not.toBeInTheDocument();
    expect(screen.queryByText("目标 OA 分组")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("以发票反提 OA 提示")).not.toBeInTheDocument();
    expect(screen.queryByText("不可提交原因")).not.toBeInTheDocument();
    expect(screen.queryByText("缺少目标 OA 账号")).not.toBeInTheDocument();
    expect(screen.queryByText("create_batch")).not.toBeInTheDocument();
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("昆明供应商一")).toBeInTheDocument();
    expect(screen.getByText("2026-05-02")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "开票日期" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "状态" })).not.toBeInTheDocument();
    expect(within(screen.getByText("SD-INV-002").closest("td") as HTMLElement).getByText("2026-05-02")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建本地批次" })).not.toBeInTheDocument();
    expect(screen.queryByText("尚未创建本地批次。")).not.toBeInTheDocument();
    const candidateSection = screen.getByRole("heading", { name: "待使用发票" }).closest("section") as HTMLElement;
    const createDraftButton = within(candidateSection).getByRole("button", { name: "创建 OA 草稿" });
    const candidateSearchInput = within(candidateSection).getByLabelText("搜索候选发票");
    expect(createDraftButton.compareDocumentPosition(candidateSearchInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "OA 草稿" })).not.toBeInTheDocument();
    expect(screen.queryByText("请选择候选发票后创建 OA 草稿。")).not.toBeInTheDocument();
    expect(createDraftButton).toBeDisabled();
  });

  test("OA reverse candidate search submits server query and resets the page", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    render(<OaReverseWorkspaceDrawer open loadPreview={loadPreview} onClose={() => undefined} />);
    await user.type(await screen.findByRole("searchbox", { name: "搜索候选发票" }), "4311.00");
    await user.click(screen.getByRole("button", { name: "查询" }));
    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: "4311.00", page: 1, pageSize: 50 })));
  });

  test("OA reverse drawer creates OA draft directly and records submitted confirmation", async () => {
    const user = userEvent.setup();
    const initialPreview: OaReversePreviewPayload = {
      ...previewPayload,
      permissions: { canCreateDraft: true },
    };
    const refreshedPreview: OaReversePreviewPayload = {
      ...initialPreview,
      previewId: "oa_reverse_preview_subset_001",
      previewHash: "preview-hash-subset-001",
      canCreateDraft: true,
      invoiceCount: 1,
      totalWithTax: "49.86",
      groups: [{
        ...initialPreview.groups[0],
        invoiceCount: 1,
        totalWithTax: "49.86",
        invoiceRows: initialPreview.groups[0].invoiceRows?.filter((invoice) => invoice.invoiceId === "inv-001"),
        candidateInvoiceIds: ["inv-001"],
        candidateInvoices: initialPreview.groups[0].candidateInvoices?.filter((invoice) => invoice.invoiceId === "inv-001"),
      }],
      invoiceRows: initialPreview.invoiceRows?.filter((invoice) => invoice.invoiceId === "inv-001"),
      candidateInvoices: initialPreview.candidateInvoices?.filter((invoice) => invoice.invoiceId === "inv-001"),
    };
    const loadPreview = vi.fn((request) => Promise.resolve(
      request.selectedInvoiceIds.length === 1 ? refreshedPreview : initialPreview,
    ));
    const createDraftFromSelection = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_001",
      version: 4,
      status: "oa_draft_created",
      invoiceIds: ["inv-001"],
      selectedInvoiceIds: ["inv-001"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-001",
      oaDetectionStatus: "draft_created",
      canConfirmSubmission: true,
    }));
    const manualStatus = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_001",
      version: 5,
      status: "submitted_confirmed",
      invoiceIds: ["inv-001"],
      selectedInvoiceIds: ["inv-001"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-001",
      oaDetectionStatus: "submitted_confirmed",
    }));
    const loadSubmittedHistory = vi.fn(() => Promise.resolve({
      items: [{
        targetApplicantName: "陈秀云",
        submittedAt: "2026-06-10T10:30:00+08:00",
        totalWithTax: "99.72",
        invoiceCount: 1,
        invoices: [{ invoiceNo: "SD-INV-001", invoiceDate: "2026-05-01", sellerName: "昆明供应商一", totalWithTax: "49.86" }],
      }],
    }));

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        manualStatus={manualStatus}
        loadSubmittedHistory={loadSubmittedHistory}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("checkbox", { name: "选择候选发票 SD-INV-001" }));
    expect(screen.queryByRole("button", { name: "创建本地批次" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(loadPreview).toHaveBeenCalledWith(expect.objectContaining({
      selectedInvoiceIds: ["inv-001"],
      targetApplicantCode: "chen_xiuyun",
    })));
    await waitFor(() => expect(createDraftFromSelection).toHaveBeenCalledWith(expect.objectContaining({
      previewId: "oa_reverse_preview_subset_001",
      expectedPreviewHash: "preview-hash-subset-001",
      selectedInvoiceIds: ["inv-001"],
      targetApplicantCode: "chen_xiuyun",
    })));
    const confirmDialog = await screen.findByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute("href", "https://oa.example.test/draft/oa-draft-001");
    expect(screen.queryByRole("button", { name: "刷新 OA 状态" })).not.toBeInTheDocument();

    await user.click(within(confirmDialog).getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ }));
    await waitFor(() => expect(manualStatus).toHaveBeenCalledWith("oa_reverse_batch_001", expect.objectContaining({
      decision: "submitted",
      expectedVersion: 4,
    })));
    expect(await screen.findByText("已进入已提交历史。")).toBeInTheDocument();
    expect(await screen.findByText("SD-INV-001")).toBeInTheDocument();
  });

  test("OA reverse drawer revalidates exact selection even when the candidate set is unchanged", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const createDraftFromSelection = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_fast_create",
      version: 2,
      status: "oa_draft_created",
      invoiceIds: ["inv-001", "inv-002"],
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-fast-create",
      oaDraftUrl: "https://oa.example.test/draft/fast-create",
      canConfirmSubmission: true,
    }));

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));

    await waitFor(() => expect(createDraftFromSelection).toHaveBeenCalledWith(expect.objectContaining({
      previewId: createReadyPreviewPayload.previewId,
      expectedPreviewHash: createReadyPreviewPayload.previewHash,
      selectedInvoiceIds: ["inv-001", "inv-002"],
    })));
    expect(loadPreview).toHaveBeenCalledTimes(3);
  });

  test("OA reverse draft confirmation stays open across parent rerenders until the user decides", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const createDraftFromSelection = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_persistent_dialog",
      version: 2,
      status: "oa_draft_created",
      invoiceIds: ["inv-001", "inv-002"],
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoiceRows: [],
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-persistent",
      oaDraftUrl: "https://oa.example.test/draft/persistent",
      canConfirmSubmission: true,
    }));
    const props = {
      open: true,
      loadPreview,
      createDraftFromSelection,
      manualStatus: vi.fn(),
      onClose: () => undefined,
    };
    const { rerender } = render(
      <OaReverseWorkspaceDrawer
        {...props}

      />,
    );

    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    expect(await screen.findByRole("dialog", { name: "OA 草稿提交确认" })).toBeInTheDocument();

    rerender(
      <OaReverseWorkspaceDrawer
        {...props}

      />,
    );

    await waitFor(() => expect(loadPreview).toHaveBeenCalledTimes(3));
    const confirmDialog = screen.getByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ })).toBeInTheDocument();
    expect(within(confirmDialog).getByRole("button", { name: /OA提交内容需修改\s+删除本次提交内容/ })).toBeInTheDocument();

    rerender(
      <OaReverseWorkspaceDrawer
        {...props}


      />,
    );

    await waitFor(() => expect(loadPreview).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("dialog", { name: "OA 草稿提交确认" })).toBeInTheDocument();
  });

  test("OA reverse rejects a changed selection instead of silently submitting the remaining invoices", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn((request) => Promise.resolve(request.selectedInvoiceIds.length ? {
      ...createReadyPreviewPayload, groups: [{ ...createReadyPreviewPayload.groups[0], invoiceRows: [createReadyPreviewPayload.groups[0].invoiceRows![0]] }],
    } : createReadyPreviewPayload));
    const createDraftFromSelection = vi.fn();
    render(<OaReverseWorkspaceDrawer open loadPreview={loadPreview} createDraftFromSelection={createDraftFromSelection} onClose={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    expect(await screen.findByText("所选发票的关联或占用状态已变化，请刷新并重新选择。")).toBeInTheDocument();
    expect(createDraftFromSelection).not.toHaveBeenCalled();
  });

  test("OA reverse reports a newly bank-linked invoice and never creates a partial draft", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn((request) => Promise.resolve(request.selectedInvoiceIds.length ? {
      ...createReadyPreviewPayload,
      groups: [], invoiceRows: [],
      rejectedInvoices: [{ invoiceId: "inv-001", invoiceNumber: "SD-INV-001", reason: "发票已关联银行流水，不能反提 OA" }],
    } : createReadyPreviewPayload));
    const createDraftFromSelection = vi.fn();
    render(<OaReverseWorkspaceDrawer open loadPreview={loadPreview} createDraftFromSelection={createDraftFromSelection} onClose={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    expect(await screen.findByText("SD-INV-001：发票已关联银行流水，不能反提 OA")).toBeInTheDocument();
    expect(createDraftFromSelection).not.toHaveBeenCalled();
  });

  test("OA reverse staged tab recovers a draft after closing confirmation without exposing draft link", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const stagedBatch = {
      batchId: "oa_reverse_batch_staged",
      version: 2,
      status: "oa_draft_created",
      invoiceIds: ["inv-001"],
      selectedInvoiceIds: ["inv-001"],
      totalWithTax: "49.86",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoiceRows: [{
        invoiceId: "inv-001",
        invoiceNumber: "SD-STAGED-001",
        displayNo: "SD-STAGED-001",
        sellerName: "暂存供应商",
        issueDate: "2026-05-01",
        totalWithTax: "49.86",
        paymentStatusLabel: "待处理",
      }],
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-staged",
      oaDraftUrl: "https://oa.example.test/draft/staged",
      canConfirmSubmission: true,
    };
    const createDraftFromSelection = vi.fn(() => Promise.resolve(stagedBatch));
    const loadStagedDrafts = vi.fn(() => Promise.resolve({ items: [stagedBatch] }));
    const manualStatus = vi.fn(() => Promise.resolve({
      ...stagedBatch,
      version: 3,
      status: "submitted_confirmed",
      oaDetectionStatus: "user_confirmed_submitted",
    }));

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        loadStagedDrafts={loadStagedDrafts}
        manualStatus={manualStatus}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    const confirmDialog = await screen.findByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ })).toBeInTheDocument();
    expect(within(confirmDialog).getByRole("button", { name: /OA提交内容需修改\s+删除本次提交内容/ })).toBeInTheDocument();
    await user.click(within(confirmDialog).getByRole("button", { name: "关闭确认弹窗" }));

    expect(screen.queryByRole("dialog", { name: "OA 草稿提交确认" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "暂存" }));

    expect(await screen.findByText("SD-STAGED-001")).toBeInTheDocument();
    expect(screen.getByText("暂存供应商")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /OA 草稿|打开/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ }));

    await waitFor(() => expect(manualStatus).toHaveBeenCalledWith("oa_reverse_batch_staged", expect.objectContaining({
      expectedVersion: 2,
      decision: "submitted",
    })));
  });

  test("OA reverse describes the unused scope and preserves full invoice numbers", async () => {
    const number = "00123456789012345678";
    const first = { ...createReadyPreviewPayload.groups[0].invoiceRows![0], displayNo: number, invoiceNumber: number };
    const loadPreview = vi.fn(() => Promise.resolve({ ...createReadyPreviewPayload,
      invoiceCount: 384, groups: [], invoiceRows: [first],
    }));
    render(<OaReverseWorkspaceDrawer open loadPreview={loadPreview} onClose={() => undefined} />);
    expect(await screen.findByRole("heading", { name: "待使用发票" })).toBeInTheDocument();
    expect(screen.getByText(number, { exact: true })).toHaveTextContent(number);
    expect(screen.getByRole("checkbox", { name: `选择候选发票 ${number}` })).toBeEnabled();
    expect(screen.getByText("可选择")).toBeInTheDocument();
    expect(screen.queryByLabelText("筛选流水关联状态")).not.toBeInTheDocument();
    expect(loadPreview).toHaveBeenCalledTimes(1);
  });

  test("OA reverse inherits scope, keeps search local and resets scope on reopen", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const initialScope = { keyword: "销方", month: "2026-09", invoiceDateFrom: "2026-09-01", invoiceDateTo: "2026-09-30", filters: [{ field: "oa_relation", operator: "equals" as const, value: "unlinked" }] };
    const { rerender } = render(<OaReverseWorkspaceDrawer open initialScope={initialScope} loadPreview={loadPreview} onClose={() => undefined} />);
    const search = await screen.findByRole("searchbox", { name: "搜索候选发票" });
    expect(search).toHaveValue("销方");
    expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({ ...initialScope, page: 1 }));
    await user.clear(search);
    await user.type(search, "500");
    await user.click(screen.getByRole("button", { name: "查询" }));
    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({ ...initialScope, keyword: "500", page: 1 })));
    expect(initialScope.keyword).toBe("销方");
    const nextScope = { ...initialScope, keyword: "新销方", month: "2026-10" };
    rerender(<OaReverseWorkspaceDrawer open={false} initialScope={nextScope} loadPreview={loadPreview} onClose={() => undefined} />);
    rerender(<OaReverseWorkspaceDrawer open initialScope={nextScope} loadPreview={loadPreview} onClose={() => undefined} />);
    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({ ...nextScope, page: 1 })));
    expect(await screen.findByRole("searchbox", { name: "搜索候选发票" })).toHaveValue("新销方");
  });

  test("OA reverse keeps cross-page selection and disables occupied invoices without reducing totals", async () => {
    const user = userEvent.setup();
    const first = createReadyPreviewPayload.groups[0].invoiceRows![0];
    const second = { ...first, invoiceId: "inv-002", displayNo: "SD-INV-002", occupiedBatchId: "batch-existing", bankRelationStatus: "unlinked" as const };
    const loadPreview = vi.fn((request) => Promise.resolve({ ...createReadyPreviewPayload, invoiceCount: 51,
      pagination: { page: request.page || 1, pageSize: 50, total: 51 },
      groups: [], invoiceRows: request.page === 2 ? [second] : [first],
    }));
    render(<OaReverseWorkspaceDrawer open loadPreview={loadPreview} onClose={() => undefined} />);
    expect(await screen.findByRole("checkbox", { name: "选择候选发票 SD-INV-001" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByRole("checkbox", { name: /暂存或提交中的发票 SD-INV-002/ })).toBeDisabled();
    expect(screen.getByText(/已选 1 张（其中 1 张不在本页）/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "上一页" }));
    expect(await screen.findByRole("checkbox", { name: "选择候选发票 SD-INV-001" })).toBeChecked();
    expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }));
  });

  test("unknown draft results remain visible and require explicit verified release without retrying creation", async () => {
    const user = userEvent.setup();
    const failed = { batchId: "failed-batch", version: 7, status: "oa_draft_failed", invoiceIds: ["inv-001"], selectedInvoiceIds: ["inv-001"], totalWithTax: "49.86", targetApplicantName: "陈秀云", invoiceRows: createReadyPreviewPayload.groups[0].invoiceRows!, invoices: [], rejectedInvoices: [], draftRequestState: "unknown" as const, canRelease: true, canConfirmSubmission: false, oaDetectionError: "OA 响应超时" };
    const manualStatus = vi.fn(() => Promise.resolve({ ...failed, status: "not_submitted", canRelease: false }));
    const createDraftFromSelection = vi.fn();
    const loadStagedDrafts = vi.fn(() => Promise.resolve({ items: [failed] }));
    const onChanged = vi.fn();
    render(<OaReverseWorkspaceDrawer open loadPreview={() => Promise.resolve(createReadyPreviewPayload)} loadStagedDrafts={loadStagedDrafts} manualStatus={manualStatus} createDraftFromSelection={createDraftFromSelection} onChanged={onChanged} onClose={() => undefined} />);
    await user.click(await screen.findByRole("tab", { name: "暂存" }));
    expect(await screen.findByText(/创建结果不明/)).toBeInTheDocument();
    expect(screen.getByText(/不会删除 OA 中的草稿/)).toBeInTheDocument();
    expect(screen.getByText("OA 响应超时")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /我已在OA系统提交/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "已核实并清理 OA 草稿，解除本地占用" }));
    await waitFor(() => expect(manualStatus).toHaveBeenCalledWith("failed-batch", expect.objectContaining({ decision: "not_submitted", expectedVersion: 7, reason: "用户已到 OA 核实并删除可能存在的草稿，确认无有效 OA 单据，解除本地发票占用" })));
    expect(await screen.findByText("已解除本地暂存占用，返回候选后可重新选择发票。")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(createDraftFromSelection).not.toHaveBeenCalled();
  });

  test("requesting batches cannot be released or recreated and can be refreshed manually", async () => {
    const user = userEvent.setup();
    const requesting = { batchId: "request-batch", version: 3, status: "draft", invoiceIds: ["inv-001"], selectedInvoiceIds: ["inv-001"], totalWithTax: "49.86", targetApplicantName: "陈秀云", invoiceRows: [], invoices: [], rejectedInvoices: [], draftRequestState: "requesting" as const, canRelease: false, canConfirmSubmission: false };
    const loadStagedDrafts = vi.fn(() => Promise.resolve({ items: [requesting] }));
    const createDraftFromSelection = vi.fn();
    const manualStatus = vi.fn();
    render(<OaReverseWorkspaceDrawer open loadPreview={() => Promise.resolve(createReadyPreviewPayload)} loadStagedDrafts={loadStagedDrafts} manualStatus={manualStatus} createDraftFromSelection={createDraftFromSelection} onClose={() => undefined} />);
    await user.click(await screen.findByRole("tab", { name: "暂存" }));
    expect(await screen.findByText(/OA 创建请求正在处理/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /解除.*占用|创建 OA 草稿|我已在OA系统提交/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新暂存状态" }));
    await waitFor(() => expect(loadStagedDrafts).toHaveBeenCalledTimes(2));
    expect(createDraftFromSelection).not.toHaveBeenCalled();
    expect(manualStatus).not.toHaveBeenCalled();
  });

  test("staged batches beyond the first fifty remain reachable with load more", async () => {
    const user = userEvent.setup();
    const base = { version: 1, status: "draft", invoiceIds: ["inv-1"], selectedInvoiceIds: ["inv-1"], totalWithTax: "1", invoiceRows: [], invoices: [], rejectedInvoices: [], draftRequestState: "not_started" as const, canRelease: true };
    const batches = Array.from({ length: 51 }, (_, index) => ({ ...base, batchId: `batch-${index}`, targetApplicantName: `申请人 ${index}` }));
    const loadStagedDrafts = vi.fn((limit = 50) => Promise.resolve({ items: batches.slice(0, limit) }));
    render(<OaReverseWorkspaceDrawer open loadPreview={() => Promise.resolve(createReadyPreviewPayload)} loadStagedDrafts={loadStagedDrafts} manualStatus={vi.fn()} onClose={() => undefined} />);
    await user.click(await screen.findByRole("tab", { name: "暂存" }));
    await user.click(await screen.findByRole("button", { name: "加载更多暂存批次" }));
    await waitFor(() => expect(loadStagedDrafts).toHaveBeenLastCalledWith(100));
    expect(await screen.findByText("申请人 50")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "加载更多暂存批次" })).not.toBeInTheDocument();
  });

  test("OA reverse drawer lets the backend target applicant list drive preview and batch target", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn((request) => Promise.resolve({
      ...createReadyPreviewPayload,
      targetApplicantCode: request.targetApplicantCode || "chen_xiuyun",
      targetApplicantName: request.targetApplicantCode === "zhou_jieying" ? "周洁莹" : "陈秀云",
      groups: [{
        ...createReadyPreviewPayload.groups[0],
        targetApplicantCode: request.targetApplicantCode || "chen_xiuyun",
        targetApplicantName: request.targetApplicantCode === "zhou_jieying" ? "周洁莹" : "陈秀云",
      }],
    }));
    const createDraftFromSelection = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_target",
      version: 1,
      status: "oa_draft_created",
      invoiceIds: ["inv-001", "inv-002"],
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "zhou_jieying",
      targetApplicantName: "周洁莹",
      oaDraftId: "oa-draft-target",
      oaDraftUrl: "https://oa.example.test/draft/target",
      invoiceRows: [],
      invoices: [],
      rejectedInvoices: [],
    }));

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        onClose={() => undefined}
      />,
    );

    const selector = await screen.findByLabelText("反提 OA 申请人");
    await user.click(selector);
    await user.click(await screen.findByRole("option", { name: "周洁莹" }));

    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({
      targetApplicantCode: "zhou_jieying",
    })));
    await user.click(screen.getByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(createDraftFromSelection).toHaveBeenCalledWith(expect.objectContaining({
      targetApplicantCode: "zhou_jieying",
    })));
  });

  test("OA reverse drawer cancels stale target applicant preview requests", async () => {
    const user = userEvent.setup();
    let callCount = 0;
    const previewSignals: AbortSignal[] = [];
    const loadPreview = vi.fn((request) => {
      callCount += 1;
      previewSignals.push(request.signal as AbortSignal);
      if (callCount === 1) {
        return Promise.resolve(createReadyPreviewPayload);
      }
      if (callCount === 2) {
        return new Promise<OaReversePreviewPayload>(() => undefined);
      }
      return Promise.resolve({
        ...createReadyPreviewPayload,
        previewHash: "preview-hash-returned-to-chen",
        targetApplicantCode: "chen_xiuyun",
        targetApplicantName: "陈秀云",
        groups: [{
          ...createReadyPreviewPayload.groups[0],
          targetApplicantCode: "chen_xiuyun",
          targetApplicantName: "陈秀云",
        }],
      });
    });

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={vi.fn()}
        onClose={() => undefined}
      />,
    );

    const selector = await screen.findByLabelText("反提 OA 申请人");
    await user.click(selector);
    await user.click(await screen.findByRole("option", { name: "周洁莹" }));
    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({
      targetApplicantCode: "zhou_jieying",
    })));
    expect(screen.getByRole("progressbar", { name: "正在加载反提 OA 预览" })).toBeInTheDocument();

    await user.click(screen.getByLabelText("反提 OA 申请人"));
    await user.click(await screen.findByRole("option", { name: "陈秀云" }));

    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({
      targetApplicantCode: "chen_xiuyun",
    })));
    expect(previewSignals[1].aborted).toBe(true);
    await waitFor(() => {
      expect(screen.queryByRole("progressbar", { name: "正在加载反提 OA 预览" })).not.toBeInTheDocument();
    });
  });

  test("OA reverse not-submitted confirmation returns to create state without visible rollback history", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const createDraftFromSelection = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_not_submitted",
      version: 2,
      status: "oa_draft_created",
      invoiceIds: ["inv-001"],
      selectedInvoiceIds: ["inv-001"],
      totalWithTax: "49.86",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoiceRows: [],
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-not-submitted",
      oaDraftUrl: "https://oa.example.test/draft/not-submitted",
      canConfirmSubmission: true,
    }));
    const manualStatus = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_not_submitted",
      version: 3,
      status: "not_submitted",
      invoiceIds: ["inv-001"],
      selectedInvoiceIds: ["inv-001"],
      totalWithTax: "49.86",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoiceRows: [],
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: null,
      oaDraftUrl: null,
      canCreateDraft: true,
    }));
    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        manualStatus={manualStatus}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    const confirmDialog = await screen.findByRole("dialog", { name: "OA 草稿提交确认" });
    await user.click(within(confirmDialog).getByRole("button", { name: /OA提交内容需修改\s+删除本次提交内容/ }));

    await waitFor(() => expect(manualStatus).toHaveBeenCalledWith("oa_reverse_batch_not_submitted", expect.objectContaining({
      expectedVersion: 2,
      decision: "not_submitted",
    })));
    expect(screen.queryByRole("dialog", { name: "OA 草稿提交确认" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建 OA 草稿" })).toBeEnabled();
    expect(screen.queryByText("oa_reverse_batch_not_submitted")).not.toBeInTheDocument();
  });

  test("OA reverse submitted tab renders compact business history without internal identifiers", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(createReadyPreviewPayload));
    const loadSubmittedHistory = vi.fn(() => Promise.resolve({
      items: [{
        batchId: "batch-hidden",
        oaDraftId: "draft-hidden",
        status: "submitted_confirmed",
        targetApplicantName: "陈秀云",
        submittedAt: "2026-06-10T10:30:00+08:00",
        totalWithTax: "99.72",
        invoiceCount: 2,
        invoices: [
          { invoiceNo: "SD-INV-001", invoiceDate: "2026-05-01", sellerName: "昆明供应商一", totalWithTax: "49.86" },
          { invoiceNo: "SD-INV-002", invoiceDate: "2026-05-02", sellerName: "昆明供应商二", totalWithTax: "49.86" },
        ],
      }],
    }));

    render(
      <OaReverseWorkspaceDrawer
        open


        loadPreview={loadPreview}
        loadSubmittedHistory={loadSubmittedHistory}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("tab", { name: "已提交" }));

    await screen.findByRole("grid", { name: "陈秀云已提交发票" });
    expect(screen.getByText("2026-06-10 10:30")).toBeInTheDocument();
    expect(screen.getByText("陈秀云")).toBeInTheDocument();
    expect(screen.getByText("99.72")).toBeInTheDocument();
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("昆明供应商二")).toBeInTheDocument();
    expect(screen.queryByText("2026-06-10T10:30:00+08:00")).not.toBeInTheDocument();
    expect(screen.queryByText("batch-hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("draft-hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("submitted_confirmed")).not.toBeInTheDocument();
    expect(screen.queryByText("previewHash")).not.toBeInTheDocument();
  });

  test("payment status rules display a read-only native table", async () => {
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: true, permissions: { canSave: false }, applicantOptions: [], rules: [
      { id: "r1", statusCode: "custom_wait", label: "待核付", description: "", enabled: true, conditions: { hasOa: true, hasBank: false } },
    ] };
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} onClose={() => undefined} />);
    expect(await screen.findByRole("table", { name: "支付状态规则" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "标签 1" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    expect(screen.queryByText(/分类按实际流水/)).not.toBeInTheDocument();
  });

  test("rules save explicit OA, net sign and comparison conditions with version", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 7, readOnly: false, permissions: { canSave: true }, applicantOptions: [
      { userId: "1", name: "陈秀云", account: "CHEN", enabled: true, matchName: "陈秀云" }, { userId: "2", name: "周洁莹", account: "ZHOU", enabled: false, matchName: "周洁莹" },
    ], rules: [{ id: "r1", statusCode: "custom_wait", label: "待核付", description: "", enabled: true, conditions: { hasOa: true, applicantNames: ["陈秀云"], hasBank: false } }] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, version: 8, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.click(await screen.findByLabelText("待核付 OA 申请人条件"));
    await user.click(await screen.findByRole("option", { name: "周洁莹 ZHOU" })); await user.keyboard("{Escape}");
    await user.click(screen.getByLabelText("待核付 发票净额条件")); await user.click(await screen.findByRole("option", { name: "＜0" }));
    expect(screen.getByLabelText("待核付 金额比较不可用")).toHaveTextContent("—");
    await user.click(screen.getByLabelText("待核付 流水条件")); await user.click(await screen.findByRole("option", { name: "✓", exact: true }));
    await user.click(screen.getByLabelText("待核付 金额比较条件")); await user.click(await screen.findByRole("option", { name: "≤", exact: true }));
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({ expectedVersion: 7, rules: [expect.objectContaining({ statusCode: "custom_wait", conditions: { hasOa: true, applicantNames: ["陈秀云", "周洁莹"], hasBank: true, invoiceNetSign: "negative", paymentComparison: "less_equal" } })] })));
    expect(await screen.findByText("规则已保存。")).toBeInTheDocument();
  });

  test("no-bank selection clears payment comparison in draft and restore recovers the saved condition", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [{ id: "r1", statusCode: "custom_one", label: "比较", description: "", conditions: { hasBank: true, paymentComparison: "equal" } }] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.click(await screen.findByLabelText("比较 流水条件")); await user.click(await screen.findByRole("option", { name: "✕", exact: true }));
    expect(screen.getByLabelText("比较 金额比较不可用")).toHaveTextContent("—");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "还原", exact: true }));
    expect(screen.getByLabelText("比较 金额比较条件")).toHaveTextContent("＝");
    expect(screen.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
    await user.click(screen.getByLabelText("比较 流水条件")); await user.click(await screen.findByRole("option", { name: "✕", exact: true }));
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({ rules: [expect.objectContaining({ conditions: { hasBank: false } })] })));
  });

  test("inclusive operators round-trip without priority controls", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 3, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [
      { id: "r1", statusCode: "custom_first", label: "第一", description: "", enabled: true, conditions: { hasBank: true, paymentComparison: "equal" } },
      { id: "r2", statusCode: "custom_second", label: "第二", description: "", enabled: true, conditions: { hasBank: false, invoiceNetSign: "positive" } },
    ] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, version: 4, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.click(await screen.findByLabelText("第一 金额比较条件")); await user.click(await screen.findByRole("option", { name: "≥", exact: true }));
    await user.click(screen.getByLabelText("第一 发票净额条件")); await user.click(await screen.findByRole("option", { name: "≥0", exact: true }));
    expect(screen.queryByRole("button", { name: "下移规则 第一" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({ expectedVersion: 3, rules: [
      expect.objectContaining({ id: "r1", statusCode: "custom_first", conditions: { hasBank: true, paymentComparison: "greater_equal", invoiceNetSign: "nonnegative" } }),
      expect.objectContaining({ id: "r2", statusCode: "custom_second" }),
    ] })));
    expect(screen.getByLabelText("第一 金额比较条件")).toHaveTextContent("≥");
    expect(screen.getByLabelText("第一 发票净额条件")).toHaveTextContent("≥0");
  });

  test("choosing no OA clears applicant conditions without changing bank or net amount", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [
      { id: "r1", statusCode: "custom_one", label: "规则", description: "", conditions: { hasOa: true, applicantNames: ["历史申请人"], hasBank: false, invoiceNetSign: "zero" } },
    ] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, version: 2, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.click(await screen.findByLabelText("规则 OA 申请人条件")); await user.click(await screen.findByRole("option", { name: "无 OA", exact: true }));
    expect(screen.queryByText("发票/OA 金额匹配")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({ rules: [expect.objectContaining({ conditions: { hasOa: false, hasBank: false, invoiceNetSign: "zero" } })] })));
  });

  test("initial rule-directory failure remains explicit and can be reloaded", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [] };
    const loadRules = vi.fn().mockRejectedValueOnce(new Error("OA 目录不可用")).mockResolvedValue(payload);
    render(<PaymentStatusRulesDrawer open loadRules={loadRules} saveRules={vi.fn()} onClose={() => undefined} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("OA 目录不可用"); expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试读取" }));
    expect(await screen.findByRole("table", { name: "支付状态规则" })).toBeInTheDocument(); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("new rules choose group and existing label explicitly, checkbox and rename retain identity", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, version: 2, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: "新增规则" }));
    await user.click(screen.getByRole("button", { name: "取消新增" }));
    expect(screen.queryByRole("button", { name: "添加", exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "新增规则" })); await user.click(screen.getByRole("button", { name: "添加", exact: true }));
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "标签 1" }), "抵账");
    expect(screen.getByRole("button", { name: "保存" })).toBeEnabled();
    await user.click(screen.getByLabelText("抵账 发票净额条件")); await user.click(await screen.findByRole("option", { name: "＝0" }));
    expect(screen.queryByRole("button", { name: "复制规则 抵账" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新增规则" }));
    await user.click(screen.getByLabelText("新增规则付款状态")); await user.click(await screen.findByRole("option", { name: "未付款", exact: true }));
    await user.click(screen.getByLabelText("新增规则标签")); await user.click(await screen.findByRole("option", { name: "抵账", exact: true }));
    await user.click(screen.getByRole("button", { name: "添加", exact: true }));
    await user.clear(screen.getByRole("textbox", { name: "标签 1" })); await user.type(screen.getByRole("textbox", { name: "标签 1" }), "抵账改名");
    expect(screen.getByRole("textbox", { name: "标签 2" })).toHaveValue("抵账改名");
    await user.click(screen.getAllByRole("checkbox", { name: "启用规则 抵账改名" })[0]);
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(saveRules).toHaveBeenCalledTimes(1));
    const saved = saveRules.mock.calls[0][0].rules;
    expect(saved[0].statusCode).toMatch(/^custom_/); expect(saved[1].statusCode).toBe(saved[0].statusCode); expect(saved[1].id).not.toBe(saved[0].id);
    expect(saved[0].enabled).toBe(false);
    expect(saved[0].conditions.hasBank).toBe(true); expect(saved[1].conditions.hasBank).toBe(false);
    expect(saved[0]).not.toHaveProperty("priority");
    await user.click(screen.getAllByRole("button", { name: "删除规则 抵账改名" })[0]);
    await user.click(screen.getByRole("button", { name: "保存" })); await waitFor(() => expect(saveRules).toHaveBeenCalledTimes(2));
    expect(saveRules.mock.calls[1][0].rules[0].statusCode).toBe(saved[0].statusCode);
  });

  test("saving locks the draft, drag handle and close controls until the committed order is read back", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [
      { id: "r1", statusCode: "custom_one", label: "规则一", description: "", enabled: true, conditions: { hasBank: true } },
    ] };
    let resolve!: (next: PaymentStatusRulesPayload) => void;
    const saveRules = vi.fn(() => new Promise<PaymentStatusRulesPayload>(done => { resolve = done; }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={() => undefined} />);
    await user.type(await screen.findByRole("textbox", { name: "标签 1" }), "修改");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    expect(screen.getByRole("textbox", { name: "标签 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /调整规则 规则一修改 的顺序/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "启用规则 规则一修改" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "关闭支付状态规则抽屉" })).toBeDisabled();
    await act(async () => resolve({ ...payload, version: 2, rules: [{ ...payload.rules[0], label: "规则一修改" }] }));
    expect(await screen.findByText("规则已保存。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "标签 1" })).toBeEnabled();
  });

  test("version conflicts preserve draft and reload gets a fresh version only after discard", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [{ id: "r1", statusCode: "custom_one", label: "原标签", description: "", conditions: { hasBank: true } }] };
    const loadRules = vi.fn().mockResolvedValueOnce(payload).mockResolvedValue({ ...payload, version: 2 });
    const saveRules = vi.fn().mockRejectedValueOnce({ status: 409 }).mockImplementation(request => Promise.resolve({ ...payload, version: 3, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={loadRules} saveRules={saveRules} onClose={() => undefined} />);
    await user.type(await screen.findByRole("textbox", { name: "标签 1" }), "草稿"); await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("规则已被其他人更新");
    expect(screen.getByRole("textbox", { name: "标签 1" })).toHaveValue("原标签草稿");
    await user.click(screen.getByRole("button", { name: "重试读取" })); await user.click(screen.getByRole("button", { name: "继续编辑" })); expect(loadRules).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "重试读取" })); await user.click(screen.getByRole("button", { name: "放弃修改" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "标签 1" })).toHaveValue("原标签"));
    await user.type(screen.getByRole("textbox", { name: "标签 1" }), "新版"); await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(saveRules.mock.calls[1][0].expectedVersion).toBe(2));
  });

  test("save success and list refresh failure are distinct and retry never saves twice", async () => {
    const user = userEvent.setup();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [{ id: "r1", statusCode: "custom_one", label: "标签", description: "", conditions: { hasBank: true } }] };
    const saveRules = vi.fn(request => Promise.resolve({ ...payload, version: 2, rules: request.rules }));
    const onSaved = vi.fn().mockRejectedValueOnce(new Error("规则已保存，列表刷新失败")).mockResolvedValue(undefined);
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onSaved={onSaved} onClose={() => undefined} />);
    await user.type(await screen.findByRole("textbox", { name: "标签 1" }), "修改"); await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("列表刷新失败"); expect(screen.getByText("规则已保存。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled(); await user.click(screen.getByRole("button", { name: "重试刷新" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument()); expect(saveRules).toHaveBeenCalledTimes(1);
  });

  test("rules retain unsaved edits on cancelled close and save failure, and explicit empty rules can save", async () => {
    const user = userEvent.setup(); const onClose = vi.fn();
    const payload: PaymentStatusRulesPayload = { version: 1, readOnly: false, permissions: { canSave: true }, applicantOptions: [], rules: [] };
    const saveRules = vi.fn().mockRejectedValueOnce(new Error("保存失败")).mockImplementation(request => Promise.resolve({ ...payload, rules: request.rules }));
    render(<PaymentStatusRulesDrawer open loadRules={() => Promise.resolve(payload)} saveRules={saveRules} onClose={onClose} />);
    await user.click(await screen.findByRole("button", { name: "新增规则" })); await user.click(screen.getByRole("button", { name: "添加", exact: true })); await user.type(screen.getByRole("textbox", { name: "标签 1" }), "新标签");
    await user.click(screen.getByLabelText("新标签 流水条件")); await user.click(await screen.findByRole("option", { name: "✕", exact: true }));
    await user.click(screen.getByRole("button", { name: "关闭支付状态规则抽屉" })); await user.click(screen.getByRole("button", { name: "继续编辑" })); expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存" })); expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
    expect(screen.getByRole("textbox", { name: "标签 1" })).toHaveValue("新标签");
    await user.click(screen.getByRole("button", { name: "保存" })); await waitFor(() => expect(saveRules).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "删除规则 新标签" })); await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(saveRules.mock.calls[2][0].rules).toEqual([]));
  });

  test("parent state can keep the two workflow drawers mutually exclusive", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      rules: [],
      applicantOptions: [{ userId: "1", name: "陈秀云", account: "CHEN", enabled: true, matchName: "陈秀云" }, { userId: "2", name: "周洁莹", account: "ZHOU", enabled: false, matchName: "周洁莹" }],
    }));

    function Harness() {
      const [activeWorkflow, setActiveWorkflow] = useState<"oaReverse" | "paymentRules" | null>(null);
      return (
        <>
          <button type="button" onClick={() => setActiveWorkflow("oaReverse")}>以发票反提 OA</button>
          <button type="button" onClick={() => setActiveWorkflow("paymentRules")}>发票与支付状态规则设置</button>
          <OaReverseWorkspaceDrawer
            open={activeWorkflow === "oaReverse"}


            loadPreview={loadPreview}
            onClose={() => setActiveWorkflow(null)}
          />
          <PaymentStatusRulesDrawer
            open={activeWorkflow === "paymentRules"}
            loadRules={loadRules}
            onClose={() => setActiveWorkflow(null)}
          />
        </>
      );
    }

    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "以发票反提 OA" }));
    expect(await screen.findByLabelText("以发票反提 OA 工作流")).toBeInTheDocument();
    expect(screen.queryByLabelText("发票与支付状态规则设置")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭以发票反提 OA 工作流" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "以发票反提 OA" })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "发票与支付状态规则设置" }));
    await waitFor(() => {
      expect(screen.queryByLabelText("以发票反提 OA 工作流")).not.toBeInTheDocument();
    });
    expect(await screen.findByLabelText("发票与支付状态规则设置")).toBeInTheDocument();
  });

  test("opening and closing workflow drawers does not invoke the parent rows loader", async () => {
    const user = userEvent.setup();
    const loadRows = vi.fn();
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      rules: [],
      applicantOptions: [],
    }));

    function Harness() {
      const [activeWorkflow, setActiveWorkflow] = useState<"oaReverse" | "paymentRules" | null>(null);
      return (
        <>
          <button type="button" onClick={loadRows}>加载主表</button>
          <button type="button" onClick={() => setActiveWorkflow("oaReverse")}>以发票反提 OA</button>
          <button type="button" onClick={() => setActiveWorkflow("paymentRules")}>发票与支付状态规则设置</button>
          <OaReverseWorkspaceDrawer
            open={activeWorkflow === "oaReverse"}


            loadPreview={loadPreview}
            onClose={() => setActiveWorkflow(null)}
          />
          <PaymentStatusRulesDrawer
            open={activeWorkflow === "paymentRules"}
            loadRules={loadRules}
            onClose={() => setActiveWorkflow(null)}
          />
        </>
      );
    }

    render(<Harness />);
    const oaReverseOpener = screen.getByRole("button", { name: "以发票反提 OA" });
    await user.click(oaReverseOpener);
    await screen.findByLabelText("以发票反提 OA 工作流");
    await user.click(screen.getByRole("button", { name: "关闭以发票反提 OA 工作流" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "以发票反提 OA" })).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(oaReverseOpener));
    await user.click(screen.getByRole("button", { name: "发票与支付状态规则设置" }));
    await screen.findByLabelText("发票与支付状态规则设置");

    await act(async () => undefined);
    expect(loadRows).not.toHaveBeenCalled();
  });
});
