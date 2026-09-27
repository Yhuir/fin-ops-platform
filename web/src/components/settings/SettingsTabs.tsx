import "../common/segmentedControl.css";
import { Tabs } from "@heroui/react";
import type { ReactNode } from "react";

import type { SettingsNavigationItem, SettingsSectionId } from "./types";

type SettingsTabsProps = {
  items: SettingsNavigationItem[];
  activeSectionId: SettingsSectionId;
  onSelect: (id: SettingsSectionId) => void;
  children: ReactNode;
};

export default function SettingsTabs({ items, activeSectionId, onSelect, children }: SettingsTabsProps) {
  return (
    <Tabs className="app-segments settings-tabs"
      selectedKey={activeSectionId}
      onSelectionChange={(key) => onSelect(key as SettingsSectionId)}
    >
      <Tabs.List aria-label="设置分类">
        {items.map((item) => (
          <Tabs.Tab id={item.id} key={item.id}>
            {item.label}
          <Tabs.Indicator /></Tabs.Tab>
        ))}
      </Tabs.List>
      <Tabs.Panel id={activeSectionId} className="settings-tab-panel">{children}</Tabs.Panel>
    </Tabs>
  );
}
