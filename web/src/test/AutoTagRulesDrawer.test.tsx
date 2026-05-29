import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import AutoTagRulesDrawer, { reorderRulesById } from "../features/bankDetails/AutoTagRulesDrawer";
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
    expect(within(drawer).getByDisplayValue(label)).toBeInTheDocument();
  });
}

function rowForText(drawer: HTMLElement, text: string) {
  const cellContent = within(drawer).getByText(text);
  const row = cellContent.closest("tr");
  if (!(row instanceof HTMLElement)) {
    throw new Error(`row for ${text} not found`);
  }
  return row;
}

function rowForDisplayValue(drawer: HTMLElement, value: string) {
  const input = within(drawer).getByDisplayValue(value);
  const row = input.closest("tr");
  if (!(row instanceof HTMLElement)) {
    throw new Error(`row for ${value} not found`);
  }
  return row;
}

function buttonByName(container: HTMLElement, name: string) {
  const button = Array.from(container.querySelectorAll("button"))
    .find((item) => item.getAttribute("aria-label") === name || item.textContent?.trim() === name);
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`button ${name} not found`);
  }
  return button;
}

function matchFieldCombobox(row: HTMLElement) {
  const combobox = Array.from(row.querySelectorAll('[role="combobox"]'))
    .find((item) => item.getAttribute("aria-labelledby")?.endsWith("-fields-label"));
  if (!(combobox instanceof HTMLElement)) {
    throw new Error("match field combobox not found");
  }
  return combobox;
}

function lastEditableRow(drawer: HTMLElement) {
  const rows = Array.from(drawer.querySelectorAll(".bank-auto-tag-rule-row"));
  const row = rows.at(-1);
  if (!(row instanceof HTMLElement)) {
    throw new Error("rule row not found");
  }
  return row;
}

async function editRuleLabel(user: ReturnType<typeof userEvent.setup>, row: HTMLElement, primary: string, sub: string) {
  const primaryInput = within(row).getByLabelText(/主标签$/, { selector: "input" });
  const subInput = within(row).getByLabelText(/子标签$/, { selector: "input" });
  await user.clear(primaryInput);
  if (primary) {
    await user.type(primaryInput, primary);
  }
  await user.clear(subInput);
  if (sub) {
    await user.type(subInput, sub);
  }
}

