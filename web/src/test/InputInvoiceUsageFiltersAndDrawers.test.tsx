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

afterEach(() => {
  vi.restoreAllMocks();
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
    expect(await screen.findByText("OA详情不可用")).toBeInTheDocument();
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
  const previewPayload: OaReversePreviewPayload = {
    previewId: "oa_reverse_preview_001",
    previewHash: "preview-hash-001",
    source: "explicitSelection",
    invoiceCount: 2,
    totalWithTax: "99.72",
    groups: [
      {
        targetApplicantCode: "chen_xiuyun",
        targetApplicantName: "陈秀云",
        invoiceCount: 2,
        totalWithTax: "99.72",
        candidateInvoiceIds: ["inv-001", "inv-002"],
        candidateInvoices: [
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
        rejectedInvoices: [
          { invoiceId: "inv-reject-001", reasonCode: "missing_target_account", reason: "缺少目标 OA 账号" },
        ],
      },
    ],
    warnings: [],
    canCreateDraft: false,
    nextAction: "future_contract_only",
  };

  test("OA reverse drawer calls loadPreview after opening and only displays backend-provided totals/groups/rejections", async () => {
    const loadPreview = vi.fn(() => Promise.resolve(previewPayload));

    render(
      <OaReverseWorkspaceDrawer
        open
        sourceFilters={[{ field: "payment_status", operator: "in", values: ["pending"] }]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        onClose={() => undefined}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "正在加载反提 OA 预览" })).toBeInTheDocument();

    await waitFor(() => {
      expect(loadPreview).toHaveBeenCalledWith({
        sourceFilters: [{ field: "payment_status", operator: "in", values: ["pending"] }],
        selectedInvoiceIds: ["inv-001", "inv-002"],
      });
    });
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("99.72").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("陈秀云")).toBeInTheDocument();
    expect(screen.getByText("chen_xiuyun")).toBeInTheDocument();
    expect(screen.getByText("缺少目标 OA 账号")).toBeInTheDocument();
    expect(screen.getByText("SD-INV-001")).toBeInTheDocument();
    expect(screen.getByText("昆明供应商一")).toBeInTheDocument();
    expect(screen.getByText("2026-05-02")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /创建.*草稿|提交|保存/ })).not.toBeInTheDocument();
  });

  test("OA reverse drawer runs preview to batch to draft without fabricating unavailable draft success", async () => {
    const user = userEvent.setup();
    const loadPreview = vi.fn(() => Promise.resolve({
      ...previewPayload,
      canCreateDraft: true,
      nextAction: "create_batch",
      permissions: { canCreateBatch: true, canCreateDraft: true },
    }));
    const createBatch = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_001",
      version: 3,
      status: "previewed",
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      canCreateDraft: true,
    }));
    const createDraft = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_001",
      version: 4,
      status: "oa_submission_detecting",
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-001",
      oaDetectionStatus: "detecting",
      canRefreshStatus: true,
    }));
    const refreshStatus = vi.fn(() => Promise.resolve({
      batchId: "oa_reverse_batch_001",
      version: 5,
      status: "oa_submitted",
      selectedInvoiceIds: ["inv-001", "inv-002"],
      totalWithTax: "99.72",
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      invoices: [],
      rejectedInvoices: [],
      oaDraftId: "oa-draft-001",
      oaDraftUrl: "https://oa.example.test/draft/oa-draft-001",
      oaDetectionStatus: "submitted",
    }));

    render(
      <OaReverseWorkspaceDrawer
        open
        sourceFilters={[]}
        selectedInvoiceIds={["inv-001", "inv-002"]}
        loadPreview={loadPreview}
        createBatch={createBatch}
        createDraft={createDraft}
        refreshStatus={refreshStatus}
        onClose={() => undefined}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "创建本地批次" }));
    await waitFor(() => expect(createBatch).toHaveBeenCalledWith(expect.objectContaining({
      previewId: "oa_reverse_preview_001",
      expectedPreviewHash: "preview-hash-001",
      selectedInvoiceIds: ["inv-001", "inv-002"],
      targetApplicantCode: "chen_xiuyun",
    })));
    expect(await screen.findByText("oa_reverse_batch_001")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(createDraft).toHaveBeenCalledWith("oa_reverse_batch_001", expect.objectContaining({
      expectedVersion: 3,
    })));
    expect(await screen.findByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute("href", "https://oa.example.test/draft/oa-draft-001");

    await user.click(screen.getByRole("button", { name: "刷新 OA 状态" }));
    await waitFor(() => expect(refreshStatus).toHaveBeenCalledWith("oa_reverse_batch_001", { expectedVersion: 4 }));
    expect(await screen.findByText("OA 状态已刷新。")).toBeInTheDocument();
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
          priority: 6,
        },
        {
          id: "paid_full_match",
          label: "已付款（自动识别有oa有流水）",
          description: "有发票、有 OA、有流水，并且关联台完全匹配",
          priority: 2,
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
    expect(screen.getByText("陈秀云批量反提oa")).toBeInTheDocument();
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
          priority: 6,
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
          priority: 6,
        },
      ],
      pendingDirections: [{ code: "pending", label: "待处理" }],
    }));

    render(<PaymentStatusRulesDrawer open loadRules={loadRules} saveRules={saveRules} onClose={() => undefined} />);

    const ruleEditor = await screen.findByLabelText("规则");
    await user.clear(ruleEditor);
    await user.type(ruleEditor, "已更新规则");
    await user.click(screen.getByRole("button", { name: "保存规则" }));

    await waitFor(() => expect(saveRules).toHaveBeenCalledWith(expect.objectContaining({
      expectedVersion: 7,
      rules: [expect.objectContaining({ description: "已更新规则" })],
    })));
    expect(saveRules.mock.calls[0][0].idempotencyKey).toMatch(/^input-invoice-usage-payment-rules-save:/);
    expect(await screen.findByText("规则已保存，读模型会按后端返回的刷新状态更新。")).toBeInTheDocument();
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

    const ruleEditor = await screen.findByLabelText("规则");
    await user.clear(ruleEditor);
    await user.type(ruleEditor, "新规则");
    await user.click(screen.getByRole("button", { name: "保存规则" }));

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
