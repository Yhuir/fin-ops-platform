import AddIcon from "@mui/icons-material/Add";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { settingsButtonSx, settingsTokens } from "./settingsDesign";
import type { SettingsBankTransactionTagsSectionProps } from "./types";
import Button from "@mui/material/Button";

export default function SettingsBankTransactionTagsSection({
  controlsDisabled,
  tags,
  labelDraft,
  pathDraft,
  onAddTag,
  onArchiveTag,
  onChangeLabelDraft,
  onChangePathDraft,
  onRenameTag,
}: SettingsBankTransactionTagsSectionProps) {
  return (
    <Box
      component="section"
      aria-labelledby="settings-section-bank-transaction-tags-title"
      id="settings-section-bank-transaction-tags"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-bank-transaction-tags-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          银行明细标签管理
        </Typography>
      </Stack>
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <TextField label="标签名称" size="small" value={labelDraft} disabled={controlsDisabled} onChange={(event) => onChangeLabelDraft(event.target.value)} />
          <TextField label="标签路径" size="small" value={pathDraft} disabled={controlsDisabled} onChange={(event) => onChangePathDraft(event.target.value)} placeholder="自定义 / 餐费" />
          <Button startIcon={<AddIcon />} variant="contained" disabled={controlsDisabled || !labelDraft.trim()} sx={settingsButtonSx} onClick={onAddTag}>
            新增标签
          </Button>
        </Stack>
        <List dense disablePadding sx={{ border: "1px solid", borderColor: settingsTokens.borderSubtle }}>
          {tags.map((tag) => (
            <ListItem
              key={tag.code}
              divider
              secondaryAction={(
                <Tooltip title="停用标签">
                  <span>
                    <IconButton edge="end" aria-label={`${tag.label} 停用`} disabled={controlsDisabled || tag.status === "archived"} onClick={() => onArchiveTag(tag.code)}>
                      <ArchiveOutlinedIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
            >
              <Stack direction="row" spacing={1.25} alignItems="center" sx={{ width: "100%", minWidth: 0, pr: 5 }}>
                <TextField
                  aria-label={`${tag.label} 标签名称`}
                  size="small"
                  value={tag.label}
                  disabled={controlsDisabled || tag.source === "system"}
                  onChange={(event) => onRenameTag(tag.code, event.target.value)}
                  sx={{ width: 220 }}
                />
                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }} noWrap title={tag.path.join(" / ")}>
                  {tag.path.join(" / ") || "未分组"}
                </Typography>
                <Chip label={tag.source === "system" ? "系统" : "自定义"} size="small" variant="outlined" />
                <Chip label={tag.status === "archived" ? "停用" : "启用"} size="small" variant="outlined" color={tag.status === "archived" ? "default" : "success"} />
              </Stack>
            </ListItem>
          ))}
        </List>
      </Stack>
    </Box>
  );
}
