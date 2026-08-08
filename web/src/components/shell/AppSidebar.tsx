import { Drawer, Separator } from "@heroui/react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { useOptionalSessionPermissions } from "../../contexts/SessionContext";
import AppSidebarAccount from "./AppSidebarAccount";
import AppStatusIndicator from "./AppStatusIndicator";
import { sidebarGroups } from "./sidebarItems";

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
  isCompact,
  mobileOpen,
  expanded,
  onCloseMobile,
  onToggleExpanded,
}: AppSidebarProps) {
  const location = useLocation();
  const { canAdminAccess } = useOptionalSessionPermissions();
  const showExpandedContent = expanded || isCompact;

  const drawerContent = (
    <div className={`app-sidebar-content${showExpandedContent ? " expanded" : " collapsed"}`}>
      <div className={`app-sidebar-brand${showExpandedContent ? "" : " collapsed"}`}>
        <div
          aria-hidden={!showExpandedContent}
          className="app-sidebar-brand-lockup"
          inert={showExpandedContent ? undefined : true}
        >
          <AppStatusIndicator />
          <span className="app-sidebar-brand-text" aria-hidden={!showExpandedContent}>
            <span className="app-sidebar-eyebrow">溯源办公系统</span>
            <span className="app-sidebar-title">财务运营平台</span>
          </span>
        </div>
        {!isCompact ? (
          <button
            aria-label={expanded ? "折叠菜单" : "展开菜单"}
            aria-expanded={expanded}
            className="app-sidebar-toggle"
            title={expanded ? "折叠菜单" : "展开菜单"}
            type="button"
            onClick={onToggleExpanded}
          >
            {expanded ? (
              <PanelLeftClose aria-hidden="true" className="app-sidebar-toggle-glyph" size={17} strokeWidth={2} />
            ) : (
              <PanelLeftOpen aria-hidden="true" className="app-sidebar-toggle-glyph" size={17} strokeWidth={2} />
            )}
          </button>
        ) : null}
      </div>

      <Separator className="app-sidebar-separator" />

      <nav className="app-sidebar-scroll" aria-label="主导航">
        {sidebarGroups.map((group) => (
          <section key={group.title} className="app-sidebar-group" aria-labelledby={`app-sidebar-group-${group.title}`}>
            <h2 id={`app-sidebar-group-${group.title}`} className="app-sidebar-group-title" aria-hidden={!showExpandedContent}>
              {group.title}
            </h2>
            <ul className="app-sidebar-list" aria-label={group.title}>
              {group.items.filter((item) => !item.requiresAdmin || canAdminAccess).map((item) => {
                const Icon = item.icon;
                const active = item.active === false ? false : isSidebarItemActive(location.pathname, location.search, item.to, item.end);
                const prefetchRoute = () => {
                  item.preload().catch(() => undefined);
                };
                const link = (
                  <Link
                    to={item.to}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    className={`app-sidebar-link${active ? " active" : ""}`}
                    title={showExpandedContent ? undefined : item.label}
                    onClick={isCompact ? onCloseMobile : undefined}
                    onFocus={prefetchRoute}
                    onPointerEnter={prefetchRoute}
                    onTouchStart={prefetchRoute}
                  >
                    <span className="app-sidebar-link-icon">
                      <Icon aria-hidden="true" size={16} strokeWidth={2} />
                    </span>
                    <span className="app-sidebar-link-label" aria-hidden={!showExpandedContent}>
                      <span className="app-sidebar-link-label-text">{item.label}</span>
                    </span>
                  </Link>
                );

                return (
                  <li key={item.id ?? item.to} className="app-sidebar-item">
                    {link}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>

      <div className="app-sidebar-account-footer">
        <AppSidebarAccount showExpandedContent={showExpandedContent} />
      </div>
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
