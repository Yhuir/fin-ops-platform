import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import OaDraftPrefillDrawer from "../components/common/OaDraftPrefillDrawer";
import { fetchOaDraftPrefill, saveOaDraftPrefill, type OaDraftPrefillPayload } from "../features/oaDraftPrefill";

vi.mock("../features/oaDraftPrefill", async (importOriginal) => {
  const original = await importOriginal<typeof import("../features/oaDraftPrefill")>();
  return { ...original, fetchOaDraftPrefill: vi.fn(), saveOaDraftPrefill: vi.fn() };
});

const payload: OaDraftPrefillPayload = {
  family: "etc",
  version: 3,
  configuration: {
    application_type: "s5",
    payment_method: "Bank_transfer",
    invoice_kind: "Special_invoice",
    project_id: "project-1",
    project_name: "云南溯源科技",
    payee: "刘树刚",
    bank: "建设银行",
    bank_account: "6217003860012460901",
    reason_template: "{statement_month}月账单{payment_date} 支付 ETC批里提交",
  },
  dynamic_fields: {
    applicant: "杨丽萍",
    application_date: "2026-08-05",
    amount: "",
    payee: "",
  },
  options: {
    application_types: [{ value: "s5", label: "车辆使用费（汽油、过路、保险、维修、税费等）" }],
    payment_methods: [{ value: "Bank_transfer", label: "银行转账" }],
    invoice_kinds: [{ value: "Special_invoice", label: "普通发票/行政收据" }],
    projects: [{ value: "project-1", label: "云南溯源科技" }],
  },
  can_save: true,
};

describe("OaDraftPrefillDrawer", () => {
  beforeEach(() => {
    vi.mocked(fetchOaDraftPrefill).mockResolvedValue(payload);
    vi.mocked(saveOaDraftPrefill).mockResolvedValue({ ...payload, version: 4 });
  });

  test("loads the canonical options and saves the edited versioned configuration", async () => {
    const user = userEvent.setup();
    render(<OaDraftPrefillDrawer family="etc" open onClose={vi.fn()} />);

    const drawer = await screen.findByRole("dialog", { name: "OA 草稿预填管理" });
    expect(within(drawer).getByDisplayValue("杨丽萍")).toBeDisabled();
    expect(within(drawer).getByDisplayValue("2026-08-05")).toBeDisabled();
    await user.click(within(drawer).getByLabelText("支付方式"));
    expect(await screen.findByRole("option", { name: "银行转账" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "银行转账" }));

    const bank = within(drawer).getByLabelText("开户行");
    await user.clear(bank);
    await user.type(bank, "中国建设银行");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    expect(saveOaDraftPrefill).toHaveBeenCalledWith(
      "etc",
      3,
      expect.objectContaining({ bank: "中国建设银行" }),
    );
    expect(await within(drawer).findByText("已保存。")).toBeInTheDocument();
  });

  test("keeps every configuration control read-only without administrator access", async () => {
    vi.mocked(fetchOaDraftPrefill).mockResolvedValue({ ...payload, can_save: false });
    render(<OaDraftPrefillDrawer family="etc" open onClose={vi.fn()} />);

    const drawer = await screen.findByRole("dialog", { name: "OA 草稿预填管理" });
    expect(within(drawer).getByLabelText("开户行")).toBeDisabled();
    expect(within(drawer).queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
  });
});
