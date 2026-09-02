import { Button, Input } from "@heroui/react";
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
      className="settings-section-panel settings-section-panel--standard"
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
            <Input
              aria-label="银行名称"
              disabled={controlsDisabled}
              value={bankNameDraft}
              onChange={(event) => onChangeBankNameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>银行卡后四位</span>
            <Input
              aria-label="银行卡后四位"
              disabled={controlsDisabled}
              inputMode="numeric"
              maxLength={4}
              value={last4Draft}
              onChange={(event) => onChangeLast4Draft(normalizeLast4(event.currentTarget.value))}
            />
          </label>
          <label className="settings-field">
            <span>简称</span>
            <Input
              aria-label="简称"
              disabled={controlsDisabled}
              value={bankShortNameDraft}
              onChange={(event) => onChangeBankShortNameDraft(event.currentTarget.value)}
            />
          </label>
          <Button
            isDisabled={!canAddMapping || controlsDisabled}
            variant="primary"
            onPress={onAddMapping}
          >
            新增映射
          </Button>
        </div>

        {mappings.length === 0 ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            当前没有银行映射。
          </div>
        ) : (
          <div className="settings-native-table-shell">
            <FinanceTable ariaLabel="银行账户映射" className="settings-native-table" minWidth={720}>
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
                      <Input
                        aria-label={`${mapping.bankName || mapping.last4} 银行名称`}
                        className="settings-table-input"
                        disabled={controlsDisabled}
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
                      <Input
                        aria-label={`${mapping.bankName || mapping.last4} 后四位`}
                        className="settings-table-input settings-table-input--code"
                        disabled={controlsDisabled}
                        inputMode="numeric"
                        maxLength={4}
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
                      <Input
                        aria-label={`${mapping.bankName || mapping.last4} 简称`}
                        className="settings-table-input"
                        disabled={controlsDisabled}
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
                      <Button
                        aria-label={`${mapping.bankName} 删除`}
                        isDisabled={controlsDisabled}
                        isIconOnly
                        size="sm"
                        variant="danger"
                        onPress={() => onDeleteMapping(mapping.id)}
                      >
                        <Trash2 aria-hidden="true" size={16} />
                      </Button>
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
