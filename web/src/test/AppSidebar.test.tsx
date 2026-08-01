import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import AppSidebar from "../components/shell/AppSidebar";
import { sidebarGroups } from "../components/shell/sidebarItems";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";

const sidebarSession: SessionContextValue = {
  status: "authenticated",
  session: {
    allowed: true,
    user: {
      userId: "101",
      username: "liuji",
      nickname: "刘际涛",
      displayName: "刘际涛",
      deptId: "88",
      deptName: "财务部",
      avatar: null,
    },
    roles: ["finance"],
    permissions: ["finops:app:view"],
    accessTier: "full_access",
    canAccessApp: true,
    canMutateData: true,
    canAdminAccess: false,
  },
  refresh: () => undefined,
};

function withSidebarSession(children: React.ReactNode) {
  return <SessionContext.Provider value={sidebarSession}>{children}</SessionContext.Provider>;
}

function renderSidebar(expanded = false) {
  return render(
    withSidebarSession(
      <MemoryRouter initialEntries={["/fin-ops/workbench"]}>
        <AppSidebar
          embedded={false}
          expanded={expanded}
          isCompact={false}
          mobileOpen={false}
          onCloseMobile={() => undefined}
          onToggleExpanded={() => undefined}
        />
      </MemoryRouter>,
    ),
  );
}

function renderSidebarAt(
  initialPath: string,
  props?: Partial<{
    expanded: boolean;
    isCompact: boolean;
    mobileOpen: boolean;
    onCloseMobile: () => void;
    onToggleExpanded: () => void;
  }>,
) {
  return render(
    withSidebarSession(
      <MemoryRouter initialEntries={[initialPath]}>
        <AppSidebar
          embedded={false}
          expanded={props?.expanded ?? true}
          isCompact={props?.isCompact ?? false}
          mobileOpen={props?.mobileOpen ?? false}
          onCloseMobile={props?.onCloseMobile ?? (() => undefined)}
          onToggleExpanded={props?.onToggleExpanded ?? (() => undefined)}
        />
      </MemoryRouter>,
    ),
  );
}

function renderEmbeddedSidebar(expanded = true) {
  return render(
    withSidebarSession(
      <MemoryRouter initialEntries={["/fin-ops/workbench"]}>
        <AppSidebar
          embedded={true}
          expanded={expanded}
          isCompact={false}
          mobileOpen={false}
          onCloseMobile={() => undefined}
          onToggleExpanded={() => undefined}
        />
      </MemoryRouter>,
    ),
  );
}

