import { Save, Trash2 } from "lucide-react";

import type { OaApplicantCredentialSummary } from "../../features/workbench/types";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import type { SettingsOaApplicantCredentialsSectionProps } from "./types";

function credentialStatusLabel(credential: OaApplicantCredentialSummary) {
  return credential.hasCredential && credential.credentialStatus === "configured" ? "已配置" : "未配置";
}

function credentialStatusTone(credential: OaApplicantCredentialSummary) {
  return credentialStatusLabel(credential) === "已配置" ? "success" : "neutral";
}

function sortedCredentials(credentials: OaApplicantCredentialSummary[]) {
  return [...credentials].sort((left, right) =>
    (left.targetApplicantName || left.targetApplicantCode).localeCompare(
      right.targetApplicantName || right.targetApplicantCode,
      "zh-CN",
    ),
  );
}

export default function SettingsOaApplicantCredentialsSection({
  controlsDisabled,
  credentials,
  isLoading,
  isSaving,
  status,
  targetApplicantNameDraft,
  targetApplicantCodeDraft,
  oaUsernameDraft,
  oaPasswordDraft,
  canSaveCredential,
  onChangeTargetApplicantNameDraft,
  onChangeTargetApplicantCodeDraft,
  onChangeOaUsernameDraft,
  onChangeOaPasswordDraft,
  onSelectCredential,
  onSaveCredential,
  onClearCredential,
}: SettingsOaApplicantCredentialsSectionProps) {
  const rows = sortedCredentials(credentials);
  const sectionDisabled = controlsDisabled || isSaving;

  return (
    <section
      aria-labelledby="settings-section-oa-applicant-credentials-title"
      className="settings-section-panel"
      id="settings-section-oa-applicant-credentials"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-oa-applicant-credentials-title">OA申请人凭据</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-access-form">
          <label className="settings-field">
            <span>目标 OA 申请人</span>
            <input
              disabled={sectionDisabled}
              type="text"
              value={targetApplicantNameDraft}
              onChange={(event) => onChangeTargetApplicantNameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>申请人账号标识</span>
            <input
              disabled={sectionDisabled}
              type="text"
              value={targetApplicantCodeDraft}
              onChange={(event) => onChangeTargetApplicantCodeDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>OA 登录账号</span>
            <input
              disabled={sectionDisabled}
              type="text"
              value={oaUsernameDraft}
              onChange={(event) => onChangeOaUsernameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>OA 登录密码</span>
            <input
              disabled={sectionDisabled}
              type="password"
              value={oaPasswordDraft}
              onChange={(event) => onChangeOaPasswordDraft(event.currentTarget.value)}
            />
          </label>
          <button
            className="settings-primary-button"
            disabled={!canSaveCredential || sectionDisabled}
            type="button"
            onClick={() =>
              onSaveCredential({
                targetApplicantCode: targetApplicantCodeDraft.trim(),
                targetApplicantName: targetApplicantNameDraft.trim(),
                oaUsername: oaUsernameDraft.trim(),
                password: oaPasswordDraft,
              })
            }
          >
            <Save aria-hidden="true" size={16} />
            保存凭据
          </button>
        </div>

        {status ? (
          <div
            className={`settings-inline-alert settings-inline-alert--${status.tone}`}
            role={status.tone === "error" ? "alert" : "status"}
          >
            {status.message}
          </div>
        ) : null}

        {isLoading ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            正在加载 OA 申请人凭据。
          </div>
        ) : rows.length === 0 ? (
          <div className="settings-inline-alert settings-inline-alert--info" role="status">
            当前没有配置 OA 申请人凭据。
          </div>
        ) : (
          <div className="settings-native-table-shell settings-native-table-shell--scroll">
            <FinanceTable ariaLabel="OA申请人凭据" className="settings-native-table" minWidth={640} scrollMode="contained">
              <FinanceTableHeader>
                <FinanceTableColumn id="applicant" isRowHeader columnRole="identity">目标 OA 申请人</FinanceTableColumn>
                <FinanceTableColumn id="account" columnRole="account">OA 登录账号</FinanceTableColumn>
                <FinanceTableColumn id="status" columnRole="status">凭据状态</FinanceTableColumn>
                <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {rows.map((credential) => (
                  <FinanceTableRow id={credential.targetApplicantCode || credential.targetApplicantName} key={credential.targetApplicantCode || credential.targetApplicantName}>
                    <FinanceTableCell columnRole="identity">
                      <button
                        className="settings-secondary-button"
                        disabled={sectionDisabled}
                        type="button"
                        onClick={() => onSelectCredential(credential)}
                      >
                        {credential.targetApplicantName || credential.targetApplicantCode}
                      </button>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="account">{credential.oaUsername || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="status">
                      <span className={`settings-selected-tag settings-selected-tag--${credentialStatusTone(credential)}`}>
                        {credentialStatusLabel(credential)}
                      </span>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="action">
                      <div className="settings-table-actions">
                        <button
                          aria-label={`${credential.targetApplicantName || credential.targetApplicantCode} 清空密码`}
                          className="settings-icon-button settings-icon-button--danger"
                          disabled={sectionDisabled || !credential.targetApplicantCode}
                          type="button"
                          onClick={() => onClearCredential(credential.targetApplicantCode)}
                        >
                          <Trash2 aria-hidden="true" size={16} />
                        </button>
                      </div>
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
