import type { SettingsBankAccountsSectionProps } from "./types";

export default function SettingsBankAccountsSection({
  controlsDisabled,
  mappings,
  bankNameDraft,
  bankShortNameDraft,
  last4Draft,
  canAddMapping,
  onChangeBankNameDraft,
  onChangeBankShortNameDraft,
  onChangeLast4Draft,
  onAddMapping,
  onUpdateMapping,
  onDeleteMapping,
}: SettingsBankAccountsSectionProps) {
  return (
    <section
      aria-labelledby="settings-section-bank-accounts-title"
      className="cost-explorer-lane settings-section-panel"
      id="settings-section-bank-accounts"
      role="region"
    >
      <div className="cost-explorer-lane-header settings-section-header">
        <h3 id="settings-section-bank-accounts-title">银行账户映射</h3>
      </div>
      <div className="settings-section-body">
        <div className="settings-bank-mapping-form">
          <label className="project-export-select-field">
            <span>银行名称</span>
            <input
              value={bankNameDraft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeBankNameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="project-export-select-field">
            <span>银行卡后四位</span>
            <input
              maxLength={4}
              value={last4Draft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeLast4Draft(event.currentTarget.value.replace(/\D/g, ""))}
            />
          </label>
          <label className="project-export-select-field">
            <span>简称</span>
            <input
              value={bankShortNameDraft}
              disabled={controlsDisabled}
              onChange={(event) => onChangeBankShortNameDraft(event.currentTarget.value)}
            />
          </label>
          <button
            className="primary-button"
            type="button"
            disabled={!canAddMapping || controlsDisabled}
            onClick={onAddMapping}
          >
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
                  disabled={controlsDisabled}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    onUpdateMapping(mapping.id, (current) => ({ ...current, bankName: value }));
                  }}
                />
              </label>
              <label className="project-export-select-field">
                <span>后四位</span>
                <input
                  maxLength={4}
                  value={mapping.last4}
                  disabled={controlsDisabled}
                  onChange={(event) => {
                    const value = event.currentTarget.value.replace(/\D/g, "").slice(0, 4);
                    onUpdateMapping(mapping.id, (current) => ({
                      ...current,
                      last4: value,
                    }));
                  }}
                />
              </label>
              <label className="project-export-select-field">
                <span>简称</span>
                <input
                  value={mapping.shortName}
                  disabled={controlsDisabled}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    onUpdateMapping(mapping.id, (current) => ({ ...current, shortName: value }));
                  }}
                />
              </label>
              <button
                className="secondary-button danger-button"
                type="button"
                disabled={controlsDisabled}
                onClick={() => onDeleteMapping(mapping.id)}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
