import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

import AutoTagRulesDrawer from "../features/bankDetails/AutoTagRulesDrawer";
import { installMockApiFetch } from "./apiMock";

function renderDrawer(onSaved = vi.fn()) {
  const onClose = vi.fn();
  render(
    <AutoTagRulesDrawer open onClose={onClose} onSaved={onSaved} />,
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
    .find((item) => item.getAttribute("aria-label")?.includes("查询项"));
  if (!(combobox instanceof HTMLElement)) {
    throw new Error("match field combobox not found");
  }
  return combobox;
}

async function findAutoTagRuleSurface(drawer: HTMLElement) {
  const scope = within(drawer);
  const currentTable = scope.queryByRole("table", { name: "自动标签规则表格" });
  if (currentTable) {
    return currentTable;
  }
  const currentGrid = scope.queryByRole("grid", { name: "自动标签规则表格" });
  if (currentGrid) {
    return currentGrid;
  }
  try {
    return await scope.findByRole("table", { name: "自动标签规则表格" }, { timeout: 500 });
  } catch {
    return scope.findByRole("grid", { name: "自动标签规则表格" });
  }
}

function lastEditableRow(drawer: HTMLElement) {
  const emptyPrimaryInput = Array.from(drawer.querySelectorAll('input[placeholder="主标签名称"]'))
    .find((input) => input instanceof HTMLInputElement && input.value === "");
  const row = emptyPrimaryInput?.closest("tr");
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
  test("targets project right drawer and dialog primitives", () => {
    const source = readFileSync(resolve(process.cwd(), "src/features/bankDetails/AutoTagRulesDrawer.tsx"), "utf8");

    expect(source).toContain("AppDrawer");
    expect(source).toContain("AppDialog");
    expect(source).not.toContain("@mui/material/Drawer");
    expect(source).not.toContain("@mui/material/Dialog");
    expect(source).not.toContain("@mui/material/Table");
    expect(source).not.toContain("@mui/material/Select");
    expect(source).not.toContain("@mui/material/TextField");
    expect(source).not.toContain("@mui/icons-material");
  });

  test("loads active rules as a wide table with fixed system priority first", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    const table = await findAutoTagRuleSurface(drawer);

    expect(within(table).getByRole("columnheader", { name: "流水类型" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "主标签" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "不包含字样" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "查询项" })).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "主标签",
      "子标签",
      "流水类型",
      "查询项",
      "包含",
      "必须同时包含",
      "精准命中",
      "不包含字样",
      "优先级",
      "操作",
    ]);
    expect(within(drawer).queryByText("选择查询的项")).not.toBeInTheDocument();
    expect(within(drawer).getByText("内部往来款")).toBeInTheDocument();
    const systemRow = rowForText(drawer, "系统规则");
    expect(systemRow).toHaveTextContent("内部往来款");
    expect(systemRow).toHaveTextContent("1");
    expect(systemRow).not.toHaveTextContent("内部账户成对流水");
    expect(systemRow).not.toHaveTextContent("只读");
    expect(within(drawer).getAllByDisplayValue("费用")).toHaveLength(1);
    expect(within(drawer).getByDisplayValue("手续费")).toBeInTheDocument();
    expect(within(drawer).getByRole("spinbutton", { name: "费用 / 手续费 优先级" })).toHaveValue(10);
    expect(within(drawer).getByRole("spinbutton", { name: "费用 / 工资 优先级" })).toHaveValue(20);
    expect(within(drawer).queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: /上移/ })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: /下移/ })).not.toBeInTheDocument();
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

  test("edits a merged primary label once and saves it to every child rule in the group", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const primaryInput = within(drawer).getByDisplayValue("费用");
    await user.clear(primaryInput);
    await user.type(primaryInput, "支出费用");
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    const activeRules = payload?.active_rules as Array<Record<string, unknown>>;
    expect(activeRules.filter((rule) => rule.code === "fee" || rule.code === "salary")).toEqual([
      expect.objectContaining({ code: "fee", output_primary_label: "支出费用", priority: 10 }),
      expect.objectContaining({ code: "salary", output_primary_label: "支出费用", priority: 20 }),
    ]);
  });

  test("edits ordinary rule priority and submits it with the saved rules", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const feePriority = within(drawer).getByRole("spinbutton", { name: "费用 / 手续费 优先级" });
    await user.clear(feePriority);
    await user.type(feePriority, "3");
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "fee", priority: 3 }),
      expect.objectContaining({ code: "salary", priority: 20 }),
    ]));
  });

  test("shows external turnover third label candidates as read-only and saves only action type", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "借出款");
    const feeRow = rowForDisplayValue(drawer, "手续费");
    expect(within(feeRow).queryByLabelText(/子子标签/)).not.toBeInTheDocument();
    expect(within(feeRow).queryByLabelText(/台账动作类型/)).not.toBeInTheDocument();

    const externalRow = rowForDisplayValue(drawer, "借出款");
    const thirdLabelSelect = within(externalRow).getAllByLabelText(/子子标签/)
      .find((element) => element.getAttribute("role") === "combobox");
    expect(thirdLabelSelect).toBeDefined();
    expect(thirdLabelSelect).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("option", { name: "公司往来" })).not.toBeInTheDocument();
    const actionTypeSelect = within(externalRow).getAllByLabelText(/台账动作类型/)
      .find((element) => element.getAttribute("role") === "combobox");
    expect(actionTypeSelect).toBeDefined();
    await user.click(actionTypeSelect as HTMLElement);
    await user.click(await screen.findByRole("option", { name: "已收款" }));
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: "external_payment",
        output_primary_label: "外部往来款付款",
        output_sub_label: "借出款",
        turnover_action_type: "collected",
      }),
    ]));
    const savedExternalRule = (payload?.active_rules as Array<Record<string, unknown>>)
      .find((rule) => rule.code === "external_payment");
    expect(savedExternalRule).not.toHaveProperty("output_third_label");
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

    await user.click(matchFieldCombobox(editedRow));
    let listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("button", { name: "全选" })).toBeInTheDocument();
    expect(within(listbox).getByRole("button", { name: "清空" })).toBeInTheDocument();
    await user.click(within(listbox).getByRole("button", { name: "清空" }));
    await user.keyboard("{Escape}");
    await user.click(buttonByName(drawer, "保存"));

    expect(await within(drawer).findByText("往来款 至少选择一个匹配字段。")).toBeInTheDocument();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();

    await user.click(matchFieldCombobox(editedRow));
    listbox = await screen.findByRole("listbox");
    expect(within(listbox).queryByRole("option", { name: /全部文本/ })).not.toBeInTheDocument();
    await user.click(within(listbox).getByRole("button", { name: "全选" }));
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
    expect(within(drawer).getByText("借据号")).toBeInTheDocument();
    expect(within(drawer).queryByText(/共 \d+ 项/)).not.toBeInTheDocument();
    await user.click(buttonByName(drawer, "保存"));

    const payload = requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT");
    expect(payload?.active_rules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: "外部往来候选",
        output_primary_label: "往来款",
        output_sub_label: "外部往来候选",
        direction: "expense",
        priority: 2,
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

    expect(await within(drawer).findByText(/第 \d+ 条规则的主标签名称不能为空。/)).toBeInTheDocument();
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
        priority: 2,
        output_primary_label: "收入",
        output_sub_label: "银行利息",
        account_scope: { type: "any", values: [] },
        rules: expect.objectContaining({ regex_any: [] }),
      }),
    ]));
  });

  test("reapplies saved rules without submitting a rule update", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch();
    const onSaved = vi.fn();
    renderDrawer(onSaved);

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const reapplyButton = buttonByName(drawer, "重新应用规则");
    const saveButton = buttonByName(drawer, "保存");
    expect(Boolean(reapplyButton.compareDocumentPosition(saveButton) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);

    await user.click(reapplyButton);

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(within(drawer).getByText("已提交重新应用，银行明细正在刷新。")).toBeInTheDocument();
    const reapplyCall = fetchMock.mock.calls.find(([input, init]) => (
      new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost").pathname === "/api/bank-details/auto-tag-rules/reapply"
      && String(init?.method || "GET").toUpperCase() === "POST"
    ));
    expect(reapplyCall).toBeTruthy();
    expect(requestPayload(fetchMock, "/api/bank-details/auto-tag-rules", "PUT")).toBeNull();
  });

  test("requires saving draft changes before reapplying rules", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderDrawer();

    const drawer = await screen.findByRole("dialog", { name: "自动标签规则" });
    await waitForLoadedRule(drawer, "手续费");
    const primaryInput = within(drawer).getByDisplayValue("费用");
    await user.clear(primaryInput);
    await user.type(primaryInput, "支出费用");

    expect(buttonByName(drawer, "重新应用规则")).toBeDisabled();
  });

  test("keeps automatic tag rule drawer styling table-based and non-truncating", () => {
    const source = readFileSync(resolve(process.cwd(), "src/app/styles.css"), "utf8");

    expect(source).toMatch(/\.bank-auto-tag-drawer-paper\s*\{[^}]*width:\s*80vw/s);
    expect(source).toMatch(/\.bank-auto-tag-table-container\s*\{[^}]*overflow-x:\s*hidden/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-table\s*\{[^}]*table-layout:\s*fixed/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-table\s*\{[^}]*width:\s*100%/s);
    expect(source).toMatch(/\.bank-auto-tag-rule-table\s+\.finance-table__cell\s*\{[^}]*white-space:\s*normal/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-field-button\s*\{[^}]*min-height:\s*30px/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-field-button\s*\{[^}]*background:\s*transparent/s);
    expect(source).not.toMatch(/\.bank-auto-tag-rule-row\s+\.MuiInput-root::before/s);
    expect(source).toMatch(/\.bank-auto-tag-condition-preview\s*\{[^}]*white-space:\s*normal/s);
    expect(source).not.toMatch(/bank-auto-tag-primary-cell[\s\S]{0,160}border-right/s);
    expect(source).not.toMatch(/bank-auto-tag-priority-cell[\s\S]{0,160}border-right/s);
    expect(source).toMatch(/\.bank-auto-tag-priority-value\s*\{/);
    expect(source).toMatch(/\.bank-auto-tag-field-menu-actions\s*\{/);
  });
});
