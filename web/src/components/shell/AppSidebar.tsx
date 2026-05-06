import ChevronLeftOutlinedIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import SvgIcon from "@mui/material/SvgIcon";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link, NavLink, useLocation } from "react-router-dom";

import type { AppHealthStatus } from "../../features/appHealth/types";
import { sidebarGroups } from "./sidebarItems";

export const expandedSidebarWidth = 232;
export const collapsedSidebarWidth = 72;
const sidebarTransitionTimeout = { enter: 150, exit: 110 };
const sidebarTransitionEasing = {
  enter: "cubic-bezier(0.22, 1, 0.36, 1)",
  exit: "cubic-bezier(0.4, 0, 1, 1)",
};

type AppSidebarProps = {
  embedded: boolean;
  isCompact: boolean;
  mobileOpen: boolean;
  expanded: boolean;
  healthStatus: AppHealthStatus;
  workbenchStatus: { level: "ok" | "pending" | "error"; reason: string } | null;
  onCloseMobile: () => void;
  onToggleExpanded: () => void;
};

type SidebarBrandStatus = {
  level: "ok" | "pending" | "error";
  reason: string;
  details: string[];
};

function toSidebarBrandStatus(healthStatus: AppHealthStatus, workbenchStatus: AppSidebarProps["workbenchStatus"]): SidebarBrandStatus {
  if (healthStatus.level === "blocked") {
    return { level: "error", reason: healthStatus.reason, details: healthStatus.details };
  }
  if (healthStatus.level === "busy") {
    return { level: "pending", reason: healthStatus.reason, details: healthStatus.details };
  }
  if (workbenchStatus?.level === "error") {
    return { level: "error", reason: workbenchStatus.reason, details: [] };
  }
  if (workbenchStatus?.level === "pending") {
    return { level: "pending", reason: workbenchStatus.reason, details: [] };
  }
  return { level: "ok", reason: healthStatus.reason, details: healthStatus.details };
}

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

function SidebarBrandStatusMark({ status }: { status: SidebarBrandStatus }) {
  const tooltipTitle = [status.reason, ...status.details].filter(Boolean).slice(0, 3).join("\n");
  return (
    <Tooltip title={tooltipTitle} placement="right">
      <span
        aria-label={status.reason}
        aria-live="polite"
        className={`app-sidebar-brand-mark ${status.level}`}
        data-status-reason={status.reason}
        role="status"
      >
        <SvgIcon className="app-sidebar-brand-status-icon" viewBox="0 0 100 100" aria-hidden="true">
          <circle className="app-sidebar-brand-status-track" cx="50" cy="50" r="37" />
          <circle className="app-sidebar-brand-status-sweep" cx="50" cy="50" r="37" />
        </SvgIcon>
      </span>
    </Tooltip>
  );
}

