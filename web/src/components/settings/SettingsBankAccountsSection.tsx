import { Trash2 } from "lucide-react";

import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import type { SettingsBankAccountsSectionProps } from "./types";

function normalizeLast4(value: string) {
  return value.replace(/\D/g, "").slice(0, 4);
}

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
      className="settings-section-panel"
      id="settings-section-bank-accounts"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-bank-accounts-title">银行账户映射</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-bank-mapping-form">
          <label className="settings-field">
            <span>银行名称</span>
            <input
              disabled={controlsDisabled}
              type="text"
              value={bankNameDraft}
              onChange={(event) => onChangeBankNameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>银行卡后四位</span>
            <input
              disabled={controlsDisabled}
              inputMode="numeric"
              maxLength={4}
              type="text"
              value={last4Draft}
              onChange={(event) => onChangeLast4Draft(normalizeLast4(event.currentTarget.value))}
            />
          </label>
          <label className="settings-field">
            <span>简称</span>
            <input
              disabled={controlsDisabled}
              type="text"
              value={bankShortNameDraft}
              onChange={(event) => onChangeBankShortNameDraft(event.currentTarget.value)}
            />
          </label>
          <button
            className="settings-primary-button"
            disabled={!canAddMapping || controlsDisabled}
            type="button"
            onClick={onAddMapping}
          >
            新增映射
          </button>
        </div>

        {mappings.length === 0 ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            当前没有银行映射。
          </div>
        ) : (
          <div className="settings-native-table-shell settings-native-table-shell--scroll">
            <FinanceTable ariaLabel="银行账户映射" className="settings-native-table" minWidth={640} scrollMode="contained">
              <FinanceTableHeader>
                <FinanceTableColumn id="bank" isRowHeader columnRole="identity">银行名称</FinanceTableColumn>
                <FinanceTableColumn id="last4" columnRole="account">后四位</FinanceTableColumn>
                <FinanceTableColumn id="short" columnRole="identity">简称</FinanceTableColumn>
                <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {mappings.map((mapping) => (
                  <FinanceTableRow id={mapping.id} key={mapping.id}>
                    <FinanceTableCell columnRole="identity">
                      <input
                        aria-label={`${mapping.bankName || mapping.last4} 银行名称`}
                        className="settings-table-input"
                        disabled={controlsDisabled}
                        type="text"
                        value={mapping.bankName}
                        onChange={(event) => {
                          const bankName = event.currentTarget.value.trim();
                          onUpdateMapping(mapping.id, (current) => ({
                            ...current,
                            bankName,
                          }));
                        }}
                      />
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="account">
                      <input
                        aria-label={`${mapping.bankName || mapping.last4} 后四位`}
                        className="settings-table-input settings-table-input--code"
                        disabled={controlsDisabled}
                        inputMode="numeric"
                        maxLength={4}
                        type="text"
                        value={mapping.last4}
                        onChange={(event) => {
                          const last4 = normalizeLast4(event.currentTarget.value);
                          onUpdateMapping(mapping.id, (current) => ({
                            ...current,
                            last4,
                          }));
                        }}
                      />
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="identity">
                      <input
                        aria-label={`${mapping.bankName || mapping.last4} 简称`}
                        className="settings-table-input"
                        disabled={controlsDisabled}
                        type="text"
                        value={mapping.shortName}
                        onChange={(event) => {
                          const shortName = event.currentTarget.value.trim();
                          onUpdateMapping(mapping.id, (current) => ({
                            ...current,
                            shortName,
                          }));
                        }}
                      />
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="action">
                      <button
                        aria-label={`${mapping.bankName} 删除`}
                        className="settings-icon-button settings-icon-button--danger"
                        disabled={controlsDisabled}
                        type="button"
                        onClick={() => onDeleteMapping(mapping.id)}
                      >
                        <Trash2 aria-hidden="true" size={16} />
                      </button>
                    </FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </div>
        )}
      </div>
    </section>
  );
}