describe("AppSidebar shell contract", () => {
  const appSidebarSource = readFileSync("src/components/shell/AppSidebar.tsx", "utf8");
  const appStatusSource = readFileSync("src/components/shell/AppStatusIndicator.tsx", "utf8");
  const brandMarkSource = readFileSync("src/components/shell/finance-platform-mark.svg", "utf8");
  const appSource = readFileSync("src/app/App.tsx", "utf8");
  const workbenchFilterSource = readFileSync("src/components/workbench/WorkbenchColumnFilterMenu.tsx", "utf8");
  const appStyles = readFileSync("src/app/styles.css", "utf8");

  test("keeps the desktop rail fixed and uses the approved navigation rhythm", () => {
    const sidebarRule = appStyles.match(/\.app-sidebar\s*\{[^}]*\}/s)?.[0] ?? "";
    const paperRule = appStyles.match(/\.app-sidebar-paper\s*\{[^}]*\}/s)?.[0] ?? "";
    const brandRule = appStyles.match(/\.app-sidebar-brand\s*\{[^}]*\}/s)?.[0] ?? "";
    const itemRule = appStyles.match(/\.app-sidebar-item\s*\{[^}]*\}/s)?.[0] ?? "";
    const groupTitleRule = appStyles.match(/\.app-sidebar-group-title\s*\{[^}]*\}/s)?.[0] ?? "";
    const linkRule = appStyles.match(/\.app-sidebar-link\s*\{[^}]*\}/s)?.[0] ?? "";
    const iconRule = appStyles.match(/\.app-sidebar-link-icon\s*\{[^}]*\}/s)?.[0] ?? "";
    const iconSvgRule = appStyles.match(/\.app-sidebar-link-icon svg\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(sidebarRule).toMatch(/position:\s*sticky;/);
    expect(sidebarRule).toMatch(/top:\s*0;/);
    expect(sidebarRule).toMatch(/height:\s*100dvh;/);
    expect(paperRule).toMatch(/background:\s*#334154;/);
    expect(paperRule).toMatch(/color:\s*#e6f0ff;/);
    expect(brandRule).toMatch(/min-height:\s*64px;/);
    expect(groupTitleRule).toMatch(/color:\s*#b8cce5;/);
    expect(itemRule).toMatch(/min-height:\s*36px;/);
    expect(linkRule).toMatch(/min-height:\s*36px;/);
    expect(linkRule).toMatch(/font-size:\s*14px;/);
    expect(linkRule).toMatch(/font-weight:\s*500;/);
    expect(iconRule).toMatch(/width:\s*26px;/);
    expect(iconRule).toMatch(/min-width:\s*26px;/);
    expect(iconRule).toMatch(/flex:\s*0 0 26px;/);
    expect(iconSvgRule).toMatch(/width:\s*16px;/);
    expect(iconSvgRule).toMatch(/height:\s*16px;/);
    expect(iconSvgRule).toMatch(/flex:\s*none;/);
    expect(appSidebarSource).toMatch(/size=\{16\}/);
    expect(appStyles).toMatch(/\.app-sidebar-list\s*\{[^}]*gap:\s*4px;/s);
    expect(appStyles).toMatch(/\.app-sidebar-account-footer\s*\{[^}]*flex:\s*0 0 72px;/s);
    expect(appStyles).toMatch(/\.app-sidebar-dialog \.app-sidebar-link\s*\{[^}]*min-height:\s*44px;/s);
    expect(appSource).toContain("function StatefulAppSidebar");
    expect(appSource).not.toMatch(/style=\{shellStyle\}|const sidebarWidth/);
    expect(appStyles).not.toContain("--sidebar-width");
    expect(workbenchFilterSource).toContain('querySelector<HTMLElement>(".app-sidebar")');
    expect(workbenchFilterSource).not.toContain("--sidebar-width");
  });

  test("does not render the OA embedded layout explanation card", () => {
    renderEmbeddedSidebar(true);

    expect(screen.queryByText("OA 嵌入模式默认折叠，避免占用工作台宽度。")).not.toBeInTheDocument();
    expect(appSidebarSource).not.toContain("OA 嵌入模式默认折叠");
    expect(appStyles).not.toMatch(/\.app-sidebar-embedded-note\s*\{/);
  });

  test("uses a static local brand mark and deletes the rotating status path", () => {
    const brandMarkRule = appStyles.match(/\.app-sidebar-brand-mark\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(brandMarkRule).not.toMatch(/radial-gradient|linear-gradient/);
    expect(brandMarkRule).toMatch(/border:\s*0;/);
    expect(brandMarkRule).toMatch(/border-radius:\s*8px;/);
    expect(brandMarkRule).toMatch(/background:\s*transparent;/);
    expect(brandMarkRule).toMatch(/color:\s*#86efac;/);
    expect(appStatusSource).toContain("finance-platform-mark.svg");
    expect(appStatusSource).toContain("<button");
    expect(appStatusSource).not.toContain('role="status"');
    expect(appStatusSource).not.toMatch(/<circle|status-track|status-sweep/);
    expect(brandMarkSource).toContain('fill="#2563EB"');
    expect(brandMarkSource).toContain('stroke="#FFF"');
    expect(brandMarkSource).not.toContain("#EAF2FF");
    expect(brandMarkSource).not.toContain("M8 9.5h16");
    expect(appStyles).not.toMatch(/sidebar-status-orbit|app-sidebar-brand-status-track|app-sidebar-brand-status-sweep/);
    expect(appStyles).not.toMatch(/\.app-sidebar[^}]*animation:\s*[^;]*infinite/s);
  });

  test("shows the current OA account and opens its details without a second identity source", async () => {
    renderSidebar(true);

    expect(screen.getByText("刘际涛")).toBeInTheDocument();
    expect(screen.getByText("liuji")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "当前账号：刘际涛" }));

    const dialog = await screen.findByRole("dialog", { name: "当前 OA 账号详情" });
    expect(dialog).toHaveTextContent("当前登录 OA 账号");
    expect(dialog).toHaveTextContent("liuji");
    expect(dialog).toHaveTextContent("财务部");
    expect(appSidebarSource).toContain("AppSidebarAccount");
    expect(appSidebarSource).not.toContain("财务运营管理员");
  });

  test("renders the expand control as an icon-only control without visible tooltip copy", () => {
    const { container } = renderSidebar(false);

    const toggle = screen.getByRole("button", { name: "展开菜单" });
    const brandLockup = container.querySelector(".app-sidebar-brand-lockup");
    expect(toggle).toHaveClass("app-sidebar-toggle");
    expect(toggle).toHaveAttribute("title", "展开菜单");
    expect(brandLockup).toHaveAttribute("aria-hidden", "true");
    expect(brandLockup).toHaveAttribute("inert");
    expect(container.querySelector(".app-sidebar-brand-mark")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "系统状态正常" })).not.toBeInTheDocument();
    expect(screen.queryByText("展开菜单")).not.toBeInTheDocument();
    expect(appSidebarSource).toContain("PanelLeftOpen");
    expect(appSidebarSource).toContain("PanelLeftClose");
    expect(appSidebarSource).not.toMatch(/ChevronLeft|ChevronRight/);
    expect(appSidebarSource).not.toMatch(/Tooltip\.Content[\s\S]*(展开菜单|折叠菜单)/);
  });

  test("keeps collapsed labels mounted while hiding the brand and animating the shared shell", () => {
    renderSidebar(false);

    const contentRule = appStyles.match(/\.app-sidebar-content\s*\{[^}]*\}/s)?.[0] ?? "";
    const sidebarRule = appStyles.match(/\.app-sidebar\s*\{[^}]*\}/s)?.[0] ?? "";
    const paperRule = appStyles.match(/\.app-sidebar-paper\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedPaperRule = appStyles.match(/\.app-sidebar\.collapsed \.app-sidebar-paper\s*\{[^}]*\}/s)?.[0] ?? "";
    const brandLockupRule = appStyles.match(/\.app-sidebar-brand-lockup\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedBrandLockupRule = appStyles.match(/\.app-sidebar-brand\.collapsed \.app-sidebar-brand-lockup\s*\{[^}]*\}/s)?.[0] ?? "";
    const toggleRule = appStyles.match(/\.app-sidebar-toggle\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedToggleRule = appStyles.match(/\.app-sidebar-brand\.collapsed \.app-sidebar-toggle\s*\{[^}]*\}/s)?.[0] ?? "";
    const brandTextRule = appStyles.match(/\.app-sidebar-brand-text\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedBrandTextRule = appStyles.match(/\.app-sidebar-content\.collapsed \.app-sidebar-brand-text\s*\{[^}]*\}/s)?.[0] ?? "";
    const linkLabelRule = appStyles.match(/\.app-sidebar-link-label\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedLinkLabelRule = appStyles.match(/\.app-sidebar-content\.collapsed \.app-sidebar-link-label\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedGroupRule = appStyles.match(/\.app-sidebar-content\.collapsed \.app-sidebar-group\s*\{[^}]*\}/s)?.[0] ?? "";
    const collapsedListRule = appStyles.match(/\.app-sidebar-content\.collapsed \.app-sidebar-list\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(screen.getByText("财务运营平台")).toBeInTheDocument();
    expect(screen.getByText("财务业务")).toBeInTheDocument();
    expect(screen.getByText("关联台")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "银行明细" })).toHaveAttribute("title", "银行明细");
    expect(sidebarRule).toMatch(/--app-sidebar-content-motion:\s*var\(--motion-base\) var\(--ease-out-quart\)/);
    expect(sidebarRule).not.toMatch(/transition:[^}]*(flex-basis|width)/);
    expect(paperRule).toMatch(/width:\s*232px;/);
    expect(paperRule).toMatch(/transition:\s*width var\(--app-sidebar-content-motion\)/);
    expect(collapsedPaperRule).toMatch(/width:\s*72px;/);
    expect(contentRule).toMatch(/width:\s*232px;/);
    expect(contentRule).toMatch(/transition:\s*width var\(--app-sidebar-content-motion\)/);
    expect(appStyles).toMatch(/\.app-sidebar-content\.collapsed\s*\{[^}]*width:\s*72px;/s);
    expect(contentRule).not.toMatch(/will-change:\s*width/);
    expect(paperRule).not.toMatch(/will-change:\s*width/);
    expect(sidebarRule).not.toMatch(/will-change:\s*width/);
    expect(brandLockupRule).toMatch(/opacity[^;]*var\(--motion-fast\)/);
    expect(brandLockupRule).toMatch(/transform[^;]*var\(--motion-base\)/);
    expect(collapsedBrandLockupRule).toMatch(/opacity:\s*0;/);
    expect(collapsedBrandLockupRule).toMatch(/pointer-events:\s*none;/);
    expect(collapsedBrandLockupRule).toMatch(/visibility:\s*hidden;/);
    expect(collapsedBrandLockupRule).not.toMatch(/width:\s*28px|flex:\s*0 0 28px/);
    expect(toggleRule).toMatch(/position:\s*absolute;/);
    expect(toggleRule).toMatch(/right:\s*10px;/);
    expect(collapsedToggleRule).toMatch(/--app-sidebar-toggle-offset:\s*-10px;/);
    expect(brandTextRule).toMatch(/opacity[^;]*var\(--app-sidebar-content-motion\)/);
    expect(brandTextRule).toMatch(/transform[^;]*var\(--app-sidebar-content-motion\)/);
    expect(brandTextRule).not.toMatch(/transition:[^;]*(max-width|max-height|padding)/);
    expect(collapsedBrandTextRule).toMatch(/opacity:\s*0;/);
    expect(linkLabelRule).toMatch(/opacity[^;]*var\(--app-sidebar-content-motion\)/);
    expect(linkLabelRule).toMatch(/transform[^;]*var\(--app-sidebar-content-motion\)/);
    expect(collapsedLinkLabelRule).toMatch(/opacity:\s*0;/);
    expect(collapsedLinkLabelRule).toMatch(/width:\s*0;/);
    expect(collapsedLinkLabelRule).toMatch(/max-width:\s*0;/);
    expect(collapsedLinkLabelRule).toMatch(/flex:\s*0 0 0;/);
    expect(linkLabelRule).not.toMatch(/transition:[^;]*(max-width|max-height|padding)/);
    expect(collapsedGroupRule).toMatch(/width:\s*34px;/);
    expect(collapsedListRule).toMatch(/width:\s*34px;/);
    expect(appStyles).toMatch(/\.app-sidebar-content\.collapsed \.app-sidebar-link-icon\s*\{[^}]*flex:\s*0 0 34px;/s);
    expect(appStyles).not.toMatch(/\.app-sidebar-brand\.collapsed \.app-sidebar-toggle\s*\{[^}]*right:\s*-7px;/s);
    expect(appSidebarSource).not.toMatch(/Tooltip\.Trigger/);
    expect(appStyles).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(appStyles).toMatch(/\[data-reduce-motion="true"\] \.app-sidebar-paper/);
  });

  test("prefetches the route chunk on sidebar hover and focus without changing the link target", () => {
    const bankDetailsItem = sidebarGroups
      .flatMap((group) => group.items)
      .find((item) => item.label === "银行明细");
    expect(bankDetailsItem).toBeDefined();
    const originalPreload = bankDetailsItem?.preload;
    const preload = vi.fn(() => Promise.resolve());
    if (bankDetailsItem) {
      bankDetailsItem.preload = preload;
    }

    try {
      renderSidebar(true);
      const bankDetailsLink = screen.getByRole("link", { name: "银行明细" });

      expect(bankDetailsLink).toHaveAttribute("href", "/bank-details");
      fireEvent.pointerEnter(bankDetailsLink);
      fireEvent.focus(bankDetailsLink);

      expect(preload).toHaveBeenCalledTimes(2);
    } finally {
      if (bankDetailsItem && originalPreload) {
        bankDetailsItem.preload = originalPreload;
      }
    }
  });

  test("derives active route state from the current path while import shortcuts stay inactive", () => {
    const { unmount } = renderSidebarAt("/bank-details/transactions");

    expect(screen.getByRole("link", { name: "银行明细" })).toHaveAttribute("aria-current", "page");

    unmount();
    renderSidebarAt("/imports/bank-transactions");

    expect(screen.getByRole("link", { name: "银行流水导入" })).not.toHaveAttribute("aria-current");
  });

  test("closes the compact drawer after selecting a navigation item", () => {
    const onCloseMobile = vi.fn();

    renderSidebarAt("/cost-statistics", {
      isCompact: true,
      mobileOpen: true,
      onCloseMobile,
    });

    fireEvent.click(screen.getByRole("link", { name: "设置" }));

    expect(onCloseMobile).toHaveBeenCalledTimes(1);
  });
});
