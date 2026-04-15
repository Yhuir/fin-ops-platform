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
    <div className={`settings-project-row${rowClassName ? ` ${rowClassName}` : ""}`}>
      <span className="settings-project-main">
        <strong>{project.projectName}</strong>
        <small>{project.projectCode} / 来源：{project.source === "manual" ? "本地" : "OA"}</small>
      </span>
      <span className="settings-project-actions">
        <button
          aria-label={`${project.projectName} ${toggleLabel}`}
          className="secondary-button"
          type="button"
          disabled={controlsDisabled}
          onClick={() => onToggleCompleted(project.id)}
        >
          {toggleLabel}
        </button>
        <button
          aria-label={`${project.projectName} ${deleteLabel}`}
          className="secondary-button danger-button"
          type="button"
          disabled={controlsDisabled}
          onClick={() => void onDeleteProject(project)}
        >
          {deleteLabel}
        </button>
      </span>
    </div>
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
    <section
      aria-labelledby="settings-section-projects-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-projects"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-projects-title">项目状态管理</h3>
      </div>
      <div className="settings-section-body">
        <div className="settings-project-toolbar">
          <button
            className="secondary-button"
            type="button"
            disabled={controlsDisabled}
            onClick={() => void onSyncProjects()}
          >
            {isProjectActionBusy ? "同步中..." : "从 OA 拉取项目"}
          </button>
          <label className="project-export-select-field">
            <span>项目编码</span>
            <input
              aria-label="项目编码"
              value={projectCodeDraft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeProjectCodeDraft(event.currentTarget.value)}
            />
          </label>
          <label className="project-export-select-field">
            <span>项目名称</span>
            <input
              aria-label="项目名称"
              value={projectNameDraft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeProjectNameDraft(event.currentTarget.value)}
            />
          </label>
          <button
            className="primary-button"
            type="button"
            disabled={!canAddProject || controlsDisabled}
            onClick={() => void onAddProject()}
          >
            新增本地项目
          </button>
        </div>
        {projectActionStatus ? (
          <div className={`state-panel project-action-status project-action-status-${projectActionStatus.tone}`}>
            {projectActionStatus.message}
          </div>
        ) : null}
        <div className="settings-project-columns">
          <div className="settings-project-column">
            <div className="settings-project-column-head">
              <strong>进行中项目</strong>
              <span>{activeProjects.length} 个</span>
            </div>
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
          </div>
          <div className="settings-project-column">
            <div className="settings-project-column-head">
              <strong>已完成项目</strong>
              <span>{completedProjects.length} 个</span>
            </div>
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
          </div>
        </div>
      </div>
    </section>
  );
}
