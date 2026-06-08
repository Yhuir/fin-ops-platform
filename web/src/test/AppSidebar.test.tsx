import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import AppSidebar from "../components/shell/AppSidebar";
import { sidebarGroups } from "../components/shell/sidebarItems";

function renderSidebar(expanded = false) {
  return render(
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
  );
}

function renderEmbeddedSidebar(expanded = true) {
  return render(
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
  );
}

describe("AppSidebar shell contract", () => {
  const appSidebarSource = readFileSync("src/components/shell/AppSidebar.tsx", "utf8");
  const appStyles = readFileSync("src/app/styles.css", "utf8");

  test("keeps the desktop rail fixed and uses compact navigation row rhythm", () => {
    const sidebarRule = appStyles.match(/\.app-sidebar\s*\{[^}]*\}/s)?.[0] ?? "";
    const brandRule = appStyles.match(/\.app-sidebar-brand\s*\{[^}]*\}/s)?.[0] ?? "";
    const itemRule = appStyles.match(/\.app-sidebar-item\s*\{[^}]*\}/s)?.[0] ?? "";
    const linkRule = appStyles.match(/\.app-sidebar-link\s*\{[^}]*\}/s)?.[0] ?? "";
    const iconRule = appStyles.match(/\.app-sidebar-link-icon\s*\{[^}]*\}/s)?.[0] ?? "";
    const iconSvgRule = appStyles.match(/\.app-sidebar-link-icon svg\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(sidebarRule).toMatch(/position:\s*sticky;/);
    expect(sidebarRule).toMatch(/top:\s*0;/);
    expect(sidebarRule).toMatch(/height:\s*100dvh;/);
    expect(brandRule).toMatch(/min-height:\s*52px;/);
    expect(itemRule).toMatch(/min-height:\s*30px;/);
    expect(linkRule).toMatch(/min-height:\s*30px;/);
    expect(linkRule).toMatch(/font-size:\s*13px;/);
    expect(iconRule).toMatch(/width:\s*26px;/);
    expect(iconRule).toMatch(/min-width:\s*26px;/);
    expect(iconSvgRule).toMatch(/width:\s*15px;/);
    expect(iconSvgRule).toMatch(/height:\s*15px;/);
    expect(appSidebarSource).toMatch(/size=\{15\}/);
  });

  test("does not render the OA embedded layout explanation card", () => {
    renderEmbeddedSidebar(true);

    expect(screen.queryByText("OA 嵌入模式默认折叠，避免占用工作台宽度。")).not.toBeInTheDocument();
    expect(appSidebarSource).not.toContain("OA 嵌入模式默认折叠");
    expect(appStyles).not.toMatch(/\.app-sidebar-embedded-note\s*\{/);
  });

  test("keeps the status icon mark free of decorative gradient backgrounds", () => {
    const brandMarkRule = appStyles.match(/\.app-sidebar-brand-mark\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(brandMarkRule).not.toMatch(/radial-gradient|linear-gradient/);
    expect(brandMarkRule).toMatch(/border:\s*0;/);
    expect(brandMarkRule).toMatch(/border-radius:\s*50%;/);
    expect(brandMarkRule).toMatch(/background:\s*transparent;/);
    expect(brandMarkRule).toMatch(/color:\s*#2f7d4f;/);
  });

  test("renders the expand control as an icon-only control without visible tooltip copy", () => {
    renderSidebar(false);

    const toggle = screen.getByRole("button", { name: "展开菜单" });
    expect(toggle).toHaveClass("app-sidebar-toggle");
    expect(screen.queryByText("展开菜单")).not.toBeInTheDocument();
    expect(appSidebarSource).not.toMatch(/Tooltip\.Content[\s\S]*(展开菜单|折叠菜单)/);
  });

  test("keeps collapsed text nodes mounted and animates them with HeroUI-style state transitions", () => {
    renderSidebar(false);

    const contentRule = appStyles.match(/\.app-sidebar-content\s*\{[^}]*\}/s)?.[0] ?? "";
    const sidebarRule = appStyles.match(/\.app-sidebar\s*\{[^}]*\}/s)?.[0] ?? "";
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
    expect(sidebarRule).toMatch(/--app-sidebar-motion:\s*var\(--motion-slow\) var\(--ease-out-quart\)/);
    expect(sidebarRule).toMatch(/--app-sidebar-content-motion:\s*var\(--motion-base\) var\(--ease-out-quart\)/);
    expect(contentRule).toMatch(/transition:[^;]*var\(--app-sidebar-motion\)/);
    expect(brandTextRule).toMatch(/opacity[^;]*var\(--app-sidebar-motion\)/);
    expect(brandTextRule).toMatch(/transform[^;]*var\(--app-sidebar-motion\)/);
    expect(collapsedBrandTextRule).toMatch(/opacity:\s*0;/);
    expect(linkLabelRule).toMatch(/opacity[^;]*var\(--app-sidebar-content-motion\)/);
    expect(linkLabelRule).toMatch(/transform[^;]*var\(--app-sidebar-content-motion\)/);
    expect(collapsedLinkLabelRule).toMatch(/max-width:\s*0;/);
    expect(collapsedGroupRule).toMatch(/width:\s*34px;/);
    expect(collapsedListRule).toMatch(/width:\s*34px;/);
    expect(appSidebarSource).not.toMatch(/Tooltip\.Trigger/);
    expect(appStyles).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(appStyles).toMatch(/\[data-reduce-motion="true"\] \.app-sidebar/);
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
});
