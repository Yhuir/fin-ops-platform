import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";

const settingsSourceFiles = [
  "src/pages/SettingsPage.tsx",
  "src/components/settings/SettingsPageContent.tsx",
  "src/components/settings/SettingsTabs.tsx",
  "src/components/settings/SettingsBankAccountsSection.tsx",
  "src/components/settings/SettingsOaRetentionSection.tsx",
  "src/components/settings/SettingsAccessAccountsSection.tsx",
  "src/components/settings/SettingsDataResetSection.tsx",
  "src/components/settings/SettingsDataResetDialogs.tsx",
  "src/components/settings/OaManualSearchImportTable.tsx",
] as const;

function readWebSource(path: string) {
  return readFileSync(resolve(__dirname, "..", path.replace(/^src\//, "")), "utf8");
}

function cssRule(styles: string, selector: string, containing?: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = Array.from(styles.matchAll(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\n\\}`, "gm")));
  const match = containing ? matches.find((candidate) => candidate[1].includes(containing)) : matches.at(-1);
  if (!match) {
    throw new Error(`Missing CSS rule for ${selector}`);
  }
  return match[1];
}

describe("Settings page", () => {
  test("targets project primitives for settings navigation, tables, dialogs, menus, and feedback", () => {
    const sourceByPath = Object.fromEntries(settingsSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = settingsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = settingsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = settingsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /ThemeProvider|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsSectionSx|settingsTokens|DeleteOutlined|KeyboardArrowDownIcon|KeyboardArrowRightIcon|RefreshIcon|UndoIcon|CheckCircleOutlineIcon/.test(source)
        ? [path]
        : [];
    });

    expect(forbiddenMuiImports).toEqual([]);
    expect(forbiddenMuiSelectors).toEqual([]);
    expect(forbiddenLegacySurfaces).toEqual([]);

    const heroUiInteractiveFiles = settingsSourceFiles.filter((path) => (
      path.includes("src/components/settings/") && path !== "src/components/settings/types.ts"
    ));
    expect(heroUiInteractiveFiles.filter((path) => !sourceByPath[path].includes('from "@heroui/react"'))).toEqual([]);
    expect(heroUiInteractiveFiles.filter((path) => /<(?:input|select|textarea|progress)\b/.test(sourceByPath[path]))).toEqual([]);

    const pageSource = sourceByPath["src/pages/SettingsPage.tsx"];
    const contentSource = sourceByPath["src/components/settings/SettingsPageContent.tsx"];
    const dataResetDialogsSource = sourceByPath["src/components/settings/SettingsDataResetDialogs.tsx"];
    const oaManualTableSource = sourceByPath["src/components/settings/OaManualSearchImportTable.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("SettingsPageContent") ? null : "SettingsPage.tsx should keep SettingsPageContent",
      contentSource.includes("SettingsTabs") ? null : "SettingsPageContent.tsx should keep SettingsTabs",
      sourceByPath["src/components/settings/SettingsTabs.tsx"].includes("<Tabs.Panel") ? null : "SettingsTabs must connect tabs and panel",
      /ariaLabel=["']OA全量搜索导入结果["']/.test(oaManualTableSource) ? null : "OA manual search should preserve table accessible name",
      /确认数据重置/.test(dataResetDialogsSource) && /OA 密码复核/.test(dataResetDialogsSource) ? null : "Data reset should keep two modal dialog labels",
      /minLength=\{5\}/.test(dataResetDialogsSource) && /操作原因（必填）/.test(dataResetDialogsSource) ? null : "Data reset should expose its reason requirement",
    ].filter(Boolean);

    expect(missingPrimitiveTargets).toEqual([]);
  });

  test("removes the old settings navigation while preserving shared table semantics", () => {
    const styles = readWebSource("src/components/settings/settings.css");
    expect(styles).not.toMatch(/settings-tree-item|settings-nav-shell|settings-mobile-section-select|settings-section-panel--compact/);
    expect(cssRule(styles, ".settings-table-code,\n.settings-table-input--code,\n.settings-table-amount")).toContain("font-variant-numeric: tabular-nums");
    expect(cssRule(styles, ".oa-manual-import__table")).toContain("min-width: 1500px");
  });

  test("renders as native tabs and a panel without an extra page header title", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.queryByText("管理关联台项目、账户、OA导入与高风险维护配置。")).not.toBeInTheDocument();

    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    expect(screen.queryByLabelText("移动端设置分类")).not.toBeInTheDocument();
    expect(within(tree).getByRole("tab", { name: /银行账户/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "银行账户" })).toContainElement(screen.getByRole("region", { name: "银行账户映射" }));
    expect(screen.getByRole("region", { name: "银行账户映射" })).toHaveAttribute("id", "settings-section-bank-accounts");

    expect(screen.getByRole("region", { name: "银行账户映射" })).toBeInTheDocument();
  });

  test("switches the content panel when selecting another settings section", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();

    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tree).getByRole("tab", { name: /银行账户/ }));

    expect(screen.getByRole("region", { name: "银行账户映射" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "项目状态" })).not.toBeInTheDocument();
  });

  test("keeps every save in the page header and leaves data reset without a save action", async () => {
    const user = userEvent.setup();
    installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    renderAppAt("/settings");
    const tabs = await screen.findByRole("tablist", { name: "设置分类" });
    for (const [tab, button] of [
      ["银行账户", "保存设置"], ["OA导入设置", "保存设置"],
      ["访问账户", "保存访问权限"],
    ]) {
      await user.click(within(tabs).getByRole("tab", { name: tab, exact: true }));
      const actions = screen.getByRole("group", { name: "当前设置操作" });
      expect(within(actions).getByRole("button", { name: button, exact: true })).toBeInTheDocument();
      expect(within(screen.getByRole("tabpanel")).queryByRole("button", { name: /^保存/ })).not.toBeInTheDocument();
    }
    await user.click(within(tabs).getByRole("tab", { name: "数据重置", exact: true }));
    expect(within(screen.getByRole("group", { name: "当前设置操作" })).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清除所有银行流水数据" })).toBeInTheDocument();
  });

  test("keeps ordinary drafts across tabs and clears the unsaved status after saving", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    renderAppAt("/settings");
    const tabs = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    const input = screen.getByLabelText("OA导入起始日期");
    await user.clear(input);
    await user.type(input, "2026-02-01");
    expect(screen.getByText("有未保存修改")).toBeInTheDocument();
    await user.click(within(tabs).getByRole("tab", { name: "银行账户" }));
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    expect(screen.getByLabelText("OA导入起始日期")).toHaveValue("2026-02-01");
    const settingsWrites = () => fetchMock.mock.calls.filter(([url, init]) =>
      String(url).endsWith("/api/workbench/settings") && init?.method === "POST");
    expect(settingsWrites()).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(screen.queryByText("有未保存修改")).not.toBeInTheDocument());
    expect(settingsWrites()).toHaveLength(1);
    expect(JSON.parse(String(settingsWrites()[0][1]?.body)).oa_retention.cutoff_date).toEqual("2026-02-01");
  });

  test("keeps workbench-only header actions out of standalone settings", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
  });

  test("cancels both ordinary drafts and new account input without writing or losing access drafts", async () => {
    const user = userEvent.setup();
    const api = installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    renderAppAt("/settings");
    const tabs = await screen.findByRole("tablist", { name: "设置分类" });
    const bankName = screen.getAllByRole("textbox", { name: / 银行名称$/ })[0];
    const original = (bankName as HTMLInputElement).value;
    await user.clear(bankName);
    await user.type(bankName, "修改中的银行");
    await user.type(screen.getByLabelText("银行名称", { exact: true }), "未添加账户");
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    await user.clear(screen.getByLabelText("OA导入起始日期"));
    await user.type(screen.getByLabelText("OA导入起始日期"), "2026-02-01");
    await user.click(within(tabs).getByRole("tab", { name: "访问账户" }));
    await user.click(screen.getByRole("button", { name: "新增账户", exact: true }));
    await user.type(screen.getByRole("searchbox", { name: "搜索 OA 账户" }), "READONLY001");
    await user.click(await screen.findByRole("button", { name: "新增账户 READONLY001" }));
    await user.click(screen.getByRole("checkbox", { name: "关联台" }));
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    await user.click(screen.getByRole("button", { name: "取消修改" }));
    expect(screen.getByLabelText("OA导入起始日期")).toHaveValue("2026-01-01");
    await user.click(within(tabs).getByRole("tab", { name: "银行账户" }));
    expect(screen.getByLabelText("银行名称", { exact: true })).toHaveValue("");
    expect(screen.getAllByRole("textbox", { name: / 银行名称$/ })[0]).toHaveValue(original);
    await user.click(within(tabs).getByRole("tab", { name: "访问账户" }));
    expect(screen.getByRole("checkbox", { name: "关联台" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "取消修改" }));
    expect(screen.queryByText("READONLY001")).not.toBeInTheDocument();
    expect(api.mock.calls.filter(([url, init]) => String(url).includes("/workbench/settings") && ["POST", "PUT"].includes(init?.method ?? "GET"))).toHaveLength(0);
  });

  test("rejects empty dates, invalid mappings and duplicate last four digits before saving", async () => {
    const user = userEvent.setup();
    const api = installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    renderAppAt("/settings");
    const tabs = await screen.findByRole("tablist", { name: "设置分类" });
    const last4 = screen.getByLabelText("工商银行 后四位");
    await user.clear(last4);
    await user.type(last4, "0093");
    expect(last4).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
    await user.clear(last4);
    await user.type(last4, "123");
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "取消修改" }));
    const bankName = screen.getByLabelText("工商银行 银行名称");
    await user.clear(bankName);
    expect(bankName).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByRole("button", { name: "取消修改" }));
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    await user.clear(screen.getByLabelText("OA导入起始日期"));
    expect(screen.getByRole("alert")).toHaveTextContent("请选择 OA 导入起始日期。");
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
    expect(api.mock.calls.filter(([url, init]) => String(url).endsWith("/workbench/settings") && init?.method === "POST")).toHaveLength(0);
  });

  test("uses the server-normalized save result and retains unadded input outside the save payload", async () => {
    const user = userEvent.setup();
    const base = installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    const api = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await base(input, init);
      if (String(input).endsWith("/api/workbench/settings") && init?.method === "POST") {
        const saved = await response.json();
        saved.bank_account_mappings.reverse();
        saved.bank_account_mappings[0].short_name = "服务端简称";
        return new Response(JSON.stringify(saved), { headers: { "Content-Type": "application/json" } });
      }
      return response;
    });
    vi.stubGlobal("fetch", api);
    renderAppAt("/settings");
    const tabs = await screen.findByRole("tablist", { name: "设置分类" });
    await user.type(screen.getByLabelText("银行名称", { exact: true }), "待添加银行");
    await user.type(screen.getByLabelText("银行卡后四位"), "0066");
    await user.click(within(tabs).getByRole("tab", { name: "OA导入设置" }));
    await user.clear(screen.getByLabelText("OA导入起始日期"));
    await user.type(screen.getByLabelText("OA导入起始日期"), "2026-02-01");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await screen.findByText("已保存银行账户与 OA 导入设置。");
    expect(screen.queryByText("有未保存修改")).not.toBeInTheDocument();
    await user.click(within(tabs).getByRole("tab", { name: "银行账户" }));
    expect(screen.getByLabelText("银行名称", { exact: true })).toHaveValue("待添加银行");
    expect(screen.getByLabelText("银行卡后四位")).toHaveValue("0066");
    expect(screen.getByText("尚未添加", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByRole("textbox", { name: / 简称$/ })[0]).toHaveValue("服务端简称");
    expect(screen.getAllByRole("textbox", { name: / 银行名称$/ })[0]).toHaveValue("建设银行");
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();
    const write = api.mock.calls.find(([url, init]) => String(url).endsWith("/api/workbench/settings") && init?.method === "POST");
    const payload = JSON.parse(String(write![1]!.body));
    expect(payload.bank_account_mappings).toHaveLength(3);
    expect(payload.bank_account_mappings.some((mapping: { last4: string }) => mapping.last4 === "0066")).toBe(false);
    expect(payload.bank_account_mappings.some((mapping: { last4: string }) => mapping.last4 === "0093")).toBe(true);
    expect(payload).not.toHaveProperty("accounts");
    expect(payload).not.toHaveProperty("oa_applicant_credentials");
  });

  test("lets a user assigned to settings use normal settings actions", async () => {
    installMockApiFetch({
      sessionRole: "user",
      sessionUsername: "READONLY001",
    });
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "保存设置" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("银行名称", { exact: true }), "新账户");
    expect(screen.getByLabelText("银行名称", { exact: true })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消修改" })).toBeEnabled();
    await userEvent.type(screen.getByLabelText("银行卡后四位"), "0011");
    await userEvent.click(screen.getByRole("button", { name: "新增映射" }));
    expect(screen.getByRole("button", { name: "保存设置" })).toBeEnabled();
  });

  test("removes credential management and its requests from settings", async () => {
    const fetchMock = installMockApiFetch({ sessionRole: "admin", sessionUsername: "YNSYLP005" });
    renderAppAt("/settings");
    await screen.findByTestId("settings-page");
    expect(screen.queryByRole("tab", { name: /OA申请人凭据/ })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("oa-applicant-credentials"))).toBe(false);
  });

  test("keeps OA applicant credentials hidden from non-admin users", async () => {
    const fetchMock = installMockApiFetch({
      sessionRole: "user",
      sessionUsername: "chen_xiuyun",
    });
    renderAppAt("/settings");

    await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    expect(within(tree).queryByRole("tab", { name: /OA申请人凭据/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "OA申请人凭据" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/workbench/settings/access-control")).toBe(false);
  });

  test("saves access accounts only through the versioned admin endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionRole: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tree).getByRole("tab", { name: /访问账户/ }));
    const region = screen.getByRole("region", { name: "访问账户" });
    expect(within(region).getByText("YNSYLP005")).toBeInTheDocument();
    expect(within(region).queryByRole("textbox", { name: "YNSYLP005 账户" })).not.toBeInTheDocument();
    expect(within(region).queryByText(/固定权限管理员|自动拥有全部页面|为每个OA账户选择/)).not.toBeInTheDocument();

    await user.click(within(region).getByRole("button", { name: "新增账户" }));
    await user.type(within(region).getByRole("searchbox", { name: "搜索 OA 账户" }), "READONLY001");
    await user.click(await within(region).findByRole("button", { name: "新增账户 READONLY001" }));
    await user.click(within(region).getByRole("checkbox", { name: "关联台" }));
    await user.click(screen.getByRole("button", { name: "保存访问权限" }));
    expect(await screen.findByText("已保存访问账户。")).toBeInTheDocument();

    const accessSave = fetchMock.mock.calls.find(([input, init]) =>
      String(input) === "/api/workbench/settings/access-control"
      && (init?.method ?? "GET").toUpperCase() === "PUT",
    );
    expect(JSON.parse(String(accessSave?.[1]?.body ?? "{}"))).toEqual({
      expected_version: 1,
      accounts: [{ username: "READONLY001", page_keys: ["reconciliation-workbench"] }],
    });
  });

  test("keeps the access-account draft when CAS reports a conflict", async () => {
    const user = userEvent.setup();
    const baseFetch = installMockApiFetch({
      sessionRole: "admin",
      sessionUsername: "YNSYLP005",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (
        String(input) === "/api/workbench/settings/access-control"
        && (init?.method ?? "GET").toUpperCase() === "PUT"
      ) {
        return new Response(JSON.stringify({
          error: "access_control_version_conflict",
          message: "Access control version conflict.",
          current_version: 7,
        }), { status: 409, headers: { "Content-Type": "application/json" } });
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAppAt("/settings");

    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tree).getByRole("tab", { name: /访问账户/ }));
    const region = screen.getByRole("region", { name: "访问账户" });
    await user.click(within(region).getByRole("button", { name: "新增账户" }));
    await user.type(within(region).getByRole("searchbox", { name: "搜索 OA 账户" }), "CONFLICT001");
    await user.click(await within(region).findByRole("button", { name: "新增账户 CONFLICT001" }));
    await user.click(within(region).getByRole("checkbox", { name: "关联台" }));
    await user.click(screen.getByRole("button", { name: "保存访问权限" }));

    expect(await screen.findByText("访问账户已被其他管理员更新，请保留当前编辑并刷新后重试。")).toBeInTheDocument();
    expect(within(region).queryByText(/当前版本 7/)).not.toBeInTheDocument();
    expect(within(region).getAllByText("CONFLICT001").length).toBeGreaterThan(0);
  });

  test("keeps data reset behind impact confirmation, OA password review, and job progress", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionRole: "admin",
      sessionUsername: "YNSYLP005",
      dataResetJobPollsBeforeComplete: 1,
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tree).getByRole("tab", { name: /数据重置/ }));
    expect(within(settingsPage).queryByText(/高风险操作|不会触碰|会被清空/)).not.toBeInTheDocument();
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "确认数据重置" });
    expect(confirmDialog).toBeInTheDocument();
    expect(within(confirmDialog).getByText("清除所有银行流水数据")).toBeInTheDocument();
    expect(within(confirmDialog).getByText("预计影响 2 条记录。")).toBeInTheDocument();
    expect(within(confirmDialog).queryByText("已导入银行流水会被清空")).not.toBeInTheDocument();
    expect(within(confirmDialog).getByText("恢复点已验证。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "继续" }));
    expect(await screen.findByRole("dialog", { name: "OA 密码复核" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("当前 OA 用户密码"), "oa-password");
    await user.type(screen.getByLabelText(/操作原因/), "修复");
    expect(screen.getByText("还需输入 3 个字。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认清理" })).toBeDisabled();
    await user.clear(screen.getByLabelText(/操作原因/));
    await user.type(screen.getByLabelText(/操作原因/), "生产数据修复验证");
    await user.click(screen.getByRole("button", { name: "确认清理" }));

    expect(await within(settingsPage).findByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/data-reset/jobs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringMatching(/"oa_password":"oa-password".*"reason":"生产数据修复验证".*"impact_fingerprint":"a{64}".*"recovery_receipt_id":"00000000-0000-0000-0000-000000000001"/),
      }),
    );
  });


  test("saves OA attachment invoice promotion mode from OA retention settings", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionRole: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tablist", { name: "设置分类" });
    await user.click(within(tree).getByRole("tab", { name: /OA导入设置/ }));

    const region = within(settingsPage).getByRole("region", { name: "OA导入设置" });
    await user.click(within(region).getByRole("button", { name: /OA附件发票处理/ }));
    await user.click(await screen.findByRole("option", { name: "不处理附件发票" }));
    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/settings",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"attachment_invoice_promotion_mode\":\"disabled\""),
        }),
      );
    });
  });


});
