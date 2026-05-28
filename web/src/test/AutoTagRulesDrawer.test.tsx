import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import AutoTagRulesDrawer from "../features/bankDetails/AutoTagRulesDrawer";
import { installMockApiFetch } from "./apiMock";

function renderDrawer(onSaved = vi.fn()) {
  const onClose = vi.fn();
  render(
    <MuiProviders>
      <AutoTagRulesDrawer open onClose={onClose} onSaved={onSaved} />
    </MuiProviders>,
  );
  return { onClose, onSaved };
}

function requestPayload(fetchMock: ReturnType<typeof installMockApiFetch>, pathname: string, method: string) {
  const call = fetchMock.mock.calls.find(([input, init]) => (
    new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === pathname
    && String(init?.method || "GET").toUpperCase() === method
  ));
  if (!call) {
    return null;
  }
  return JSON.parse(String(call[1]?.body || "{}")) as Record<string, unknown>;
}

async function waitForLoadedRule(drawer: HTMLElement, label: string) {
  await waitFor(() => {
    expect(within(drawer).getByRole("heading", { name: label })).toBeInTheDocument();
  });
}

function lastRuleCard(drawer: HTMLElement) {
  const cards = drawer.querySelectorAll(".bank-auto-tag-rule-card");
  const card = cards[cards.length - 1];
  if (!(card instanceof HTMLElement)) {
    throw new Error("rule card not found");
  }
  return card;
}

