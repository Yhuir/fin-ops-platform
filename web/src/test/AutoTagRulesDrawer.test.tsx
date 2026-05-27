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
    expect(within(drawer).getAllByDisplayValue(label).length).toBeGreaterThan(0);
  });
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
    await waitForLoadedRule(drawer, "手续费");

    await user.click(within(drawer).getByRole("button", { name: "停用" }));
    expect(await within(drawer).findByText("旧奖金")).toBeInTheDocument();
  });

  test("uses a structured rule layout with separate summary and editor areas", async () => {
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");

    const feeHeading = within(drawer).getByRole("heading", { name: "手续费" });
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
    await waitForLoadedRule(drawer, "手续费");

    expect(within(drawer).getByLabelText("适用方向")).toBeInTheDocument();
    expect(within(drawer).getByLabelText("适用账户范围")).toBeInTheDocument();
    expect(within(drawer).getByLabelText("必须同时包含", { selector: "textarea" })).toBeInTheDocument();
    expect(within(drawer).getByLabelText("不包含字样", { selector: "textarea" })).toBeInTheDocument();
    expect(within(drawer).getByLabelText("正则命中", { selector: "textarea" })).toBeInTheDocument();
    expect(within(drawer).queryByText("stop_on_match")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("review_required")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("route_to")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("规则ID")).not.toBeInTheDocument();
  });

  test("serializes direction, account scope, combined conditions, and regex conditions", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const labelInputs = within(drawer).getAllByLabelText("标签名称", { selector: "input" });
    await user.type(labelInputs[labelInputs.length - 1], "外部往来候选");
    const containsInputs = within(drawer).getAllByLabelText("包含任一", { selector: "textarea" });
    await user.type(containsInputs[containsInputs.length - 1], "借据号");
    const allInputs = within(drawer).getAllByLabelText("必须同时包含", { selector: "textarea" });
    await user.type(allInputs[allInputs.length - 1], "还款");
    const regexInputs = within(drawer).getAllByLabelText("正则命中", { selector: "textarea" });
    await user.click(regexInputs[regexInputs.length - 1]);
    await user.paste("借据号[:：]?[A-Z0-9]+");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
        direction: "any",
        account_scope: { type: "any", values: [] },
        rules: expect.objectContaining({
          contains_any: ["借据号"],
          contains_all: ["还款"],
          none_of: [],
          regex_any: ["借据号[:：]?[A-Z0-9]+"],
        }),
      }),
    ]));
  });

  test("keeps Enter-created new lines visible while editing rule keywords", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const labelInputs = within(drawer).getAllByLabelText("标签名称", { selector: "input" });
    await user.type(labelInputs[labelInputs.length - 1], "外部往来候选");
    const containsInputs = within(drawer).getAllByLabelText("包含任一", { selector: "textarea" });
    const textarea = containsInputs[containsInputs.length - 1];
    await user.type(textarea, "借款{Enter}");

    expect(textarea).toHaveValue("借款\n");

    await user.type(textarea, "还款");
    expect(textarea).toHaveValue("借款\n还款");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
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
    expect(source).toMatch(/\.bank-auto-tag-rule-summary\s*\{[^}]*flex-wrap:\s*wrap/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-editor-body\s*\{[^}]*grid-template-columns:\s*minmax\(220px,\s*320px\) minmax\(0,\s*1fr\)/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-grid\s*\{[^}]*grid-template-columns:\s*1fr/s);
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
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    expect(await within(drawer).findByText("优先级 3 的标签名称不能为空。")).toBeInTheDocument();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();
  });

  test("saves edited and newly created rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const onSaved = vi.fn();
    renderDrawer(onSaved);

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const labelInputs = within(drawer).getAllByLabelText("标签名称", { selector: "input" });
    await user.type(labelInputs[labelInputs.length - 1], "银行利息");
    const containsInputs = within(drawer).getAllByLabelText("包含任一", { selector: "textarea" });
    await user.type(containsInputs[containsInputs.length - 1], "利息");
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.expected_version).toBe(1);
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "银行利息" }),
    ]));
  });
});
