import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { SettingsNavigationItem, SettingsSectionId } from "./types";

type SettingsTreeNavProps = {
  items: SettingsNavigationItem[];
  activeSectionId: SettingsSectionId;
  onSelect: (id: SettingsSectionId) => void;
};

export default function SettingsTreeNav({
  items,
  activeSectionId,
  onSelect,
}: SettingsTreeNavProps) {
  function panelId(id: SettingsSectionId) {
    switch (id) {
      case "projects":
        return "settings-section-projects";
      case "bank_accounts":
        return "settings-section-bank-accounts";
      case "oa_retention":
        return "settings-section-oa-retention";
      case "oa_invoice_offset":
        return "settings-section-oa-invoice-offset";
      case "access_accounts":
        return "settings-section-access-accounts";
      case "data_reset":
        return "settings-section-data-reset";
      default:
        return "settings-section-projects";
    }
  }

  return (
    <Paper component="aside" className="settings-tree-panel" aria-label="设置导航" variant="outlined">
      <Stack className="settings-nav-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography component="h3" variant="subtitle2">设置分类</Typography>
        <Typography component="span" variant="caption">{items.length}</Typography>
      </Stack>
      <List className="settings-tree" role="tree" aria-label="设置分类" dense disablePadding>
        {items.map((item) => (
          <ListItem key={item.id} disablePadding role="none">
            <ListItemButton
              aria-controls={panelId(item.id)}
              role="treeitem"
              aria-selected={activeSectionId === item.id}
              className="settings-tree-item"
              selected={activeSectionId === item.id}
              onClick={() => onSelect(item.id)}
            >
              <ListItemText
                className="settings-tree-copy"
                primary={item.label}
                secondary={item.description}
                primaryTypographyProps={{ component: "strong", variant: "body2" }}
                secondaryTypographyProps={{ component: "small" }}
              />
              <Typography className="settings-tree-count" component="span" variant="caption">
                {item.count}
              </Typography>
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Paper>
  );
}