async function editRuleLabel(user: ReturnType<typeof userEvent.setup>, card: HTMLElement, primary: string, sub: string) {
  await user.click(within(card).getByRole("button", { name: /^编辑标签/ }));
  const primaryInput = within(card).getByLabelText("主标签名称", { selector: "input" });
  const subInput = within(card).getByLabelText("子标签名称", { selector: "input" });
  await user.clear(primaryInput);
  await user.type(primaryInput, primary);
  await user.clear(subInput);
  if (sub) {
    await user.type(subInput, sub);
  }
  await user.keyboard("{Enter}");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AutoTagRulesDrawer", () => {
  test("loads system, active, and archived rule areas", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });

    expect(within(drawer).getByText("优先级 0")).toBeInTheDocument();
    expect(within(drawer).getByText("内部往来款")).toBeInTheDocument();
    expect(within(drawer).getByText("优先级 1")).toBeInTheDocument();
    await waitForLoadedRule(drawer, "费用 / 手续费");
    expect(within(drawer).queryByLabelText("标签名称", { selector: "input" })).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "停用" }));
    expect(await within(drawer).findByText("费用 / 旧奖金")).toBeInTheDocument();
  });

  test("uses a structured rule layout with separate summary and editor areas", async () => {
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");

    const feeHeading = within(drawer).getByRole("heading", { name: "费用 / 手续费" });
    const feeCard = feeHeading.closest(".bank-auto-tag-rule-card");
    expect(feeCard).not.toBeNull();
    expect(feeCard?.querySelector(".bank-auto-tag-rule-summary")).toHaveTextContent("字段");
    expect(feeCard?.querySelector(".bank-auto-tag-rule-summary")).toHaveTextContent("包含");
    expect(feeCard?.querySelector(".bank-auto-tag-rule-editor-body")).toBeInTheDocument();
    expect(feeCard?.querySelector(".bank-auto-tag-condition-grid")).toBeInTheDocument();
  });

  test("shows production rule controls without exposing hidden system fields", async () => {
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");

    expect(within(drawer).queryByLabelText("适用方向")).not.toBeInTheDocument();
    expect(within(drawer).queryByLabelText("适用账户范围")).not.toBeInTheDocument();
    expect(within(drawer).queryByLabelText("账户范围值")).not.toBeInTheDocument();
    expect(within(drawer).queryByLabelText("主标签名称", { selector: "input" })).not.toBeInTheDocument();
    expect(within(drawer).queryByLabelText("子标签名称", { selector: "input" })).not.toBeInTheDocument();
    expect(within(drawer).getByLabelText("必须同时包含", { selector: "textarea" })).toBeInTheDocument();
    expect(within(drawer).getByLabelText("不包含字样", { selector: "textarea" })).toBeInTheDocument();
    expect(within(drawer).queryByLabelText("正则命中", { selector: "textarea" })).not.toBeInTheDocument();
    expect(within(drawer).queryByText("不限账户时无需填写")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("一行一个完整匹配文本")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("任意一行命中即可")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("stop_on_match")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("review_required")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("route_to")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("规则ID")).not.toBeInTheDocument();
  });

  test("edits labels inline, toggles direction, and normalizes hidden account and regex fields", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const card = lastRuleCard(drawer);
    await editRuleLabel(user, card, "往来款", "外部往来候选");
    await user.click(within(card).getByRole("button", { name: "支出" }));
    await user.type(within(card).getByLabelText("包含任一", { selector: "textarea" }), "借据号");
    await user.type(within(card).getByLabelText("必须同时包含", { selector: "textarea" }), "还款");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
        output_primary_label: "往来款",
        output_sub_label: "外部往来候选",
        direction: "expense",
        account_scope: { type: "any", values: [] },
        rules: expect.objectContaining({
          contains_any: ["借据号"],
          contains_all: ["还款"],
          none_of: [],
          regex_any: [],
        }),
      }),
    ]));
  });

  test("keeps Enter-created new lines visible while editing rule keywords", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const card = lastRuleCard(drawer);
    await editRuleLabel(user, card, "往来款", "外部往来候选");
    const textarea = within(card).getByLabelText("包含任一", { selector: "textarea" });
    await user.type(textarea, "借款{Enter}");

    expect(textarea).toHaveValue("借款\n");

    await user.type(textarea, "还款");
    expect(textarea).toHaveValue("借款\n还款");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
        output_primary_label: "往来款",
        output_sub_label: "外部往来候选",
        rules: expect.objectContaining({
          contains_any: ["借款", "还款"],
        }),
      }),
    ]));
  });

  test("keeps automatic tag rule drawer styling simple and non-truncating", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-auto-tag-rule-card\s*\{[^}]*border:\s*1px solid var\(--bank-border-subtle\)/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-card\s*\{[^}]*overflow:\s*visible/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-card\.expanded\s*\{[^}]*border-color:\s*#8bb7f0/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-summary\s*\{[^}]*flex-wrap:\s*wrap/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-editor-body\s*\{[^}]*grid-template-columns:\s*minmax\(240px,\s*360px\) minmax\(0,\s*1fr\)/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-grid\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/s);
    expect(source).toMatch(/@media \(max-width:\s*1200px\)[\s\S]*\.bank-auto-tag-condition-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s);
    expect(source).toMatch(/@media \(max-width:\s*720px\)[\s\S]*\.bank-auto-tag-condition-grid\s*\{[^}]*grid-template-columns:\s*1fr/s);
  });

  test("does not use animated height measurement for expanded rule editors", () => {
    const source = readFileSync(resolve(process.cwd(), "src/features/bankDetails/AutoTagRulesDrawer.tsx"), "utf8");

    expect(source).not.toContain("@mui/material/Collapse");
    expect(source).not.toContain("<Collapse");
  });

  test("validates active rules before save", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    expect(await within(drawer).findByText("优先级 3 的主标签名称不能为空。")).toBeInTheDocument();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();
    expect(within(drawer).queryByText(/正则命中/)).not.toBeInTheDocument();
  });

  test("discards unsaved draft rules instead of submitting them as archived rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");
    const firstCard = drawer.querySelector(".bank-auto-tag-rule-card");
    if (!(firstCard instanceof HTMLElement)) {
      throw new Error("rule card not found");
    }
    await editRuleLabel(user, firstCard, "费用", "手续费调整");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    await user.click(within(drawer).getByRole("button", { name: "未命名标签 停用" }));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.archived_rules).toEqual([
      expect.objectContaining({ code: "old_bonus", label: "旧奖金" }),
    ]);
    expect(payload?.archived_rules).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ output_primary_label: "" }),
    ]));
  });

  test("saves edited and newly created rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const onSaved = vi.fn();
    renderDrawer(onSaved);

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "费用 / 手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const card = lastRuleCard(drawer);
    await editRuleLabel(user, card, "收入", "银行利息");
    await user.type(within(card).getByLabelText("包含任一", { selector: "textarea" }), "利息");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.expected_version).toBe(1);
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "银行利息",
        output_primary_label: "收入",
        output_sub_label: "银行利息",
        account_scope: { type: "any", values: [] },
        rules: expect.objectContaining({ regex_any: [] }),
      }),
    ]));
  });
});
