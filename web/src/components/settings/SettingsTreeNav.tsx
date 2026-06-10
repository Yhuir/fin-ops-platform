import type { SettingsNavigationItem, SettingsSectionId } from "./types";

type SettingsTreeNavProps = {
  items: SettingsNavigationItem[];
  activeSectionId: SettingsSectionId;
  onSelect: (id: SettingsSectionId) => void;
};

function classNames(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

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
      case "pending_invoice_tags":
        return "settings-section-pending-invoice-tags";
      case "oa_retention":
        return "settings-section-oa-retention";
      case "oa_invoice_offset":
        return "settings-section-oa-invoice-offset";
      case "oa_applicant_credentials":
        return "settings-section-oa-applicant-credentials";
      case "access_accounts":
        return "settings-section-access-accounts";
      case "data_reset":
        return "settings-section-data-reset";
      default:
        return "settings-section-projects";
    }
  }

  return (
    <aside aria-label="设置导航" className="settings-tree-nav">
      <div className="settings-tree-nav__header">
        <h2>
          设置分类
        </h2>
        <span>{items.length}</span>
      </div>
      <ul className="settings-tree" role="tree" aria-label="设置分类">
        {items.map((item) => {
          const selected = activeSectionId === item.id;
          return (
            <li key={item.id} role="none">
              <button
                className={classNames("settings-tree-item", selected && "settings-tree-item--selected")}
                type="button"
                aria-controls={panelId(item.id)}
                role="treeitem"
                aria-selected={selected}
                onClick={() => onSelect(item.id)}
              >
                <span className="settings-tree-copy">
                  <strong>{item.label}</strong>
                  <small>{item.description}</small>
                </span>
                <span className="settings-tree-count">{item.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