export default function AppSidebar({
  embedded,
  isCompact,
  mobileOpen,
  expanded,
  healthStatus,
  workbenchStatus,
  onCloseMobile,
  onToggleExpanded,
}: AppSidebarProps) {
  const location = useLocation();
  const width = expanded ? expandedSidebarWidth : collapsedSidebarWidth;
  const brandStatus = toSidebarBrandStatus(healthStatus, workbenchStatus);
  const showExpandedContent = expanded || isCompact;

  const drawerContent = (
    <Stack className="app-sidebar-content" sx={{ width, height: "100%" }}>
      <Stack
        className={`app-sidebar-brand${showExpandedContent ? "" : " collapsed"}`}
        direction="row"
        alignItems="center"
        justifyContent={showExpandedContent ? "space-between" : "center"}
      >
        <Stack className="app-sidebar-brand-lockup" direction="row" alignItems="center" spacing={showExpandedContent ? 1 : 0}>
          <SidebarBrandStatusMark status={brandStatus} />
          <Collapse
            in={showExpandedContent}
            orientation="horizontal"
            collapsedSize={0}
            timeout={sidebarTransitionTimeout}
            easing={sidebarTransitionEasing}
            className="app-sidebar-horizontal-collapse app-sidebar-brand-copy-collapse"
            aria-hidden={!showExpandedContent}
          >
            <span className="app-sidebar-brand-text">
              <Typography className="app-sidebar-eyebrow" component="div">
                溯源办公系统
              </Typography>
              <Typography className="app-sidebar-title" component="div">
                财务运营平台
              </Typography>
            </span>
          </Collapse>
        </Stack>
        {!isCompact ? (
          <Tooltip title={expanded ? "折叠菜单" : "展开菜单"} placement="right">
            <IconButton
              aria-label={expanded ? "折叠菜单" : "展开菜单"}
              className="app-sidebar-toggle"
              size="small"
              onClick={onToggleExpanded}
            >
              {expanded ? <ChevronLeftOutlinedIcon fontSize="small" /> : <ChevronRightOutlinedIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        ) : null}
      </Stack>

      <Divider />

      <Stack className="app-sidebar-scroll">
        {sidebarGroups.map((group) => (
          <Stack key={group.title} component="section" className="app-sidebar-group">
            <Collapse
              in={showExpandedContent}
              orientation="horizontal"
              collapsedSize={0}
              timeout={sidebarTransitionTimeout}
              easing={sidebarTransitionEasing}
              className="app-sidebar-horizontal-collapse app-sidebar-group-title-collapse"
              aria-hidden={!showExpandedContent}
            >
              <Typography className="app-sidebar-group-title" component="h2">
                {group.title}
              </Typography>
            </Collapse>
            <List dense disablePadding aria-label={group.title}>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.active === false ? false : isSidebarItemActive(location.pathname, location.search, item.to, item.end);
                const LinkComponent = item.active === false ? Link : NavLink;
                const button = (
                  <ListItemButton
                    component={LinkComponent}
                    to={item.to}
                    end={item.end}
                    selected={active}
                    aria-label={item.label}
                    className="app-sidebar-link"
                    onClick={isCompact ? onCloseMobile : undefined}
                  >
                    <ListItemIcon className="app-sidebar-link-icon">
                      <Icon fontSize="small" />
                    </ListItemIcon>
                    <Collapse
                      in={showExpandedContent}
                      orientation="horizontal"
                      collapsedSize={0}
                      timeout={sidebarTransitionTimeout}
                      easing={sidebarTransitionEasing}
                      className="app-sidebar-horizontal-collapse app-sidebar-link-label-collapse"
                      aria-hidden={!showExpandedContent}
                    >
                      <ListItemText className="app-sidebar-link-label" primary={item.label} />
                    </Collapse>
                  </ListItemButton>
                );

                return (
                  <ListItem key={item.id ?? item.to} disablePadding className="app-sidebar-item">
                    {showExpandedContent ? button : (
                      <Tooltip title={item.label} placement="right">
                        {button}
                      </Tooltip>
                    )}
                  </ListItem>
                );
              })}
            </List>
          </Stack>
        ))}
      </Stack>

      {embedded ? (
        <Collapse
          in={showExpandedContent}
          orientation="horizontal"
          collapsedSize={0}
          timeout={sidebarTransitionTimeout}
          easing={sidebarTransitionEasing}
          className="app-sidebar-horizontal-collapse app-sidebar-note-collapse"
          aria-hidden={!showExpandedContent}
        >
          <Typography className="app-sidebar-embedded-note" component="div">
            OA 嵌入模式默认折叠，避免占用工作台宽度。
          </Typography>
        </Collapse>
      ) : null}
    </Stack>
  );

  if (isCompact) {
    return (
      <Drawer
        open={mobileOpen}
        variant="temporary"
        onClose={onCloseMobile}
        ModalProps={{ keepMounted: true }}
        PaperProps={{ className: "app-sidebar-paper" }}
      >
        {drawerContent}
      </Drawer>
    );
  }

  return (
    <Drawer
      open
      variant="permanent"
      PaperProps={{ className: "app-sidebar-paper" }}
      sx={{
        width,
        flexShrink: 0,
        transition: (theme) =>
          theme.transitions.create("width", {
            duration: expanded ? sidebarTransitionTimeout.enter : sidebarTransitionTimeout.exit,
            easing: expanded ? sidebarTransitionEasing.enter : sidebarTransitionEasing.exit,
          }),
        "& .MuiDrawer-paper": {
          width,
          transition: (theme) =>
            theme.transitions.create("width", {
              duration: expanded ? sidebarTransitionTimeout.enter : sidebarTransitionTimeout.exit,
              easing: expanded ? sidebarTransitionEasing.enter : sidebarTransitionEasing.exit,
            }),
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
}
