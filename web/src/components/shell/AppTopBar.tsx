import MenuOutlinedIcon from "@mui/icons-material/MenuOutlined";
import AppBar from "@mui/material/AppBar";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";

type AppTopBarProps = {
  embedded: boolean;
  isCompact: boolean;
  onOpenMobileSidebar: () => void;
};

export default function AppTopBar({
  embedded,
  isCompact,
  onOpenMobileSidebar,
}: AppTopBarProps) {
  if (!isCompact) {
    return null;
  }

  return (
    <AppBar
      className={`global-header${embedded ? " embedded-header" : ""}`}
      color="inherit"
      elevation={0}
      position="sticky"
    >
      <Toolbar className="global-toolbar" disableGutters>
        <Stack className="global-header-main" direction="row" alignItems="center" spacing={1.5}>
          {isCompact ? (
            <Tooltip title="打开菜单">
              <IconButton aria-label="打开菜单" edge="start" onClick={onOpenMobileSidebar}>
                <MenuOutlinedIcon />
              </IconButton>
            </Tooltip>
          ) : null}
        </Stack>

        <Stack className="header-actions" direction="row" alignItems="center" spacing={1.5} />
      </Toolbar>
    </AppBar>
  );
}
