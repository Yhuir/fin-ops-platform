import type { SettingsNavigationItem, SettingsSectionId } from "./types";

type SettingsTreeNavProps = {
  items: SettingsNavigationItem[];
  activeSectionId: SettingsSectionId;
  onSelect: (id: SettingsSectionId) => void;
};

export default function SettingsTreeNav({
  items,
  activeSectionId,
  onSelect,
}: SettingsTreeNavProps) {
  function panelId(id: SettingsSectionId) {
    switch (id) {
      case "projects":
        return "settings-section-projects";
      case "bank_accounts":
        return "settings-section-bank-accounts";
      case "oa_retention":
        return "settings-section-oa-retention";
      case "oa_invoice_offset":
        return "settings-section-oa-invoice-offset";
      case "access_accounts":
        return "settings-section-access-accounts";
      case "data_reset":
        return "settings-section-data-reset";
      default:
        return "settings-section-projects";
    }
  }

  return (
    <aside className="cost-explorer-lane settings-tree-panel" aria-label="设置导航">
      <header className="cost-explorer-lane-header settings-nav-header">
        <h3>设置分类</h3>
        <span>{items.length}</span>
      </header>
      <div className="cost-explorer-list settings-tree" role="tree" aria-label="设置分类">
        {items.map((item) => (
          <button
            key={item.id}
            aria-controls={panelId(item.id)}
            role="treeitem"
            aria-selected={activeSectionId === item.id}
            className={`cost-explorer-item settings-tree-item${activeSectionId === item.id ? " active" : ""}`}
            type="button"
            onClick={() => onSelect(item.id)}
          >
            <span className="settings-tree-copy">
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </span>
            <span className="settings-tree-count">{item.count}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
