import { Disclosure, Drawer, Separator } from "@heroui/react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useOptionalSessionPermissions, useSession } from "../../contexts/SessionContext";
import AppSidebarAccount from "./AppSidebarAccount";
import AppStatusIndicator from "./AppStatusIndicator";
import { isSidebarDisclosureItem, sidebarGroups, type SidebarItem } from "./sidebarItems";

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

function SidebarLink({
  item,
  pathname,
  search,
  showExpandedContent,
  nested = false,
  onSelect,
}: {
  item: SidebarItem;
  pathname: string;
  search: string;
  showExpandedContent: boolean;
  nested?: boolean;
  onSelect?: () => void;
}) {
  const Icon = item.icon;
  const active = item.active === false ? false : isSidebarItemActive(pathname, search, item.to, item.end);
  const prefetchRoute = () => {
    item.preload().catch(() => undefined);
  };

  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      aria-label={item.label}
      className={`app-sidebar-link${nested ? " app-sidebar-sublink" : ""}${active ? " active" : ""}`}
      title={showExpandedContent ? undefined : item.label}
      onClick={onSelect}
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
}

export default function AppSidebar({
  isCompact,
  mobileOpen,
  expanded,
  onCloseMobile,
  onToggleExpanded,
}: AppSidebarProps) {
  const location = useLocation();
  const session = useSession();
  const { canAccessPage } = useOptionalSessionPermissions();
  const showExpandedContent = expanded || isCompact;
  const [importsExpanded, setImportsExpanded] = useState(() => location.pathname.startsWith("/imports"));
  const [openPopover, setOpenPopover] = useState<"status" | "account" | null>(null);

  const drawerContent = (
    <div className={`app-sidebar-content${showExpandedContent ? " expanded" : " collapsed"}`}>
      <div className={`app-sidebar-brand${showExpandedContent ? "" : " collapsed"}`}>
        <div
          aria-hidden={!showExpandedContent}
          className="app-sidebar-brand-lockup"
          inert={showExpandedContent ? undefined : true}
        >
          <AppStatusIndicator
            isOpen={openPopover === "status"}
            onOpenChange={(isOpen) => setOpenPopover(isOpen ? "status" : null)}
          />
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
            onClick={() => {
              setOpenPopover(null);
              onToggleExpanded();
            }}
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

      <nav className="app-sidebar-scroll" aria-busy={session.status === "loading"} aria-label="主导航">
        {session.status === "authenticated" ? sidebarGroups.map((group) => (
          <section key={group.title} className="app-sidebar-group" aria-labelledby={`app-sidebar-group-${group.title}`}>
            <h2 id={`app-sidebar-group-${group.title}`} className="app-sidebar-group-title" aria-hidden={!showExpandedContent}>
              {group.title}
            </h2>
            <ul className="app-sidebar-list" aria-label={group.title}>
              {group.items.map((item) => {
                if (isSidebarDisclosureItem(item)) {
                  const visibleChildren = item.children.filter((child) => canAccessPage(child.pageKey));
                  if (visibleChildren.length === 0) {
                    return null;
                  }
                  const routeActive = visibleChildren.some((child) => (
                    isSidebarItemActive(location.pathname, location.search, child.to, child.end)
                  ));
                  const Icon = item.icon;
                  return (
                    <li key={item.id} className="app-sidebar-item app-sidebar-disclosure-item">
                      <Disclosure
                        className="app-sidebar-disclosure"
                        isExpanded={showExpandedContent && importsExpanded}
                        onExpandedChange={(isExpanded) => {
                          setImportsExpanded(isExpanded);
                          if (isExpanded && !showExpandedContent) {
                            onToggleExpanded();
                          }
                        }}
                      >
                        <Disclosure.Heading className="app-sidebar-disclosure-heading">
                          <Disclosure.Trigger
                            aria-label={item.label}
                            className={`app-sidebar-link app-sidebar-disclosure-trigger${routeActive ? " active" : ""}`}
                          >
                            <span className="app-sidebar-link-icon">
                              <Icon aria-hidden="true" size={16} strokeWidth={2} />
                            </span>
                            <span className="app-sidebar-link-label" aria-hidden={!showExpandedContent}>
                              <span className="app-sidebar-link-label-text">{item.label}</span>
                            </span>
                            {showExpandedContent ? (
                              <Disclosure.Indicator className="app-sidebar-disclosure-indicator" />
                            ) : null}
                          </Disclosure.Trigger>
                        </Disclosure.Heading>
                        <Disclosure.Content className="app-sidebar-disclosure-content">
                          <Disclosure.Body className="app-sidebar-disclosure-body">
                            <ul className="app-sidebar-sublist" aria-label={`${item.label}子菜单`}>
                              {visibleChildren.map((child) => (
                                <li key={child.id ?? child.to} className="app-sidebar-item app-sidebar-subitem">
                                  <SidebarLink
                                    item={child}
                                    pathname={location.pathname}
                                    search={location.search}
                                    showExpandedContent={showExpandedContent}
                                    nested
                                    onSelect={isCompact ? onCloseMobile : undefined}
                                  />
                                </li>
                              ))}
                            </ul>
                          </Disclosure.Body>
                        </Disclosure.Content>
                      </Disclosure>
                    </li>
                  );
                }
                if (!canAccessPage(item.pageKey)) {
                  return null;
                }
                return (
                  <li key={item.id ?? item.to} className="app-sidebar-item">
                    <SidebarLink
                      item={item}
                      pathname={location.pathname}
                      search={location.search}
                      showExpandedContent={showExpandedContent}
                      onSelect={isCompact ? onCloseMobile : undefined}
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        )) : null}
      </nav>

      <div className="app-sidebar-account-footer">
        <AppSidebarAccount
          showExpandedContent={showExpandedContent}
          isOpen={openPopover === "account"}
          onOpenChange={(isOpen) => setOpenPopover(isOpen ? "account" : null)}
        />
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
