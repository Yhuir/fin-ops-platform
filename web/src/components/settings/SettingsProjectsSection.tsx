import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { WorkbenchProjectSetting } from "../../features/workbench/types";
import type { SettingsProjectsSectionProps } from "./types";

function ProjectRow({
  project,
  controlsDisabled,
  toggleLabel,
  deleteLabel,
  rowClassName,
  onToggleCompleted,
  onDeleteProject,
}: {
  project: WorkbenchProjectSetting;
  controlsDisabled: boolean;
  toggleLabel: string;
  deleteLabel: string;
  rowClassName?: string;
  onToggleCompleted: (projectId: string) => void;
  onDeleteProject: (project: WorkbenchProjectSetting) => Promise<void> | void;
}) {
  return (
    <Paper className={`settings-project-row${rowClassName ? ` ${rowClassName}` : ""}`} variant="outlined">
      <Box className="settings-project-main">
        <Typography component="strong" variant="body2">{project.projectName}</Typography>
        <Typography component="small" variant="caption">{project.projectCode} / 来源：{project.source === "manual" ? "本地" : "OA"}</Typography>
      </Box>
      <Stack className="settings-project-actions" direction="row" spacing={1}>
        <Button
          aria-label={`${project.projectName} ${toggleLabel}`}
          size="small"
          type="button"
          variant="outlined"
          disabled={controlsDisabled}
          onClick={() => onToggleCompleted(project.id)}
        >
          {toggleLabel}
        </Button>
        <Button
          aria-label={`${project.projectName} ${deleteLabel}`}
          color="error"
          size="small"
          type="button"
          variant="outlined"
          disabled={controlsDisabled}
          onClick={() => void onDeleteProject(project)}
        >
          {deleteLabel}
        </Button>
      </Stack>
    </Paper>
  );
}

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
  return (
    <Paper
      component="section"
      aria-labelledby="settings-section-projects-title"
      className="settings-section-panel"
      id="settings-section-projects"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-projects-title" component="h3" variant="subtitle1">项目状态管理</Typography>
      </Stack>
      <div className="settings-section-body">
        <Stack className="settings-project-toolbar" direction="row" spacing={1.5} useFlexGap flexWrap="wrap">
          <Button
            size="small"
            type="button"
            variant="outlined"
            disabled={controlsDisabled}
            onClick={() => void onSyncProjects()}
          >
            {isProjectActionBusy ? "同步中..." : "从 OA 拉取项目"}
          </Button>
          <TextField
            label="项目编码"
            size="small"
            value={projectCodeDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeProjectCodeDraft(event.currentTarget.value)}
          />
          <TextField
            label="项目名称"
            size="small"
            value={projectNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeProjectNameDraft(event.currentTarget.value)}
          />
          <Button
            type="button"
            variant="contained"
            disabled={!canAddProject || controlsDisabled}
            onClick={() => void onAddProject()}
          >
            新增本地项目
          </Button>
        </Stack>
        {projectActionStatus ? (
          <Alert className="project-action-status" severity={projectActionStatus.tone === "error" ? "error" : "success"}>
            {projectActionStatus.message}
          </Alert>
        ) : null}
        <div className="settings-project-columns">
          <Paper className="settings-project-column" variant="outlined">
            <Stack className="settings-project-column-head" direction="row" alignItems="center" justifyContent="space-between">
              <Typography component="strong" variant="body2">进行中项目</Typography>
              <Typography component="span" variant="caption">{activeProjects.length} 个</Typography>
            </Stack>
            <div className="settings-project-list">
              {activeProjects.map((project) => (
                <ProjectRow
                  key={project.id}
                  project={project}
                  controlsDisabled={controlsDisabled}
                  toggleLabel="标记完成"
                  deleteLabel="删除"
                  onToggleCompleted={onToggleCompleted}
                  onDeleteProject={onDeleteProject}
                />
              ))}
            </div>
          </Paper>
          <Paper className="settings-project-column" variant="outlined">
            <Stack className="settings-project-column-head" direction="row" alignItems="center" justifyContent="space-between">
              <Typography component="strong" variant="body2">已完成项目</Typography>
              <Typography component="span" variant="caption">{completedProjects.length} 个</Typography>
            </Stack>
            <div className="settings-project-list">
              {completedProjects.map((project) => (
                <ProjectRow
                  key={project.id}
                  project={project}
                  controlsDisabled={controlsDisabled}
                  toggleLabel="移回进行中"
                  deleteLabel="删除"
                  rowClassName="done"
                  onToggleCompleted={onToggleCompleted}
                  onDeleteProject={onDeleteProject}
                />
              ))}
            </div>
          </Paper>
        </div>
      </div>
    </Paper>
  );
}
