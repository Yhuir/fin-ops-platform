import "./settings.css";
import { Tabs } from "@heroui/react";
import type { ReactNode } from "react";

import type { SettingsNavigationItem, SettingsSectionId } from "./types";

type SettingsTabsProps = {
  items: SettingsNavigationItem[];
  activeSectionId: SettingsSectionId;
  onSelect: (id: SettingsSectionId) => void;
  children: ReactNode;
  dirtySectionIds?: ReadonlySet<SettingsSectionId>;
};

export default function SettingsTabs({ items, activeSectionId, onSelect, children, dirtySectionIds }: SettingsTabsProps) {
  return (
    <Tabs className="settings-tabs"
      selectedKey={activeSectionId}
      onSelectionChange={(key) => onSelect(key as SettingsSectionId)}
    >
      <Tabs.List aria-label="设置分类">
        {items.map((item) => (
          <Tabs.Tab id={item.id} key={item.id}>
            {item.label}
            {dirtySectionIds?.has(item.id) ? <span className="settings-tab-draft" title="未保存修改" aria-hidden="true" /> : null}
          </Tabs.Tab>
        ))}
      </Tabs.List>
      <Tabs.Panel id={activeSectionId} className="settings-tab-panel">{children}</Tabs.Panel>
    </Tabs>
  );
}
