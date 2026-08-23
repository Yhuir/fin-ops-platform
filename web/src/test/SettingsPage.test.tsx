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
  "src/components/settings/SettingsTreeNav.tsx",
  "src/components/settings/SettingsProjectsSection.tsx",
  "src/components/settings/SettingsBankAccountsSection.tsx",
  "src/components/settings/SettingsPendingInvoiceTagsSection.tsx",
  "src/components/settings/SettingsOaRetentionSection.tsx",
  "src/components/settings/SettingsOaInvoiceOffsetSection.tsx",
  "src/components/settings/SettingsOaApplicantCredentialsSection.tsx",
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

function installSettingsTagFetch() {
  const baseFetch = installMockApiFetch();
  let settingsVersion = 4;
  const settingsPayload = () => ({
    projects: { active: [], completed: [], completed_project_ids: [] },
    bank_account_mappings: [],
    workbench_column_layouts: { oa: [], bank: [], invoice: [] },
    oa_retention: { cutoff_date: "2026-01-01" },
    oa_import: {
      form_types: ["payment_request"],
      statuses: ["completed"],
      attachment_invoice_promotion_mode: "link_existing_only",
    },
    oa_invoice_offset: { applicant_names: [] },
    bank_transaction_tags: {
      version: settingsVersion,
      tags: [
        { code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" },
        { code: "salary", label: "工资", path: ["自动识别", "工资"], status: "active", source: "system" },
        { code: "internal_transfer", label: "内部往来款", path: ["自动识别", "内部往来款"], status: "active", source: "system" },
      ],
    },
    pending_invoice_tag_groups: {
      requires_invoice: ["fee"],
      bank_statement_as_invoice: [],
      no_invoice_required: ["salary"],
    },
  });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/workbench/settings") {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        settingsVersion = 5;
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        expect(body).not.toHaveProperty("bank_transaction_tags");
        expect(body.pending_invoice_tag_groups).toMatchObject({
          groups: {
            bank_statement_as_invoice: { tag_codes: expect.arrayContaining(["internal_transfer"]) },
          },
        });
      }
      return new Response(JSON.stringify(settingsPayload()), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function installInvalidPendingInvoiceTagFetch() {
  const baseFetch = installMockApiFetch();
  let postCount = 0;
  const settingsPayload = () => ({
    projects: { active: [], completed: [], completed_project_ids: [] },
    bank_account_mappings: [],
    workbench_column_layouts: { oa: [], bank: [], invoice: [] },
    oa_retention: { cutoff_date: "2026-01-01" },
    oa_import: {
      form_types: ["payment_request"],
      statuses: ["completed"],
      attachment_invoice_promotion_mode: "link_existing_only",
    },
    oa_invoice_offset: { applicant_names: [] },
    bank_transaction_tags: {
      version: 4,
      tags: [
        { code: "fee", label: "手续费", path: ["自动识别", "手续费"], status: "active", source: "system" },
        { code: "salary", label: "工资", path: ["自动识别", "工资"], status: "archived", source: "system" },
      ],
    },
    pending_invoice_tag_groups: {
      requires_invoice: ["missing_tag", "salary"],
      bank_statement_as_invoice: [],
      no_invoice_required: [],
    },
  });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/workbench/settings") {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        postCount += 1;
      }
      return new Response(JSON.stringify(settingsPayload()), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    fetchMock,
    getPostCount: () => postCount,
  };
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

    const pageSource = sourceByPath["src/pages/SettingsPage.tsx"];
    const contentSource = sourceByPath["src/components/settings/SettingsPageContent.tsx"];
    const dataResetDialogsSource = sourceByPath["src/components/settings/SettingsDataResetDialogs.tsx"];
    const oaManualTableSource = sourceByPath["src/components/settings/OaManualSearchImportTable.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("SettingsPageContent") ? null : "SettingsPage.tsx should keep SettingsPageContent",
      contentSource.includes("SettingsTreeNav") ? null : "SettingsPageContent.tsx should keep SettingsTreeNav",
      /role=["']treeitem["']/.test(sourceByPath["src/components/settings/SettingsTreeNav.tsx"]) ? null : "SettingsTreeNav should preserve treeitem semantics",
      /ListBox, Select/.test(sourceByPath["src/components/settings/SettingsTreeNav.tsx"]) ? null : "SettingsTreeNav should use the HeroUI mobile section selector",
      /ariaLabel=["']OA全量搜索导入结果["']/.test(oaManualTableSource) ? null : "OA manual search should preserve table accessible name",
      /确认数据重置/.test(dataResetDialogsSource) && /OA 密码复核/.test(dataResetDialogsSource) ? null : "Data reset should keep two modal dialog labels",
      /minLength=\{5\}/.test(dataResetDialogsSource) && /至少输入 5 个字/.test(dataResetDialogsSource) ? null : "Data reset should expose its reason requirement",
    ].filter(Boolean);

    expect(missingPrimitiveTargets).toEqual([]);
  });

  test("keeps premium settings tree, form, table, dialog, and motion CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const shellRule = cssRule(styles, ".settings-route,\n.settings-layout,\n.settings-content-panel");
    const navRule = cssRule(styles, ".settings-nav-shell,\n.settings-tree-panel");
    const panelRule = cssRule(styles, ".settings-content-panel,\n.settings-section-panel");
    const treeMotionRule = cssRule(styles, ".settings-tree-item", "--motion-fast");
    const controlMotionRule = cssRule(
      styles,
      ".settings-save-button,\n.settings-primary-button,\n.settings-secondary-button,\n.settings-danger-button,\n.settings-icon-button,\n.settings-menu button,\n.settings-pending-group-button,\n.settings-project-row,\n.settings-checkbox-row,\n.settings-table-pagination select",
      "--motion-fast",
    );
    const fieldRule = cssRule(styles, ".settings-field input,\n.settings-table-input,\n.settings-select-control");
    const tableRule = cssRule(styles, ".settings-native-table th,\n.settings-native-table td");
    const amountRule = cssRule(styles, ".settings-table-code,\n.settings-table-input--code,\n.settings-table-amount");
    const tagRule = cssRule(styles, ".settings-source-tag,\n.settings-selected-tag,\n.oa-manual-import__metrics span");
    const projectRule = cssRule(styles, ".settings-project-toolbar,\n.settings-bank-mapping-row,\n.settings-data-reset-card,\n.settings-pending-tag-panel,\n.settings-checkbox-list");
    const projectColumnRule = cssRule(styles, ".settings-project-column");
    const oaTableRule = cssRule(styles, ".oa-manual-import__table");
    const selectedRule = cssRule(styles, ".settings-native-table-row--selected > td,\n.settings-tree-item[aria-selected=\"true\"],\n.settings-tree-item--selected");
    const dangerRule = cssRule(styles, ".settings-danger-button:hover:not(:disabled)");

    expect(shellRule).toContain("var(--fp-surface)");
    expect(navRule).toContain("var(--fp-border)");
    expect(navRule).toContain("var(--fp-radius-sm)");
    expect(panelRule).toContain("border-radius: 0");
    expect(treeMotionRule).toContain("--motion-fast");
    expect(treeMotionRule).toContain("--ease-out-quart");
    expect(controlMotionRule).toContain("--motion-fast");
    expect(controlMotionRule).toContain("--ease-out-quart");
    expect(fieldRule).toContain("var(--fp-border)");
    expect(fieldRule).toContain("--motion-fast");
    expect(tableRule).toContain("height: 36px");
    expect(tableRule).toContain("--motion-fast");
    expect(amountRule).toContain("font-variant-numeric: tabular-nums");
    expect(amountRule).toContain("text-align: right");
    expect(tagRule).toContain("min-height: var(--fp-tag-height-table)");
    expect(tagRule).toContain("border-radius: var(--fp-tag-radius-table)");
    expect(projectRule).toContain("var(--fp-surface)");
    expect(projectRule).toContain("var(--fp-border)");
    expect(projectColumnRule).toContain("border-radius: 0");
    expect(oaTableRule).toContain("min-width: 1500px");
    expect(oaTableRule).toContain("table-layout: fixed");
    expect(selectedRule).toContain("var(--fp-primary-soft)");
    expect(dangerRule).toContain("color-mix(in srgb, var(--fp-danger)");
    expect([
      shellRule,
      navRule,
      treeMotionRule,
      controlMotionRule,
      fieldRule,
      tableRule,
      projectRule,
      selectedRule,
      dangerRule,
    ].join("\n")).not.toMatch(/#102a43|#486581|#e7edf5|#fbfdff|#ffffff|#f0fff4|#fff5f5|#9f1d1d|#0f4c81|180ms ease-out/i);
  });

  test("renders as a tree-and-panel page without an extra page header title", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联台设置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "关联台设置" })).not.toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    expect(screen.getByLabelText("移动端设置分类")).toBeInTheDocument();
    expect(within(tree).getByRole("treeitem", { name: /项目状态/ })).toHaveAttribute("aria-selected", "true");
    expect(within(tree).getByRole("treeitem", { name: /银行账户/ })).toHaveAttribute("aria-controls", "settings-section-bank-accounts");
    expect(screen.getByRole("region", { name: "项目状态管理" })).toHaveAttribute("id", "settings-section-projects");

    expect(screen.getByRole("region", { name: "项目状态管理" })).toBeInTheDocument();
  });

  test("switches the content panel when selecting another settings section", async () => {
    const user = userEvent.setup();
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /银行账户/ }));

    expect(screen.getByRole("region", { name: "银行账户映射" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "项目状态管理" })).not.toBeInTheDocument();
  });

  test("keeps workbench-only header actions out of standalone settings", async () => {
    installMockApiFetch();
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument();
  });

  test("keeps read-only settings users from saving changes", async () => {
    installMockApiFetch({
      sessionAccessTier: "read_export_only",
      sessionUsername: "READONLY001",
    });
    renderAppAt("/settings");

    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(await screen.findByText("当前账号仅支持查看和导出，不能保存设置。")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "保存设置" })).toBeDisabled();
  });

  test("lets admin maintain OA applicant credentials through dedicated endpoints", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /OA申请人凭据/ }));

    const region = within(settingsPage).getByRole("region", { name: "OA申请人凭据" });
    expect(within(region).getByText("陈秀云")).toBeInTheDocument();
    expect(within(region).getByText("已配置")).toBeInTheDocument();
    expect(within(region).queryByDisplayValue("oa-secret")).not.toBeInTheDocument();

    await user.clear(within(region).getByRole("textbox", { name: "目标 OA 申请人" }));
    await user.type(within(region).getByRole("textbox", { name: "目标 OA 申请人" }), "樊祖芳");
    await user.clear(within(region).getByRole("textbox", { name: "申请人账号标识" }));
    await user.type(within(region).getByRole("textbox", { name: "申请人账号标识" }), "fan_zufang");
    await user.clear(within(region).getByRole("textbox", { name: "OA 登录账号" }));
    await user.type(within(region).getByRole("textbox", { name: "OA 登录账号" }), "fan_zufang");
    const passwordInput = within(region).getByLabelText("OA 登录密码") as HTMLInputElement;
    await user.type(passwordInput, "target-password");
    await user.click(within(region).getByRole("button", { name: "保存凭据" }));

    await waitFor(() => expect(passwordInput).toHaveValue(""));
    expect(within(region).getByText("樊祖芳")).toBeInTheDocument();
    expect(within(region).getAllByText("已配置").length).toBeGreaterThanOrEqual(2);

    const credentialSaveCall = fetchMock.mock.calls.find(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return (
        url.pathname === "/api/workbench/settings/oa-applicant-credentials/fan_zufang"
        && (init?.method ?? "GET").toUpperCase() === "PUT"
      );
    });
    expect(credentialSaveCall).toBeDefined();
    expect(JSON.parse(String(credentialSaveCall?.[1]?.body ?? "{}"))).toMatchObject({
      targetApplicantName: "樊祖芳",
      oaUsername: "fan_zufang",
      password: "target-password",
    });

    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        if (url.pathname !== "/api/workbench/settings" || (init?.method ?? "GET").toUpperCase() !== "POST") {
          return false;
        }
        const bodyText = String(init?.body ?? "");
        return !bodyText.includes("target-password") && !bodyText.includes("oa_applicant_credentials");
      })).toBe(true);
    });
  });

  test("keeps OA applicant credentials hidden from full-access non-admin users", async () => {
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "full_access",
      sessionUsername: "chen_xiuyun",
    });
    renderAppAt("/settings");

    await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    expect(within(tree).queryByRole("treeitem", { name: /OA申请人凭据/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "OA申请人凭据" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/workbench/settings/access-control")).toBe(false);
  });

  test("saves access accounts only through the versioned admin endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /访问账户/ }));
    const region = screen.getByRole("region", { name: "访问账户管理" });
    expect(within(region).getByText("YNSYLP005")).toBeInTheDocument();
    expect(within(region).queryByRole("textbox", { name: "YNSYLP005 账户" })).not.toBeInTheDocument();

    await user.type(within(region).getByRole("textbox", { name: "新增访问账户" }), "READONLY001");
    await user.selectOptions(within(region).getByLabelText("新增账户权限"), "read_export_only");
    await user.click(within(region).getByRole("button", { name: "新增账户" }));
    await user.click(within(region).getByRole("button", { name: "保存访问账户" }));
    expect(await within(region).findByText("已保存访问账户。")).toBeInTheDocument();

    const accessSave = fetchMock.mock.calls.find(([input, init]) =>
      String(input) === "/api/workbench/settings/access-control"
      && (init?.method ?? "GET").toUpperCase() === "PUT",
    );
    expect(JSON.parse(String(accessSave?.[1]?.body ?? "{}"))).toEqual({
      expected_version: 1,
      accounts: [{ username: "READONLY001", access_tier: "read_export_only" }],
    });
  });

  test("keeps the access-account draft when CAS reports a conflict", async () => {
    const user = userEvent.setup();
    const baseFetch = installMockApiFetch({
      sessionAccessTier: "admin",
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

    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /访问账户/ }));
    const region = screen.getByRole("region", { name: "访问账户管理" });
    await user.type(within(region).getByRole("textbox", { name: "新增访问账户" }), "CONFLICT001");
    await user.click(within(region).getByRole("button", { name: "新增账户" }));
    await user.click(within(region).getByRole("button", { name: "保存访问账户" }));

    expect(await within(region).findByText("访问账户已被其他管理员更新，请保留当前编辑并刷新后重试。")).toBeInTheDocument();
    expect(within(region).queryByText(/当前版本 7/)).not.toBeInTheDocument();
    expect(within(region).getByRole("textbox", { name: "CONFLICT001 账户" })).toHaveValue("CONFLICT001");
  });

  test("keeps data reset behind impact confirmation, OA password review, and job progress", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
      dataResetJobPollsBeforeComplete: 1,
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /数据重置/ }));
    await user.click(within(settingsPage).getByRole("button", { name: "清除所有银行流水数据" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "确认数据重置" });
    expect(confirmDialog).toBeInTheDocument();
    expect(within(confirmDialog).getByText("已导入银行流水会被清空")).toBeInTheDocument();
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

  test("manages pending invoice tag mappings with read-only automatic tag dictionary", async () => {
    const user = userEvent.setup();
    const fetchMock = installSettingsTagFetch();
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    expect(within(tree).queryByRole("treeitem", { name: /银行明细标签管理/ })).not.toBeInTheDocument();
    expect(within(tree).queryByText("全 app 银行明细标签字典")).not.toBeInTheDocument();
    expect(within(tree).queryByRole("treeitem", { name: /银行流水标签/ })).not.toBeInTheDocument();
    await user.click(within(tree).getByRole("treeitem", { name: /待找发票筛选/ }));

    const region = within(settingsPage).getByRole("region", { name: "待找发票筛选" });
    expect(within(region).getByText("需要开票")).toBeInTheDocument();
    expect(within(region).getByText("流水代替发票")).toBeInTheDocument();
    expect(within(region).getByText("无需开票")).toBeInTheDocument();
    expect(within(region).queryByRole("textbox", { name: "新标签" })).not.toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: /新建并加入/ })).not.toBeInTheDocument();
    await user.click(within(region).getByText("流水代替发票"));
    expect(within(region).getByText("当前分组未选择自动标签。")).toBeInTheDocument();
    await user.click(within(region).getByRole("button", { name: "选择现有标签" }));
    await user.click(await screen.findByRole("menuitem", { name: "内部往来款" }));
    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/workbench/settings" && (init?.method ?? "GET").toUpperCase() === "POST";
      })).toBe(true);
    });
  });

  test("saves OA attachment invoice promotion mode from OA retention settings", async () => {
    const user = userEvent.setup();
    const fetchMock = installMockApiFetch({
      sessionAccessTier: "admin",
      sessionUsername: "YNSYLP005",
    });
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /OA导入设置/ }));

    const region = within(settingsPage).getByRole("region", { name: "OA导入设置" });
    await user.selectOptions(within(region).getByLabelText("OA附件发票晋级"), "disabled");
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

  test("keeps invalid historical pending invoice mappings visible and blocks save until removed", async () => {
    const user = userEvent.setup();
    const { getPostCount } = installInvalidPendingInvoiceTagFetch();
    renderAppAt("/settings");

    const settingsPage = await screen.findByTestId("settings-page");
    const tree = await screen.findByRole("tree", { name: "设置分类" });
    await user.click(within(tree).getByRole("treeitem", { name: /待找发票筛选/ }));

    const region = within(settingsPage).getByRole("region", { name: "待找发票筛选" });
    expect(within(region).getByText("missing_tag")).toBeInTheDocument();
    expect(within(region).getByText("标签不存在")).toBeInTheDocument();
    expect(within(region).getByText("工资")).toBeInTheDocument();
    expect(within(region).getByText("标签已停用")).toBeInTheDocument();

    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));
    expect(await within(settingsPage).findByText("待找发票筛选引用了不存在的银行明细标签，请移除后再保存。")).toBeInTheDocument();
    expect(getPostCount()).toBe(0);

    await user.click(within(region).getByRole("button", { name: "missing_tag 移除" }));
    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));
    expect(await within(settingsPage).findByText("待找发票筛选引用了已停用的银行明细标签，请先从待找发票筛选中移除。")).toBeInTheDocument();
    expect(getPostCount()).toBe(0);

    await user.click(within(region).getByRole("button", { name: "工资 移除" }));
    await user.click(within(settingsPage).getByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(getPostCount()).toBe(1));
  });

});
