import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import AppSidebar from "../components/shell/AppSidebar";

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

describe("AppSidebar shell contract", () => {
  const appSidebarSource = readFileSync("src/components/shell/AppSidebar.tsx", "utf8");
  const appStyles = readFileSync("src/app/styles.css", "utf8");

  test("keeps the desktop rail fixed and uses compact navigation row rhythm", () => {
    const sidebarRule = appStyles.match(/\.app-sidebar\s*\{[^}]*\}/s)?.[0] ?? "";
    const itemRule = appStyles.match(/\.app-sidebar-item\s*\{[^}]*\}/s)?.[0] ?? "";
    const linkRule = appStyles.match(/\.app-sidebar-link\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(sidebarRule).toMatch(/position:\s*sticky;/);
    expect(sidebarRule).toMatch(/top:\s*0;/);
    expect(sidebarRule).toMatch(/height:\s*100dvh;/);
    expect(itemRule).toMatch(/min-height:\s*40px;/);
    expect(linkRule).toMatch(/min-height:\s*40px;/);
  });

  test("keeps the status icon mark free of decorative gradient backgrounds", () => {
    const brandMarkRule = appStyles.match(/\.app-sidebar-brand-mark\s*\{[^}]*\}/s)?.[0] ?? "";

    expect(brandMarkRule).not.toMatch(/radial-gradient|linear-gradient/);
  });

  test("renders the expand control as an icon-only control without visible tooltip copy", () => {
    renderSidebar(false);

    const toggle = screen.getByRole("button", { name: "展开菜单" });
    expect(toggle).toHaveClass("app-sidebar-toggle");
    expect(screen.queryByText("展开菜单")).not.toBeInTheDocument();
    expect(appSidebarSource).not.toMatch(/Tooltip\.Content[\s\S]*(展开菜单|折叠菜单)/);
  });
});
