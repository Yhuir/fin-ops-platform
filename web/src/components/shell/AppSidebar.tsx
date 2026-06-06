import { Button, Drawer, Separator, Tooltip } from "@heroui/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import AppStatusIndicator from "./AppStatusIndicator";
import { sidebarGroups } from "./sidebarItems";

export const expandedSidebarWidth = 232;
export const collapsedSidebarWidth = 72;

type AppSidebarProps = {
  embedded: boolean;
  isCompact: boolean;
  mobileOpen: boolean;
  expanded: boolean;
  onCloseMobile: () => void;
  onToggleExpanded: () => void;
};

function isSidebarItemActive(pathname: string, search: string, to: string, end?: boolean) {
  const [targetPath, targetSearch = ""] = to.split("?");
  if (end) {
    return pathname === targetPath && (!targetSearch || search === `?${targetSearch}`);
  }
  if (targetSearch) {
    return pathname === targetPath && search === `?${targetSearch}`;
  }
  return pathname === targetPath || pathname.startsWith(`${targetPath}/`);
}

export default function AppSidebar({
  embedded,
  isCompact,
  mobileOpen,
  expanded,
  onCloseMobile,
  onToggleExpanded,
}: AppSidebarProps) {
  const location = useLocation();
  const showExpandedContent = expanded || isCompact;

  const drawerContent = (
    <div className={`app-sidebar-content${showExpandedContent ? " expanded" : " collapsed"}`}>
      <div className={`app-sidebar-brand${showExpandedContent ? "" : " collapsed"}`}>
        <div className="app-sidebar-brand-lockup">
          <AppStatusIndicator />
          {showExpandedContent ? (
            <span className="app-sidebar-brand-text">
              <span className="app-sidebar-eyebrow">溯源办公系统</span>
              <span className="app-sidebar-title">财务运营平台</span>
            </span>
          ) : null}
        </div>
        {!isCompact ? (
          <Tooltip delay={250}>
            <Tooltip.Trigger>
              <Button
                isIconOnly
                aria-label={expanded ? "折叠菜单" : "展开菜单"}
                className="app-sidebar-toggle"
                size="sm"
                variant="tertiary"
                onPress={onToggleExpanded}
              >
                {expanded ? <ChevronLeft aria-hidden="true" size={16} strokeWidth={2.2} /> : <ChevronRight aria-hidden="true" size={16} strokeWidth={2.2} />}
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content placement="right" showArrow>
              <Tooltip.Arrow />
              {expanded ? "折叠菜单" : "展开菜单"}
            </Tooltip.Content>
          </Tooltip>
        ) : null}
      </div>

      <Separator className="app-sidebar-separator" />

      <nav className="app-sidebar-scroll" aria-label="主导航">
        {sidebarGroups.map((group) => (
          <section key={group.title} className="app-sidebar-group" aria-labelledby={`app-sidebar-group-${group.title}`}>
            {showExpandedContent ? (
              <h2 id={`app-sidebar-group-${group.title}`} className="app-sidebar-group-title">
                {group.title}
              </h2>
            ) : null}
            <ul className="app-sidebar-list" aria-label={group.title}>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.active === false ? false : isSidebarItemActive(location.pathname, location.search, item.to, item.end);
                const link = (
                  <Link
                    to={item.to}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    className={`app-sidebar-link${active ? " active" : ""}`}
                    onClick={isCompact ? onCloseMobile : undefined}
                  >
                    <span className="app-sidebar-link-icon">
                      <Icon aria-hidden="true" size={18} strokeWidth={2} />
                    </span>
                    {showExpandedContent ? (
                      <span className="app-sidebar-link-label">
                        <span className="app-sidebar-link-label-text">{item.label}</span>
                      </span>
                    ) : null}
                  </Link>
                );

                return (
                  <li key={item.id ?? item.to} className="app-sidebar-item">
                    {showExpandedContent ? (
                      link
                    ) : (
                      <Tooltip delay={350}>
                        <Tooltip.Trigger>{link}</Tooltip.Trigger>
                        <Tooltip.Content placement="right" showArrow>
                          <Tooltip.Arrow />
                          {item.label}
                        </Tooltip.Content>
                      </Tooltip>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>

      {embedded && showExpandedContent ? (
        <div className="app-sidebar-embedded-note">
          OA 嵌入模式默认折叠，避免占用工作台宽度。
        </div>
      ) : null}
    </div>
  );

  if (isCompact) {
    return (
      <Drawer.Backdrop isOpen={mobileOpen} onOpenChange={(isOpen) => {
        if (!isOpen) {
          onCloseMobile();
        }
      }}>
        <Drawer.Content placement="left" className="app-sidebar-drawer-content">
          <Drawer.Dialog aria-label="主导航菜单" className="app-sidebar-paper app-sidebar-dialog">
            {drawerContent}
          </Drawer.Dialog>
        </Drawer.Content>
      </Drawer.Backdrop>
    );
  }

  return (
    <aside
      className={`app-sidebar app-sidebar--desktop${expanded ? " expanded" : " collapsed"}`}
      aria-label="主导航"
    >
      <div className="app-sidebar-paper">{drawerContent}</div>
    </aside>
  );
}
