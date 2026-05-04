import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import UndoIcon from "@mui/icons-material/Undo";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { DataGrid } from "@mui/x-data-grid";
import type { GridColDef } from "@mui/x-data-grid";

import type { WorkbenchProjectSetting } from "../../features/workbench/types";
import { settingsButtonSx, settingsDataGridSx, settingsTokens } from "./settingsDesign";
import type { SettingsProjectsSectionProps } from "./types";

const compactTextFieldSx = {
  "& .MuiOutlinedInput-root.Mui-focused fieldset": { borderColor: settingsTokens.primary },
};

const carbonAlertSx = {
  borderRadius: "4px",
  bgcolor: settingsTokens.layer01,
  color: settingsTokens.textPrimary,
  border: `1px solid ${settingsTokens.borderSubtle}`,
  "& .MuiAlert-icon": { color: settingsTokens.primary },
};

export default function SettingsProjectsSection({
  activeProjects,
  completedProjects,
  controlsDisabled,
  projectActionStatus,
  projectCodeDraft,
  projectNameDraft,
  onChangeProjectCodeDraft,
  onChangeProjectNameDraft,
  onSyncProjects,
  onAddProject,
  onToggleCompleted,
  onDeleteProject,
  isProjectActionBusy,
  canAddProject,
}: SettingsProjectsSectionProps) {

  const getColumns = (isCompleted: boolean): GridColDef[] => [
    { field: "projectName", headerName: "项目名称", flex: 1, minWidth: 150 },
    { field: "projectCode", headerName: "项目编码", width: 120 },
    {
      field: "source",
      headerName: "来源",
      width: 80,
      renderCell: (params) => (
        <Box component="span" sx={{ color: params.value === "manual" ? settingsTokens.textPrimary : settingsTokens.primary }}>
          {params.value === "manual" ? "本地" : "OA"}
        </Box>
      )
    },
    {
      field: "actions",
      headerName: "操作",
      width: 100,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: "100%" }}>
          <IconButton
            size="small"
            aria-label={`${params.row.projectName} ${isCompleted ? "移回进行中" : "标记完成"}`}
            disabled={controlsDisabled}
            onClick={() => onToggleCompleted(params.row.id)}
            title={isCompleted ? "移回进行中" : "标记完成"}
            sx={{ color: isCompleted ? settingsTokens.textSecondary : settingsTokens.primary }}
          >
            {isCompleted ? <UndoIcon fontSize="small" /> : <CheckCircleOutlineIcon fontSize="small" />}
          </IconButton>
          <IconButton
            size="small"
            color="error"
            aria-label={`${params.row.projectName} 删除`}
            disabled={controlsDisabled}
            onClick={() => void onDeleteProject(params.row as WorkbenchProjectSetting)}
            title="删除"
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ),
    },
  ];

  return (
    <Box
      component="section"
      aria-labelledby="settings-section-projects-title"
      id="settings-section-projects"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-projects-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          项目状态管理
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button
            size="small"
            type="button"
            variant="outlined"
            disabled={controlsDisabled || isProjectActionBusy}
            onClick={() => void onSyncProjects()}
            sx={{
              minHeight: 40,
              borderRadius: 0,
              color: settingsTokens.primary,
              borderColor: settingsTokens.borderDefault,
              bgcolor: settingsTokens.page,
              "&:hover": { borderColor: settingsTokens.primary, bgcolor: settingsTokens.layer01 },
            }}
          >
            {isProjectActionBusy ? "同步中..." : "从 OA 拉取项目"}
          </Button>
          <TextField
            label="项目编码"
            size="small"
            value={projectCodeDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeProjectCodeDraft(event.currentTarget.value)}
            sx={compactTextFieldSx}
          />
          <TextField
            label="项目名称"
            size="small"
            value={projectNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeProjectNameDraft(event.currentTarget.value)}
            sx={compactTextFieldSx}
          />
          <Button
            type="button"
            variant="contained"
            disabled={!canAddProject || controlsDisabled}
            onClick={() => void onAddProject()}
            sx={settingsButtonSx}
          >
            新增本地项目
          </Button>
        </Stack>

        {projectActionStatus ? (
          <Alert severity={projectActionStatus.tone === "error" ? "error" : "success"} sx={carbonAlertSx}>
            {projectActionStatus.message}
          </Alert>
        ) : null}

        <Stack direction="column" spacing={4}>
          <Box className="settings-project-column">
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
              <Typography component="strong" variant="body2" sx={{ color: settingsTokens.textPrimary, fontWeight: 600 }}>进行中项目</Typography>
              <Typography component="span" variant="caption" sx={{ color: settingsTokens.textSecondary }}>{activeProjects.length} 个</Typography>
            </Stack>
            <DataGrid
              rows={activeProjects}
              columns={getColumns(false)}
              rowHeight={48}
              columnHeaderHeight={48}
              hideFooter
              autoHeight
              disableColumnMenu
              sx={settingsDataGridSx}
            />
          </Box>
          <Box className="settings-project-column">
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
              <Typography component="strong" variant="body2" sx={{ color: settingsTokens.textPrimary, fontWeight: 600 }}>已完成项目</Typography>
              <Typography component="span" variant="caption" sx={{ color: settingsTokens.textSecondary }}>{completedProjects.length} 个</Typography>
            </Stack>
            <DataGrid
              rows={completedProjects}
              columns={getColumns(true)}
              rowHeight={48}
              columnHeaderHeight={48}
              hideFooter
              autoHeight
              disableColumnMenu
              sx={settingsDataGridSx}
            />
          </Box>
        </Stack>
      </Box>
    </Box>
  );
}
