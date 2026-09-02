import { Button, Chip, Input, Tabs } from "@heroui/react";
import { CheckCircle, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";

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
    <div className="settings-native-table-shell">
      <FinanceTable ariaLabel={label} className="settings-native-table" minWidth={680}>
        <FinanceTableHeader>
          <FinanceTableColumn id="name" isRowHeader columnRole="identity">项目名称</FinanceTableColumn>
          <FinanceTableColumn id="code" columnRole="identity">项目编码</FinanceTableColumn>
          <FinanceTableColumn id="source" columnRole="status">来源</FinanceTableColumn>
          <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          {projects.length === 0 ? (
            <FinanceTableRow id="empty">
              <FinanceTableCell className="settings-table-empty" columnRole="identity">暂无项目</FinanceTableCell>
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
                  <Chip color="default" size="sm" variant="soft">
                    <Chip.Label>{projectSourceLabel(project.source)}</Chip.Label>
                  </Chip>
                </FinanceTableCell>
                <FinanceTableCell columnRole="action">
                  <div className="settings-table-actions">
                    <Button
                      aria-label={`${project.projectName} ${isCompleted ? "移回进行中" : "标记完成"}`}
                      isDisabled={controlsDisabled}
                      isIconOnly
                      size="sm"
                      variant="tertiary"
                      onPress={() => onToggleCompleted(project.id)}
                    >
                      {isCompleted ? <RotateCcw aria-hidden="true" size={16} /> : <CheckCircle aria-hidden="true" size={16} />}
                    </Button>
                    <Button
                      aria-label={`${project.projectName} 删除`}
                      isDisabled={controlsDisabled}
                      isIconOnly
                      size="sm"
                      variant="danger"
                      onPress={() => void onDeleteProject(project)}
                    >
                      <Trash2 aria-hidden="true" size={16} />
                    </Button>
                  </div>
                </FinanceTableCell>
              </FinanceTableRow>
            ))
          )}
        </FinanceTableBody>
      </FinanceTable>
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
  const [activeTab, setActiveTab] = useState<"active" | "completed">("active");
  const projects = activeTab === "active" ? activeProjects : completedProjects;

  return (
    <section
      aria-labelledby="settings-section-projects-title"
      className="settings-section-panel settings-section-panel--fluid"
      id="settings-section-projects"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-projects-title">项目状态管理</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-project-toolbar">
          <Button
            isDisabled={controlsDisabled || isProjectActionBusy}
            isPending={isProjectActionBusy}
            variant="secondary"
            onPress={() => void onSyncProjects()}
          >
            {isProjectActionBusy ? "同步中..." : "从 OA 拉取项目"}
          </Button>
          <label className="settings-field settings-field--project-code">
            <span>项目编码</span>
            <Input
              aria-label="项目编码"
              disabled={controlsDisabled}
              value={projectCodeDraft}
              onChange={(event) => onChangeProjectCodeDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field settings-field--project-name">
            <span>项目名称</span>
            <Input
              aria-label="项目名称"
              disabled={controlsDisabled}
              value={projectNameDraft}
              onChange={(event) => onChangeProjectNameDraft(event.currentTarget.value)}
            />
          </label>
          <Button
            isDisabled={!canAddProject || controlsDisabled}
            variant="primary"
            onPress={() => void onAddProject()}
          >
            新增本地项目
          </Button>
        </div>

        {projectActionStatus ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${projectActionStatus.tone}`}
            role={projectActionStatus.tone === "error" ? "alert" : "status"}
          >
            {projectActionStatus.message}
          </div>
        ) : null}

        <Tabs
          className="settings-project-tabs"
          selectedKey={activeTab}
          variant="secondary"
          onSelectionChange={(key) => setActiveTab(String(key) as "active" | "completed")}
        >
          <Tabs.List aria-label="项目状态">
            <Tabs.Tab id="active">进行中 {activeProjects.length}</Tabs.Tab>
            <Tabs.Tab id="completed">已完成 {completedProjects.length}</Tabs.Tab>
          </Tabs.List>
        </Tabs>
        <ProjectTable
          label={activeTab === "active" ? "进行中项目" : "已完成项目"}
          projects={projects}
          isCompleted={activeTab === "completed"}
          controlsDisabled={controlsDisabled}
          onDeleteProject={onDeleteProject}
          onToggleCompleted={onToggleCompleted}
        />
      </div>
    </section>
  );
}
