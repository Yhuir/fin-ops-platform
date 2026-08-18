import { Button, Checkbox, Input } from "@heroui/react";
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import type {
  CostStatisticsNoOaProject,
  CostStatisticsNoOaRules,
  CostStatisticsTagRuleTag,
} from "../../features/cost-statistics/types";

type Props = {
  open: boolean;
  rules: CostStatisticsNoOaRules | null;
  projects: CostStatisticsNoOaProject[];
  loading: boolean;
  saving: boolean;
  interactionLocked: boolean;
  error: string | null;
  canSave: boolean;
  onProjectsChange: (projects: CostStatisticsNoOaProject[]) => void;
  onClose: () => void;
  onSave: () => void;
};

function leafLabel(tag: CostStatisticsTagRuleTag) {
  return tag.path[1] || tag.outputSubLabel || tag.label || tag.code;
}

function createProjectId() {
  return `virtual-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function CostStatisticsNoOaRulesDrawer({
  open,
  rules,
  projects,
  loading,
  saving,
  interactionLocked,
  error,
  canSave,
  onProjectsChange,
  onClose,
  onSave,
}: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  useEffect(() => {
    if (!open) {
      setExpandedId(null);
      setEditingId(null);
    }
  }, [open]);

  const ownerByCode = useMemo(() => new Map(
    projects.flatMap((project) => project.tagCodes.map((code) => [code, project] as const)),
  ), [projects]);
  const tags = rules?.availableTags ?? [];
  const assignedCount = new Set(projects.flatMap((project) => project.tagCodes)).size;
  const hasInvalidName = projects.some((project) => !project.displayName.trim());

  function updateProject(projectId: string, update: (project: CostStatisticsNoOaProject) => CostStatisticsNoOaProject) {
    onProjectsChange(projects.map((project) => project.id === projectId ? update(project) : project));
  }

  function addProject() {
    const id = createProjectId();
    onProjectsChange([...projects, { id, displayName: "", tagCodes: [] }]);
    setExpandedId(id);
    setEditingId(id);
  }

  function removeProject(project: CostStatisticsNoOaProject) {
    if (project.tagCodes.length > 0 && !window.confirm(`删除“${project.displayName || "未命名项目"}”后，其标签将不再进入成本统计。确定删除吗？`)) return;
    onProjectsChange(projects.filter((item) => item.id !== project.id));
    if (expandedId === project.id) setExpandedId(null);
  }

  return (
    <AppDrawer
      ariaBusy={saving || loading || interactionLocked}
      className="cost-no-oa-rules-drawer"
      closeDisabled={saving}
      footer={(
        <div className="cost-tag-rules-footer" inert={interactionLocked ? true : undefined}>
          <div className="cost-tag-rules-footer-status" role="status">{rules ? `${projects.length} 个虚拟项目 · 已分配 ${assignedCount} 个标签` : ""}</div>
          <div className="cost-tag-rules-footer-actions">
            <Button isDisabled={saving || interactionLocked} onPress={onClose} size="sm" variant="secondary">取消</Button>
            <Button isDisabled={!rules || loading || saving || interactionLocked || !canSave || hasInvalidName} isPending={saving} onPress={onSave} size="sm" variant="primary">保存</Button>
          </div>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="无 OA 成本范围"
      width={520}
    >
      <div className="cost-tag-rules-body" inert={interactionLocked ? true : undefined}>
        {loading ? <div className="cost-tag-rules-state">正在加载无 OA 流水标签...</div> : null}
        {error ? <div className="cost-tag-rules-state error">{error}</div> : null}
        {!loading && rules ? (
          <>
            <div className="cost-tag-rules-intro">这里只管理当前确实存在无 active OA 关系的支出标签。统计时仍逐笔判断；同标签下已有 OA 的流水不会进入虚拟项目。</div>
            <Button className="cost-no-oa-add" isDisabled={!canSave || saving || interactionLocked} onPress={addProject} size="sm" variant="secondary"><Plus aria-hidden="true" size={15} />新增虚拟项目</Button>
            {projects.length === 0 ? <div className="cost-tag-rules-state">尚未创建虚拟项目，也不会默认纳入任何无 OA 流水。</div> : null}
            <div className="cost-no-oa-projects">
              {projects.map((project) => {
                const expanded = expandedId === project.id;
                return (
                  <section className="cost-no-oa-project" key={project.id}>
                    <div className="cost-no-oa-project-head">
                      <button className="cost-no-oa-project-toggle" onClick={() => setExpandedId(expanded ? null : project.id)} onDoubleClick={() => { if (canSave && !saving && !interactionLocked) setEditingId(project.id); }} type="button">
                        {expanded ? <ChevronDown aria-hidden="true" size={16} /> : <ChevronRight aria-hidden="true" size={16} />}
                        <span>{project.displayName || "未命名虚拟项目"}</span>
                        <em>{project.tagCodes.length} 个标签</em>
                      </button>
                      <Button aria-label={`编辑${project.displayName || "虚拟项目"}`} isDisabled={!canSave || saving || interactionLocked} isIconOnly onPress={() => { setExpandedId(project.id); setEditingId(project.id); }} size="sm" variant="ghost"><Pencil aria-hidden="true" size={15} /></Button>
                      <Button aria-label={`删除${project.displayName || "虚拟项目"}`} isDisabled={!canSave || saving || interactionLocked} isIconOnly onPress={() => removeProject(project)} size="sm" variant="ghost"><Trash2 aria-hidden="true" size={15} /></Button>
                    </div>
                    {expanded ? (
                      <div className="cost-no-oa-project-body">
                        {editingId === project.id ? (
                          <Input aria-label="虚拟项目名称" autoFocus disabled={!canSave || saving || interactionLocked} maxLength={80} onBlur={() => project.displayName.trim() && setEditingId(null)} onChange={(event) => updateProject(project.id, (item) => ({ ...item, displayName: event.currentTarget.value }))} onKeyDown={(event) => { if (event.key === "Enter" && project.displayName.trim()) setEditingId(null); }} placeholder="输入虚拟项目名称" value={project.displayName} />
                        ) : null}
                        <div aria-label={`${project.displayName || "虚拟项目"}标签`} className="cost-no-oa-tag-list" role="group">
                          {tags.length === 0 ? <div className="cost-tag-rules-state">当前没有带标签的无 OA 支出流水。</div> : tags.map((tag) => {
                            const owner = ownerByCode.get(tag.code);
                            const selected = owner?.id === project.id;
                            const occupied = Boolean(owner && owner.id !== project.id);
                            return (
                              <Checkbox className="cost-no-oa-tag" isDisabled={!canSave || saving || interactionLocked || occupied || (tag.status === "unavailable" && !selected)} isSelected={selected} key={tag.code} onChange={(checked) => updateProject(project.id, (item) => ({ ...item, tagCodes: checked ? [...item.tagCodes, tag.code] : item.tagCodes.filter((code) => code !== tag.code) }))}>
                                <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                                <span>{leafLabel(tag)}</span>
                                {occupied ? <em>已归属：{owner?.displayName || "未命名项目"}</em> : null}
                                {tag.status === "unavailable" ? <em>当前无可归集流水，可取消</em> : null}
                              </Checkbox>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </section>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    </AppDrawer>
  );
}
