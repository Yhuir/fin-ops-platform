import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { settingsTokens } from "./settingsDesign";
import type { SettingsPendingInvoiceTagsSectionProps } from "./types";

const GROUP_LABELS: Record<SettingsPendingInvoiceTagsSectionProps["activeGroup"], string> = {
  requiresInvoice: "需要开票",
  bankStatementAsInvoice: "流水代替发票",
  noInvoiceRequired: "无需开票",
};

const GROUP_DESCRIPTIONS: Record<SettingsPendingInvoiceTagsSectionProps["activeGroup"], string> = {
  requiresInvoice: "缺进项票时显示补票入口",
  bankStatementAsInvoice: "流水可替票，也允许补票",
  noInvoiceRequired: "缺进项票时不显示补票入口",
};

export default function SettingsPendingInvoiceTagsSection({
  activeGroup,
  controlsDisabled,
  groups,
  tags,
  onAddExistingTag,
  onRemoveTag,
  onSelectGroup,
}: SettingsPendingInvoiceTagsSectionProps) {
  const [selectedTagCode, setSelectedTagCode] = useState("");
  const [existingTagAnchor, setExistingTagAnchor] = useState<HTMLElement | null>(null);
  const activeTags = groups[activeGroup];
  const activeTagSet = new Set(activeTags);
  const tagsByCode = new Map(tags.map((tag) => [tag.code, tag]));
  const activeDefinitions = activeTags.map((code) => {
    const tag = tagsByCode.get(code);
    if (!tag) {
      return {
        code,
        label: code,
        path: [] as string[],
        status: "missing",
        issueLabel: "标签不存在",
      };
    }
    if (tag.status === "archived") {
      return {
        ...tag,
        issueLabel: "标签已停用",
      };
    }
    return {
      ...tag,
      issueLabel: null,
    };
  });
  const availableTags = tags.filter((tag) => tag.status === "active" && !activeTagSet.has(tag.code));

  return (
    <Box
      component="section"
      aria-labelledby="settings-section-pending-invoice-tags-title"
      id="settings-section-pending-invoice-tags"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-pending-invoice-tags-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          待找发票筛选
        </Typography>
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "240px 1fr" }, gap: 2 }}>
        <List aria-label="待找发票筛选分组" dense disablePadding sx={{ border: "1px solid", borderColor: settingsTokens.borderSubtle }}>
          {(Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>).map((group) => (
            <ListItem key={group} disablePadding>
              <ListItemButton selected={activeGroup === group} onClick={() => onSelectGroup(group)}>
                <ListItemText primary={GROUP_LABELS[group]} secondary={GROUP_DESCRIPTIONS[group]} />
                <Chip label={groups[group].length} size="small" variant="outlined" />
              </ListItemButton>
            </ListItem>
          ))}
        </List>

        <Stack spacing={2} sx={{ border: "1px solid", borderColor: settingsTokens.borderSubtle, p: 2 }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "stretch", md: "center" }}>
            <TextField
              select
              label="已有标签"
              size="small"
              value={selectedTagCode}
              disabled={controlsDisabled}
              onChange={(event) => setSelectedTagCode(event.target.value)}
              sx={{ minWidth: 220 }}
            >
              {availableTags.map((tag) => (
                <MenuItem key={tag.code} value={tag.code}>{tag.label}</MenuItem>
              ))}
            </TextField>
            <Button
              aria-label="选择现有标签"
              startIcon={<AddIcon />}
              variant="outlined"
              disabled={controlsDisabled || availableTags.length === 0}
              onClick={(event) => {
                if (selectedTagCode) {
                  onAddExistingTag(selectedTagCode);
                  setSelectedTagCode("");
                  return;
                }
                setExistingTagAnchor(event.currentTarget);
              }}
            >
              选择现有标签
            </Button>
            <Menu
              anchorEl={existingTagAnchor}
              open={Boolean(existingTagAnchor)}
              onClose={() => setExistingTagAnchor(null)}
            >
              {availableTags.map((tag) => (
                <MenuItem
                  key={tag.code}
                  onClick={() => {
                    onAddExistingTag(tag.code);
                    setSelectedTagCode("");
                    setExistingTagAnchor(null);
                  }}
                >
                  {tag.label}
                </MenuItem>
              ))}
            </Menu>
          </Stack>
          <Stack spacing={1}>
            {activeDefinitions.length === 0 ? (
              <Typography color="text.secondary" variant="body2">当前分组未选择自动标签。</Typography>
            ) : activeDefinitions.map((tag) => (
              <Stack key={tag.code} direction="row" spacing={1} alignItems="center">
                <Chip color={tag.issueLabel ? "error" : "default"} label={tag.label} variant={tag.issueLabel ? "outlined" : "filled"} />
                <Typography variant="body2" color={tag.issueLabel ? "error" : "text.secondary"} sx={{ flex: 1 }}>
                  {tag.issueLabel ?? tag.path.join(" / ")}
                </Typography>
                <Tooltip title="移除标签">
                  <IconButton aria-label={`${tag.label} 移除`} disabled={controlsDisabled} onClick={() => onRemoveTag(tag.code)}>
                    <RemoveIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            ))}
          </Stack>
        </Stack>
      </Box>
    </Box>
  );
}
