import ChevronLeftOutlinedIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { NavLink, useLocation } from "react-router-dom";

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
  const width = expanded ? expandedSidebarWidth : collapsedSidebarWidth;

  const drawerContent = (
    <Stack className="app-sidebar-content" sx={{ width, height: "100%" }}>
      <Stack className="app-sidebar-brand" direction="row" alignItems="center" justifyContent={expanded ? "space-between" : "center"}>
        {expanded ? (
          <div>
            <Typography className="app-sidebar-eyebrow" component="div">
              导航
            </Typography>
            <Typography className="app-sidebar-title" component="div">
              财务运营
            </Typography>
          </div>
        ) : null}
        {!isCompact ? (
          <Tooltip title={expanded ? "折叠菜单" : "展开菜单"} placement="right">
            <IconButton
              aria-label={expanded ? "折叠菜单" : "展开菜单"}
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
            {expanded ? (
              <Typography className="app-sidebar-group-title" component="h2">
                {group.title}
              </Typography>
            ) : null}
            <List dense disablePadding aria-label={group.title}>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isSidebarItemActive(location.pathname, location.search, item.to, item.end);
                const button = (
                  <ListItemButton
                    component={NavLink}
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
                    {expanded || isCompact ? <ListItemText primary={item.label} /> : null}
                  </ListItemButton>
                );

                return (
                  <ListItem key={item.to} disablePadding className="app-sidebar-item">
                    {expanded || isCompact ? button : (
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

      {embedded && expanded ? (
        <Typography className="app-sidebar-embedded-note" component="div">
          OA 嵌入模式默认折叠，避免占用工作台宽度。
        </Typography>
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
        "& .MuiDrawer-paper": {
          width,
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
}