async function editCondition(
  user: ReturnType<typeof userEvent.setup>,
  drawer: HTMLElement,
  ruleLabel: string,
  conditionLabel: string,
  value: string,
) {
  await user.click(buttonByName(drawer, `编辑${ruleLabel}${conditionLabel}`));
  const dialog = await screen.findByRole("dialog", { name: conditionLabel });
  const textarea = within(dialog).getByRole("textbox");
  await user.clear(textarea);
  if (value) {
    await user.type(textarea, value);
  }
  await user.click(within(dialog).getByRole("button", { name: "确定" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: conditionLabel })).not.toBeInTheDocument());
  await waitFor(() => expect(drawer).not.toHaveAttribute("aria-hidden", "true"));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AutoTagRulesDrawer", () => {
  test("reorders active rules by ids without mutating the original list", () => {
    const rules = [
      { localId: "fee" },
      { localId: "salary" },
      { localId: "tax" },
    ];

    expect(reorderRulesById(rules, "tax", "fee")).toEqual([
      { localId: "tax" },
      { localId: "fee" },
      { localId: "salary" },
    ]);
    expect(rules).toEqual([
      { localId: "fee" },
      { localId: "salary" },
      { localId: "tax" },
    ]);
    expect(reorderRulesById(rules, "missing", "fee")).toBe(rules);
  });

  test("loads active rules as a wide table with fixed system priority first", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    const table = within(drawer).getByRole("table", { name: "自动标签规则表格" });

    expect(within(table).getByRole("columnheader", { name: "流水类型" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "主标签" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "不包含字样" })).toBeInTheDocument();
    expect(within(drawer).getByText("内部往来款")).toBeInTheDocument();
    expect(rowForText(drawer, "系统规则")).toHaveTextContent("1");
    expect(within(drawer).getAllByDisplayValue("费用").length).toBeGreaterThan(0);
    expect(within(drawer).getByDisplayValue("手续费")).toBeInTheDocument();
    expect(rowForText(drawer, "手续费")).toHaveTextContent("2");
    expect(within(drawer).queryByText("OA中的类型")).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "停用" }));
    expect(await within(drawer).findByText("费用 / 旧奖金")).toBeInTheDocument();
  });

  test("opens a confirmation dialog before archiving an active rule", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");

    await user.click(within(drawer).getByRole("button", { name: "停用 费用 / 手续费" }));
    const dialog = await screen.findByRole("dialog", { name: "确认停用标签" });
    expect(within(dialog).getByText("确定停用「费用 / 手续费」吗？")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "确认停用标签" })).not.toBeInTheDocument());
    expect(within(drawer).getByDisplayValue("手续费")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "停用 费用 / 手续费" }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认停用标签" })).getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "确认停用标签" })).not.toBeInTheDocument());
    expect(within(drawer).queryByDisplayValue("手续费")).not.toBeInTheDocument();
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.archived_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "fee", label: "手续费" }),
    ]));
  });

  test("manages match fields with select all and clear actions without showing all text as an option", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const feeRow = rowForText(drawer, "手续费");
    await editRuleLabel(user, feeRow, "往来款", "外部往来候选");
    await editCondition(user, drawer, "往来款 / 外部往来候选", "包含", "借据号");
    const editedRow = rowForDisplayValue(drawer, "外部往来候选");

    await user.click(buttonByName(editedRow, "清空"));
    await user.click(buttonByName(drawer, "保存"));

    expect(await within(drawer).findByText("往来款 至少选择一个匹配字段。")).toBeInTheDocument();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();

    await user.click(buttonByName(editedRow, "全选"));
    await user.click(matchFieldCombobox(editedRow));
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).queryByRole("option", { name: /全部文本/ })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
        rules: expect.objectContaining({
          match_fields: [
            "counterparty_name",
            "purpose_text",
            "summary_text",
            "note_text",
            "detail_text",
          ],
        }),
      }),
    ]));
  });

  test("edits labels and multiline condition cells in the table", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const row = lastEditableRow(drawer);
    await editRuleLabel(user, row, "往来款", "外部往来候选");
    const editedRow = rowForDisplayValue(drawer, "外部往来候选");
    await user.click(within(editedRow).getByText("不限"));
    await user.click(await screen.findByRole("option", { name: "支出" }));
    await editCondition(user, drawer, "往来款 / 外部往来候选", "包含", "借据号");
    await editCondition(user, drawer, "往来款 / 外部往来候选", "必须同时包含", "还款");
    await user.click(buttonByName(drawer, "保存"));

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

  test("validates active rules before save", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));
    await user.click(buttonByName(drawer, "保存"));

    expect(await within(drawer).findByText("优先级 4 的主标签名称不能为空。")).toBeInTheDocument();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();
    expect(within(drawer).queryByText(/正则命中/)).not.toBeInTheDocument();
  });

  test("discards unsaved draft rules instead of submitting them as archived rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const firstRow = rowForText(drawer, "手续费");
    await editRuleLabel(user, firstRow, "费用", "手续费调整");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    await user.click(within(drawer).getByRole("button", { name: "停用 未命名标签" }));
    await user.click(within(await screen.findByRole("dialog", { name: "确认停用标签" })).getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "确认停用标签" })).not.toBeInTheDocument());
    await user.click(buttonByName(drawer, "保存"));

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
    await waitForLoadedRule(drawer, "手续费");
    await user.click(within(drawer).getByRole("button", { name: "新增标签" }));

    const row = lastEditableRow(drawer);
    await editRuleLabel(user, row, "收入", "银行利息");
    await editCondition(user, drawer, "收入 / 银行利息", "包含", "利息");
    await user.click(buttonByName(drawer, "保存"));

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

  test("keeps automatic tag rule drawer styling table-based and non-truncating", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-auto-tag-drawer-paper\s*\{[^}]*width:\s*min\(1280px,\s*92vw\)/s);
    expect(source).toMatch(/\.bank-auto-tag-table-container\s*\{[^}]*overflow-x:\s*hidden/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-table\s*\{[^}]*table-layout:\s*fixed/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-table\s+\.MuiTableCell-root\s*\{[^}]*white-space:\s*normal/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-summary\.MuiButton-root\s*\{[^}]*min-height:\s*36px/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-preview\s*\{[^}]*white-space:\s*normal/s);
  });
});
