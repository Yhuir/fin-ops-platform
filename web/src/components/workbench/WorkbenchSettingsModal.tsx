import { useMemo, useState } from "react";

import type { BankAccountMapping, WorkbenchProjectSetting, WorkbenchSettings } from "../../features/workbench/types";

type WorkbenchSettingsModalProps = {
  settings: WorkbenchSettings;
  isSaving: boolean;
  onClose: () => void;
  onSave: (payload: { completedProjectIds: string[]; bankAccountMappings: BankAccountMapping[] }) => void;
};

function toggleCompleted(projectId: string, completedProjectIds: string[]) {
  return completedProjectIds.includes(projectId)
    ? completedProjectIds.filter((id) => id !== projectId)
    : [...completedProjectIds, projectId];
}

function sortProjects(projects: WorkbenchProjectSetting[]) {
  return [...projects].sort((left, right) => left.projectName.localeCompare(right.projectName, "zh-CN"));
}

export default function WorkbenchSettingsModal({
  settings,
  isSaving,
  onClose,
  onSave,
}: WorkbenchSettingsModalProps) {
  const [completedProjectIds, setCompletedProjectIds] = useState<string[]>(settings.projects.completedProjectIds);
  const [mappings, setMappings] = useState<BankAccountMapping[]>(settings.bankAccountMappings);
  const [bankNameDraft, setBankNameDraft] = useState("");
  const [last4Draft, setLast4Draft] = useState("");

  const activeProjects = useMemo(
    () => sortProjects(settings.projects.active.filter((project) => !completedProjectIds.includes(project.id))),
    [completedProjectIds, settings.projects.active],
  );
  const completedProjects = useMemo(
    () =>
      sortProjects([
        ...settings.projects.completed,
        ...settings.projects.active.filter((project) => completedProjectIds.includes(project.id)),
      ]).filter((project, index, rows) => rows.findIndex((row) => row.id === project.id) === index),
    [completedProjectIds, settings.projects.active, settings.projects.completed],
  );

  const canAddMapping = last4Draft.trim().length === 4 && /^\d{4}$/.test(last4Draft.trim()) && bankNameDraft.trim().length > 0;

  function handleAddMapping() {
    if (!canAddMapping) {
      return;
    }
    const nextLast4 = last4Draft.trim();
    if (mappings.some((item) => item.last4 === nextLast4)) {
      setMappings((current) =>
        current.map((item) => (item.last4 === nextLast4 ? { ...item, bankName: bankNameDraft.trim() } : item)),
      );
    } else {
      setMappings((current) => [
        ...current,
        {
          id: `bank_mapping_${nextLast4}`,
          last4: nextLast4,
          bankName: bankNameDraft.trim(),
        },
      ]);
    }
    setLast4Draft("");
    setBankNameDraft("");
  }

  return (
    <div className="export-center-modal-layer" role="presentation">
      <button aria-label="关闭设置" className="export-center-modal-backdrop" type="button" onClick={onClose} />
      <section aria-labelledby="workbench-settings-modal-title" aria-modal="true" className="export-center-modal workbench-settings-modal" role="dialog">
        <header className="export-center-modal-header">
          <div>
            <h2 id="workbench-settings-modal-title">关联台设置</h2>
            <p>管理项目完工状态，以及银行名称和银行卡后四位的映射关系。</p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isSaving}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body workbench-settings-body">
          <section className="export-center-section">
            <div className="export-center-section-header">
              <h3>项目状态管理</h3>
            </div>
            <div className="settings-project-columns">
              <div className="settings-project-column">
                <div className="settings-project-column-head">
                  <strong>进行中项目</strong>
                  <span>{activeProjects.length} 个</span>
                </div>
                <div className="settings-project-list">
                  {activeProjects.map((project) => (
                    <button
                      key={project.id}
                      className="settings-project-row"
                      type="button"
                      onClick={() => setCompletedProjectIds((current) => toggleCompleted(project.id, current))}
                    >
                      <span>{project.projectName}</span>
                      <span>标记完成</span>
                    </button>
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
                    <button
                      key={project.id}
                      className="settings-project-row done"
                      type="button"
                      onClick={() => setCompletedProjectIds((current) => toggleCompleted(project.id, current))}
                    >
                      <span>{project.projectName}</span>
                      <span>移回进行中</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="export-center-section">
            <div className="export-center-section-header">
              <h3>银行账户映射</h3>
            </div>
            <div className="settings-bank-mapping-form">
              <label className="project-export-select-field">
                <span>银行名称</span>
                <input value={bankNameDraft} onChange={(event) => setBankNameDraft(event.currentTarget.value)} />
              </label>
              <label className="project-export-select-field">
                <span>银行卡后四位</span>
                <input maxLength={4} value={last4Draft} onChange={(event) => setLast4Draft(event.currentTarget.value.replace(/\D/g, ""))} />
              </label>
              <button className="primary-button" type="button" disabled={!canAddMapping} onClick={handleAddMapping}>
                新增映射
              </button>
            </div>

            <div className="settings-bank-mapping-list">
              {mappings.length === 0 ? <div className="cost-explorer-empty">当前没有银行映射。</div> : null}
              {mappings.map((mapping) => (
                <div key={mapping.id} className="settings-bank-mapping-row">
                  <label className="project-export-select-field">
                    <span>银行名称</span>
                    <input
                      value={mapping.bankName}
                      onChange={(event) =>
                        setMappings((current) =>
                          current.map((item) => (item.id === mapping.id ? { ...item, bankName: event.currentTarget.value } : item)),
                        )
                      }
                    />
                  </label>
                  <label className="project-export-select-field">
                    <span>后四位</span>
                    <input
                      maxLength={4}
                      value={mapping.last4}
                      onChange={(event) =>
                        setMappings((current) =>
                          current.map((item) =>
                            item.id === mapping.id
                              ? { ...item, last4: event.currentTarget.value.replace(/\D/g, "").slice(0, 4) }
                              : item,
                          ),
                        )
                      }
                    />
                  </label>
                  <button
                    className="secondary-button danger-button"
                    type="button"
                    onClick={() => setMappings((current) => current.filter((item) => item.id !== mapping.id))}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>

        <footer className="export-center-modal-footer">
          <button
            className="primary-button"
            type="button"
            disabled={isSaving}
            onClick={() =>
              onSave({
                completedProjectIds,
                bankAccountMappings: mappings,
              })
            }
          >
            {isSaving ? "保存中..." : "保存设置"}
          </button>
        </footer>
      </section>
    </div>
  );
}
