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
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemcheckbox\"")
        && sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemradio\"")
        ? null
        : "InputInvoiceUsageFilterMenu.tsx should preserve menuitemcheckbox and menuitemradio semantics",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageDetailDrawer.tsx should use AppDrawer",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageExportDrawer.tsx should use AppDrawer",
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

    expect(within(menu).getByRole("menuitemcheckbox", { name: "待处理 8" })).toBeChecked();
    expect(within(menu).getByRole("menuitemcheckbox", { name: "现金往来 2" })).not.toBeChecked();
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

    expect(screen.getByRole("progressbar", { name: "正在加载详情" })).toBeInTheDocument();
    await waitFor(() => expect(loadDetail).toHaveBeenCalledWith(target));
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
        sections: [{ title: "关联 OA", fields: [{ label: "关系数量", value: 2 }] }],
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
    expect(await screen.findByText("关联 OA")).toBeInTheDocument();
    expect(screen.getByText("关系数量")).toBeInTheDocument();
  });
});

describe("Input invoice usage workflow drawers", () => {
  test("relation detail mapper surfaces unavailable detail state", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      expect(url.pathname).toBe("/api/input-invoice-usage/rows/row-refreshing/relation-details");
      expect(url.searchParams.get("kind")).toBe("oa");
      return new Response(JSON.stringify({
        row_id: "row-refreshing",
        kind: "oa",
        title: "OA关联明细",
        detailAvailable: false,
        unavailableReason: "进项发票使用情况关联明细暂不可用。",
        sections: [],
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
    });

    expect(detail.title).toBe("OA关联明细");
    expect(detail.detailAvailable).toBe(false);
    expect(detail.unavailableReason).toBe("进项发票使用情况关联明细暂不可用。");
    expect(detail.sections).toEqual([]);
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
          nextAction: "create_oa_draft",
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
      filters: [],
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
    expect(preview.targetApplicants).toEqual([{ code: "chen_xiuyun", name: "陈秀云" }]);
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

  test("OA reverse drawer calls loadPreview after opening and hides rejected invoice reasons to keep the workspace compact", async () => {
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    const createDraftFromSelection = vi.fn();

    render(
      <OaReverseWorkspaceDrawer
        open
        sourceFilters={[{ field: "payment_status", operator: "in", values: ["pending"] }]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        onClose={() => undefined}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "正在加载反提 OA 预览" })).toBeInTheDocument();
    expect(screen.queryByText("候选数、合计、拒绝原因和目标申请人均以后端返回为准")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(loadPreview).toHaveBeenCalledWith({
        sourceFilters: [{ field: "payment_status", operator: "in", values: ["pending"] }],
        selectedInvoiceIds: ["inv-001", "inv-002"],
        targetApplicantCode: null,
      });
    });
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("99.72").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("陈秀云").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("chen_xiuyun")).toBeInTheDocument();
    expect(screen.queryByText("不可提交原因")).not.toBeInTheDocument();
    expect(screen.queryByText("缺少目标 OA 账号")).not.toBeInTheDocument();
    expect(screen.queryByText("create_batch")).not.toBeInTheDocument();
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("昆明供应商一")).toBeInTheDocument();
    expect(screen.getByText("2026-05-02")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建本地批次" })).not.toBeInTheDocument();
    expect(screen.queryByText("尚未创建本地批次。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建 OA 草稿" })).toBeDisabled();
  });

  test("OA reverse drawer creates OA draft directly and records submitted confirmation", async () => {
    const user = userEvent.setup();
    const initialPreview: OaReversePreviewPayload = {
      ...previewPayload,
      canCreateDraft: true,
      nextAction: "create_oa_draft",
      permissions: { canCreateDraft: true },
    };
    const refreshedPreview: OaReversePreviewPayload = {
      ...initialPreview,
      previewId: "oa_reverse_preview_subset_001",
      previewHash: "preview-hash-subset-001",
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
      canRefreshStatus: false,
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
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        manualStatus={manualStatus}
        loadSubmittedHistory={loadSubmittedHistory}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("checkbox", { name: "选择候选发票 SD-INV-002" }));
    expect(screen.queryByRole("button", { name: "创建本地批次" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith({
      sourceFilters: [],
      selectedInvoiceIds: ["inv-001"],
      targetApplicantCode: "chen_xiuyun",
    }));
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

  test("OA reverse draft confirmation stays open across parent rerenders until the user decides", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve({
      ...previewPayload,
      canCreateDraft: true,
      nextAction: "create_oa_draft",
      permissions: { canCreateDraft: true },
    }));
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
      sourceFilters: [] as unknown[],
      loadPreview,
      createDraftFromSelection,
      manualStatus: vi.fn(),
      onClose: () => undefined,
    };
    const { rerender } = render(
      <OaReverseWorkspaceDrawer
        {...props}
        selectedInvoiceIds={[]}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "创建 OA 草稿" }));
    expect(await screen.findByRole("dialog", { name: "OA 草稿提交确认" })).toBeInTheDocument();

    rerender(
      <OaReverseWorkspaceDrawer
        {...props}
        selectedInvoiceIds={[]}
      />,
    );

    await waitFor(() => expect(loadPreview).toHaveBeenCalledTimes(2));
    const confirmDialog = screen.getByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ })).toBeInTheDocument();
    expect(within(confirmDialog).getByRole("button", { name: /OA提交内容需修改\s+删除本次提交内容/ })).toBeInTheDocument();

    rerender(
      <OaReverseWorkspaceDrawer
        {...props}
        sourceFilters={[{ field: "payment_status", operator: "equals", value: "pending" }]}
        selectedInvoiceIds={[]}
      />,
    );

    await waitFor(() => expect(loadPreview).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("dialog", { name: "OA 草稿提交确认" })).toBeInTheDocument();
  });

  test("OA reverse staged tab recovers a draft after closing confirmation without exposing draft link", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve({ ...previewPayload, canCreateDraft: true, permissions: { canCreateDraft: true } }));
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
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001"]}
        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        loadStagedDrafts={loadStagedDrafts}
        manualStatus={manualStatus}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "创建 OA 草稿" }));
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

  test("OA reverse drawer marks linked OA invoices as disabled and filters by OA relation status", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve({
      ...previewPayload,
      canCreateDraft: true,
      nextAction: "create_oa_draft",
      permissions: { canCreateDraft: true },
      groups: [{
        ...previewPayload.groups[0],
        invoiceCount: 1,
        totalWithTax: "49.86",
        invoiceRows: previewPayload.groups[0].invoiceRows?.filter((invoice) => invoice.invoiceId === "inv-001"),
        candidateInvoiceIds: ["inv-001"],
        rejectedInvoices: [{
          invoiceId: "inv-linked-oa",
          invoiceNumber: "SD-INV-LINKED",
          sellerName: "已关联供应商",
          issueDate: "2026-05-03",
          totalWithTax: "68.00",
          paymentStatusLabel: "待处理",
          reasonCode: "already_has_active_oa",
          reason: "发票已有 active OA 关系",
          oaRelationStatus: "linked",
        }, {
          invoiceId: "inv-candidate-oa",
          invoiceNumber: "SD-INV-CANDIDATE",
          sellerName: "候选供应商",
          issueDate: "2026-05-04",
          totalWithTax: "109.00",
          paymentStatusLabel: "待处理",
          reasonCode: "already_has_candidate_oa",
          reason: "发票已有待确认 OA 候选关系",
          oaRelationStatus: "candidate",
        }],
      }],
    }));

    render(
      <OaReverseWorkspaceDrawer
        open
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001", "inv-linked-oa"]}
        loadPreview={loadPreview}
        createDraftFromSelection={vi.fn()}
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("SD-INV-LINKED")).toBeInTheDocument();
    expect(screen.getByText("SD-INV-CANDIDATE")).toBeInTheDocument();
    expect(screen.getByText("未关联oa")).toBeInTheDocument();
    expect(screen.getByText("已关联oa")).toBeInTheDocument();
    expect(screen.getByText("候选oa")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "已关联 OA 发票 SD-INV-LINKED 不可选择" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "候选 OA 发票 SD-INV-CANDIDATE 不可选择" })).toBeDisabled();
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "选择候选发票 SD-INV-001" })).toBeChecked();
      expect(screen.getByText((_content, node) => node?.textContent === "已选 1 张")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "筛选 OA 关联状态" }));
    await user.click(screen.getByRole("menuitemradio", { name: "已经关联oa" }));
    expect(screen.queryByText("SD-INV-001")).not.toBeInTheDocument();
    expect(screen.getByText("SD-INV-LINKED")).toBeInTheDocument();
    expect(screen.queryByText("SD-INV-CANDIDATE")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "筛选 OA 关联状态" }));
    await user.click(screen.getByRole("menuitemradio", { name: "候选oa" }));
    expect(screen.queryByText("SD-INV-001")).not.toBeInTheDocument();
    expect(screen.queryByText("SD-INV-LINKED")).not.toBeInTheDocument();
    expect(screen.getByText("SD-INV-CANDIDATE")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "筛选 OA 关联状态" }));
    await user.click(screen.getByRole("menuitemradio", { name: "未关联oa" }));
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.queryByText("SD-INV-LINKED")).not.toBeInTheDocument();
    expect(screen.queryByText("SD-INV-CANDIDATE")).not.toBeInTheDocument();
  });

  test("OA reverse drawer lets the backend target applicant list drive preview and batch target", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn((request) => Promise.resolve({
      ...previewPayload,
      targetApplicantCode: request.targetApplicantCode || "chen_xiuyun",
      targetApplicantName: request.targetApplicantCode === "zhou_jieying" ? "周洁莹" : "陈秀云",
      groups: [{
        ...previewPayload.groups[0],
        targetApplicantCode: request.targetApplicantCode || "chen_xiuyun",
        targetApplicantName: request.targetApplicantCode === "zhou_jieying" ? "周洁莹" : "陈秀云",
      }],
      canCreateDraft: true,
      permissions: { canCreateDraft: true },
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
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        onClose={() => undefined}
      />,
    );

    const selector = await screen.findByLabelText("目标 OA 申请人");
    await user.click(selector);
    await user.click(await screen.findByRole("option", { name: "周洁莹" }));

    await waitFor(() => expect(loadPreview).toHaveBeenLastCalledWith(expect.objectContaining({
      targetApplicantCode: "zhou_jieying",
    })));
    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(createDraftFromSelection).toHaveBeenCalledWith(expect.objectContaining({
      targetApplicantCode: "zhou_jieying",
    })));
  });

  test("OA reverse not-submitted confirmation returns to create state without visible rollback history", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve({ ...previewPayload, canCreateDraft: true, permissions: { canCreateDraft: true } }));
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
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001"]}
        loadPreview={loadPreview}
        createDraftFromSelection={createDraftFromSelection}
        manualStatus={manualStatus}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "创建 OA 草稿" }));
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
    const loadPreview = vi.fn(() => Promise.resolve({ ...previewPayload, canCreateDraft: true, permissions: { canCreateDraft: true } }));
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
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        loadSubmittedHistory={loadSubmittedHistory}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("tab", { name: "已提交" }));

    expect(await screen.findByText("陈秀云")).toBeInTheDocument();
    expect(screen.getByText("99.72")).toBeInTheDocument();
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("昆明供应商二")).toBeInTheDocument();
    expect(screen.queryByText("batch-hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("draft-hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("submitted_confirmed")).not.toBeInTheDocument();
    expect(screen.queryByText("previewHash")).not.toBeInTheDocument();
  });

  test("payment status rules drawer loads Sheet4 rules as read-only content without editable controls or save state", async () => {
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      version: "sheet4-v1",
      readOnly: true,
      permissions: { canSave: false },
      rules: [
        {
          id: "waiting_payment",
          label: "待付款（自动识别有oa无流水）",
          description: "有发票、有 OA、无流水",
          reason: "有发票、有 OA、无流水",
          priority: 6,
          enabled: true,
          conditions: { hasOa: true, hasBank: false },
        },
        {
          id: "paid_full_match",
          label: "已付款（自动识别有oa有流水）",
          description: "有发票、有 OA、有流水，并且关联台完全匹配",
          reason: "有发票、有 OA、有流水，并且关联台完全匹配",
          priority: 2,
          enabled: true,
          conditions: { hasOa: true, hasBank: true, fullyMatched: true },
        },
      ],
      pendingDirections: [
        { code: "pending", label: "待处理" },
        { code: "wei_dailian_batch_reverse", label: "韦代连批量反提oa" },
        { code: "chen_xiuyun_batch_reverse", label: "陈秀云批量反提oa" },
      ],
    }));

    render(<PaymentStatusRulesDrawer open loadRules={loadRules} onClose={() => undefined} />);

    await waitFor(() => expect(loadRules).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("待付款（自动识别有oa无流水）")).toBeInTheDocument();
    expect(screen.getByText("有发票、有 OA、无流水")).toBeInTheDocument();
    expect(screen.getAllByText("有 OA").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("无流水")).toBeInTheDocument();
    expect(screen.getByText("陈秀云批量反提oa")).toBeInTheDocument();
    expect(screen.getByText("当前仅作为待处理方向标签，不影响自动分流。")).toBeInTheDocument();
    expect(screen.queryByText(/版本\s*\d|sheet4-v1/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /保存|确认保存/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText("保存成功")).not.toBeInTheDocument();
  });

  test("payment status rules drawer only enables edits when backend grants save permission and sends versioned save", async () => {
    const user = userEvent.setup();
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      version: 7,
      readOnly: false,
      permissions: { canSave: true },
      rules: [
        {
          id: "waiting_payment",
          label: "待付款",
          description: "有发票、有 OA、无流水",
          reason: "有发票、有 OA、无流水",
          priority: 6,
          enabled: true,
          conditions: { hasOa: true, hasBank: false },
        },
      ],
      pendingDirections: [{ code: "pending", label: "待处理" }],
    }));
    const saveRules = vi.fn(() => Promise.resolve({
      version: 8,
      readOnly: false,
      permissions: { canSave: true },
      rules: [
        {
          id: "waiting_payment",
          label: "待付款",
          description: "已更新规则",
          reason: "已更新规则",
          priority: 6,
          enabled: true,
          conditions: { hasOa: true, hasBank: false },
        },
      ],
      pendingDirections: [{ code: "pending", label: "待处理" }],
    }));

    render(<PaymentStatusRulesDrawer open loadRules={loadRules} saveRules={saveRules} onClose={() => undefined} />);

    expect(screen.queryByText(/版本\s*7/)).not.toBeInTheDocument();
    const ruleEditor = await screen.findByLabelText("原因文案");
    await user.clear(ruleEditor);
    await user.type(ruleEditor, "已更新规则");
    await user.click(screen.getByRole("button", { name: "保存并刷新" }));

    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({
      expectedVersion: 7,
      rules: [expect.objectContaining({ description: "已更新规则", reason: "已更新规则", enabled: true })],
    })));
    expect(saveRules.mock.calls[0][0].idempotencyKey).toMatch(/^input-invoice-usage-payment-rules-save:/);
    expect(await screen.findByText("规则已保存，正在刷新进项发票使用情况。")).toBeInTheDocument();
  });

  test("payment status rules drawer handles version conflicts by asking the user to reload", async () => {
    const user = userEvent.setup();
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      version: 7,
      readOnly: false,
      permissions: { canSave: true },
      rules: [{ id: "paid_full_match", label: "已付款", description: "旧规则", priority: 2 }],
      pendingDirections: [],
    }));
    const saveRules = vi.fn(() => Promise.reject({ status: 409, code: "payment_status_rules_version_conflict" }));

    render(<PaymentStatusRulesDrawer open loadRules={loadRules} saveRules={saveRules} onClose={() => undefined} />);

    const ruleEditor = await screen.findByLabelText("原因文案");
    await user.clear(ruleEditor);
    await user.type(ruleEditor, "新规则");
    await user.click(screen.getByRole("button", { name: "保存并刷新" }));

    expect(await screen.findByText("规则已被其他人更新，请重新加载后再编辑。")).toBeInTheDocument();
  });

  test("parent state can keep the two workflow drawers mutually exclusive", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));
    const loadRules = vi.fn<[], Promise<PaymentStatusRulesPayload>>(() => Promise.resolve({
      rules: [],
      pendingDirections: [{ code: "pending", label: "待处理" }],
    }));

    function Harness() {
      const [activeWorkflow, setActiveWorkflow] = useState<"oaReverse" | "paymentRules" | null>(null);
      return (
        <>
          <button type="button" onClick={() => setActiveWorkflow("oaReverse")}>以发票反提 OA</button>
          <button type="button" onClick={() => setActiveWorkflow("paymentRules")}>发票与支付状态规则设置</button>
          <OaReverseWorkspaceDrawer
            open={activeWorkflow === "oaReverse"}
            sourceFilters={[]}
            selectedInvoiceIds={[]}
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
      pendingDirections: [],
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
            sourceFilters={[]}
            selectedInvoiceIds={[]}
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
    await screen.findByLabelText("以发票反提 OA 工作流");
    await user.click(screen.getByRole("button", { name: "关闭以发票反提 OA 工作流" }));
    await user.click(screen.getByRole("button", { name: "发票与支付状态规则设置" }));
    await screen.findByLabelText("发票与支付状态规则设置");

    await act(async () => undefined);
    expect(loadRows).not.toHaveBeenCalled();
  });
});
