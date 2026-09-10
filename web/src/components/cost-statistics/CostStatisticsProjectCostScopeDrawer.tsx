import { Button, Checkbox, Input } from "@heroui/react";
import { useMemo, useState } from "react";
import type { ProjectCostScope } from "../../features/cost-statistics/types";
import AppDrawer from "../common/AppDrawer";
import "./projectCostScope.css";

type Props = {
  open: boolean; scope: ProjectCostScope | null; selected: string[];
  loading: boolean; saving: boolean; canSave: boolean; unconfirmed: boolean;
  error: string | null; onClose: () => void; onReload: () => void;
  onChange: (codes: string[]) => void; onSave: () => void;
};

export default function CostStatisticsProjectCostScopeDrawer(props: Props) {
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set(props.selected), [props.selected]);
  const groups = useMemo(() => {
    const result = new Map<string, NonNullable<Props["scope"]>["available_tags"]>();
    for (const tag of props.scope?.available_tags ?? []) {
      if (query.trim() && ![tag.label, ...tag.path].join(" ").includes(query.trim())) continue;
      const group = tag.path.length > 1 ? tag.path[0] : "其他标签";
      const tags = result.get(group) ?? [];
      tags.push(tag); result.set(group, tags);
    }
    return [...result];
  }, [props.scope, query]);
  const locked = !props.canSave || props.saving || props.loading || props.unconfirmed;
  return <AppDrawer closeDisabled={props.saving || props.unconfirmed} open={props.open} onClose={props.onClose} title="项目成本范围" width={520}>
    <div className="project-cost-scope">
      <Input aria-label="搜索流水标签" placeholder="搜索流水标签" value={query} onChange={event => setQuery(event.currentTarget.value)} />
      {props.loading ? <p role="status">正在加载…</p> : null}
      {props.error ? <div role="alert" className="project-cost-scope-error"><span>{props.error}</span><Button size="sm" variant="secondary" isDisabled={props.loading || props.saving} onPress={props.onReload}>{props.unconfirmed ? "核实保存结果" : "重新加载"}</Button></div> : null}
      <div className="project-cost-scope-list">
        {!props.loading && props.scope && groups.length === 0 ? <p>没有匹配的标签</p> : null}
        {groups.map(([name, tags]) => <div role="group" aria-label={name} key={name}>
          <p className="project-cost-scope-group">{name}</p>
          {tags.map(tag => <Checkbox key={tag.code} className="project-cost-scope-tag" isSelected={selected.has(tag.code)} isDisabled={locked || (!tag.can_select && !selected.has(tag.code))} onChange={checked => props.onChange(checked ? [...props.selected, tag.code] : props.selected.filter(code => code !== tag.code))}>
            <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
            <span>{tag.path.length > 1 ? tag.path.slice(1).join(" / ") : tag.label}{tag.status === "archived" ? <small>已归档</small> : null}{!tag.can_select ? <small>{tag.direction === "income" ? "收入" : "不可用"}</small> : null}</span>
          </Checkbox>)}
        </div>)}
      </div>
      <div className="project-cost-scope-footer"><span>已选 {props.selected.length} 个标签</span><Button isDisabled={locked || !props.scope} onPress={props.onSave} variant="primary">{props.saving ? "正在保存…" : "保存范围"}</Button></div>
    </div>
  </AppDrawer>;
}
