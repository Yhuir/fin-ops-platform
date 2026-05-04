import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { settingsTokens } from "./settingsDesign";
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
    <Box component="aside" aria-label="设置导航" sx={{ width: "100%" }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5, px: 0.5 }}>
        <Typography
          component="h2"
          variant="caption"
          sx={{ color: settingsTokens.textSecondary, fontWeight: 600, textTransform: "uppercase" }}
        >
          设置分类
        </Typography>
        <Typography component="span" variant="caption" sx={{ color: settingsTokens.textMuted }}>
          {items.length}
        </Typography>
      </Stack>
      <List role="tree" aria-label="设置分类" dense disablePadding>
        {items.map((item) => {
          const selected = activeSectionId === item.id;
          return (
            <ListItem key={item.id} disablePadding role="none">
              <ListItemButton
                aria-controls={panelId(item.id)}
                role="treeitem"
                aria-selected={selected}
                selected={selected}
                onClick={() => onSelect(item.id)}
                sx={{
                  position: "relative",
                  minHeight: 56,
                  borderRadius: 0,
                  py: 1,
                  pr: 1,
                  pl: 2,
                  borderLeft: `2px solid ${selected ? settingsTokens.primary : settingsTokens.borderSubtle}`,
                  color: settingsTokens.textPrimary,
                  "&:hover": {
                    bgcolor: settingsTokens.layer01Hover,
                  },
                  "&.Mui-focusVisible": {
                    outline: `2px solid ${settingsTokens.primary}`,
                    outlineOffset: "-2px",
                  },
                  ...(selected
                    ? {
                        bgcolor: settingsTokens.selected,
                        "&.Mui-selected": {
                          bgcolor: settingsTokens.selected,
                        },
                        "&.Mui-selected:hover": {
                          bgcolor: settingsTokens.selected,
                        },
                      }
                    : {}),
                }}
              >
                <ListItemText
                  primary={item.label}
                  secondary={item.description}
                  primaryTypographyProps={{
                    component: "strong",
                    variant: "body2",
                    sx: {
                      color: selected ? settingsTokens.textPrimary : settingsTokens.textPrimary,
                      fontWeight: selected ? 600 : 400,
                      letterSpacing: "0.16px",
                    },
                  }}
                  secondaryTypographyProps={{
                    component: "small",
                    sx: { color: settingsTokens.textSecondary, fontSize: "12px", mt: 0.25 },
                  }}
                />
                <Typography
                  component="span"
                  variant="caption"
                  sx={{ color: selected ? settingsTokens.primary : settingsTokens.textMuted, ml: 1, fontWeight: 600 }}
                >
                  {item.count}
                </Typography>
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>
    </Box>
  );
}
