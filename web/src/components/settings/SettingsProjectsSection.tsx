import { CheckCircle, RotateCcw, Trash2 } from "lucide-react";

import type { WorkbenchProjectSetting } from "../../features/workbench/types";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import type { SettingsProjectsSectionProps } from "./types";

function projectSourceLabel(source: WorkbenchProjectSetting["source"]) {
  return source === "manual" ? "本地" : "OA";
}

type ProjectTableProps = {
  label: string;
  projects: WorkbenchProjectSetting[];
  isCompleted: boolean;
  controlsDisabled: boolean;
  onToggleCompleted: (projectId: string) => void;
  onDeleteProject: (project: WorkbenchProjectSetting) => Promise<void> | void;
};

function ProjectTable({
  label,
  projects,
  isCompleted,
  controlsDisabled,
  onDeleteProject,
  onToggleCompleted,
}: ProjectTableProps) {
  return (
    <div className="settings-project-column">
      <div className="settings-project-column-head">
        <strong>{label}</strong>
        <span>{projects.length} 个</span>
      </div>
      <div className="settings-native-table-shell">
        <FinanceTable ariaLabel={label} className="settings-native-table" minWidth={560}>
          <FinanceTableHeader>
            <FinanceTableColumn id="name" isRowHeader columnRole="identity">项目名称</FinanceTableColumn>
            <FinanceTableColumn id="code" columnRole="identity">项目编码</FinanceTableColumn>
            <FinanceTableColumn id="source" columnRole="status">来源</FinanceTableColumn>
            <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
          </FinanceTableHeader>
          <FinanceTableBody>
            {projects.length === 0 ? (
              <FinanceTableRow id="empty">
                <FinanceTableCell className="settings-table-empty" columnRole="identity">当前没有{label}。</FinanceTableCell>
                <FinanceTableCell columnRole="identity">-</FinanceTableCell>
                <FinanceTableCell columnRole="status">-</FinanceTableCell>
                <FinanceTableCell columnRole="action">-</FinanceTableCell>
              </FinanceTableRow>
            ) : (
              projects.map((project) => (
                <FinanceTableRow id={project.id} key={project.id}>
                  <FinanceTableCell columnRole="identity">
                    <span className="settings-table-primary">{project.projectName}</span>
                  </FinanceTableCell>
                  <FinanceTableCell className="settings-table-code" columnRole="identity">{project.projectCode}</FinanceTableCell>
                  <FinanceTableCell columnRole="status">
                    <span className={`settings-source-tag settings-source-tag--${project.source}`}>
                      {projectSourceLabel(project.source)}
                    </span>
                  </FinanceTableCell>
                  <FinanceTableCell columnRole="action">
                    <div className="settings-table-actions">
                      <button
                        aria-label={`${project.projectName} ${isCompleted ? "移回进行中" : "标记完成"}`}
                        className="settings-icon-button"
                        disabled={controlsDisabled}
                        title={isCompleted ? "移回进行中" : "标记完成"}
                        type="button"
                        onClick={() => onToggleCompleted(project.id)}
                      >
                        {isCompleted ? <RotateCcw aria-hidden="true" size={16} /> : <CheckCircle aria-hidden="true" size={16} />}
                      </button>
                      <button
                        aria-label={`${project.projectName} 删除`}
                        className="settings-icon-button settings-icon-button--danger"
                        disabled={controlsDisabled}
                        title="删除"
                        type="button"
                        onClick={() => void onDeleteProject(project)}
                      >
                        <Trash2 aria-hidden="true" size={16} />
                      </button>
                    </div>
                  </FinanceTableCell>
                </FinanceTableRow>
              ))
            )}
          </FinanceTableBody>
        </FinanceTable>
      </div>
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
      className="settings-section-panel"
      id="settings-section-projects"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-projects-title">项目状态管理</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-project-toolbar">
          <button
            className="settings-secondary-button"
            disabled={controlsDisabled || isProjectActionBusy}
            type="button"
            onClick={() => void onSyncProjects()}
          >
            {isProjectActionBusy ? "同步中..." : "从 OA 拉取项目"}
          </button>
          <label className="settings-field">
            <span>项目编码</span>
            <input
              disabled={controlsDisabled}
              type="text"
              value={projectCodeDraft}
              onChange={(event) => onChangeProjectCodeDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>项目名称</span>
            <input
              disabled={controlsDisabled}
              type="text"
              value={projectNameDraft}
              onChange={(event) => onChangeProjectNameDraft(event.currentTarget.value)}
            />
          </label>
          <button
            className="settings-primary-button"
            disabled={!canAddProject || controlsDisabled}
            type="button"
            onClick={() => void onAddProject()}
          >
            新增本地项目
          </button>
        </div>

        {projectActionStatus ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${projectActionStatus.tone}`}
            role={projectActionStatus.tone === "error" ? "alert" : "status"}
          >
            {projectActionStatus.message}
          </div>
        ) : null}

        <div className="settings-project-columns">
          <ProjectTable
            label="进行中项目"
            projects={activeProjects}
            isCompleted={false}
            controlsDisabled={controlsDisabled}
            onDeleteProject={onDeleteProject}
            onToggleCompleted={onToggleCompleted}
          />
          <ProjectTable
            label="已完成项目"
            projects={completedProjects}
            isCompleted
            controlsDisabled={controlsDisabled}
            onDeleteProject={onDeleteProject}
            onToggleCompleted={onToggleCompleted}
          />
        </div>
      </div>
    </section>
  );
}
