import { Button, Chip, Input } from "@heroui/react";
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
      className="settings-section-panel settings-section-panel--standard"
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
            <Input
              aria-label="目标 OA 申请人"
              disabled={sectionDisabled}
              value={targetApplicantNameDraft}
              onChange={(event) => onChangeTargetApplicantNameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>申请人账号标识</span>
            <Input
              aria-label="申请人账号标识"
              disabled={sectionDisabled}
              value={targetApplicantCodeDraft}
              onChange={(event) => onChangeTargetApplicantCodeDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>OA 登录账号</span>
            <Input
              aria-label="OA 登录账号"
              disabled={sectionDisabled}
              value={oaUsernameDraft}
              onChange={(event) => onChangeOaUsernameDraft(event.currentTarget.value)}
            />
          </label>
          <label className="settings-field">
            <span>OA 登录密码</span>
            <Input
              aria-label="OA 登录密码"
              disabled={sectionDisabled}
              type="password"
              value={oaPasswordDraft}
              onChange={(event) => onChangeOaPasswordDraft(event.currentTarget.value)}
            />
          </label>
          <Button
            isDisabled={!canSaveCredential || sectionDisabled}
            isPending={isSaving}
            variant="primary"
            onPress={() =>
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
          </Button>
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
          <div className="settings-native-table-shell">
            <FinanceTable ariaLabel="OA申请人凭据" className="settings-native-table" minWidth={640}>
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
                      <Button
                        isDisabled={sectionDisabled}
                        size="sm"
                        variant="secondary"
                        onPress={() => onSelectCredential(credential)}
                      >
                        {credential.targetApplicantName || credential.targetApplicantCode}
                      </Button>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="account">{credential.oaUsername || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="status">
                      <Chip
                        color={credentialStatusLabel(credential) === "已配置" ? "success" : "default"}
                        size="sm"
                        variant="soft"
                      >
                        <Chip.Label>{credentialStatusLabel(credential)}</Chip.Label>
                      </Chip>
                    </FinanceTableCell>
                    <FinanceTableCell columnRole="action">
                      <div className="settings-table-actions">
                        <Button
                          aria-label={`${credential.targetApplicantName || credential.targetApplicantCode} 清空密码`}
                          isDisabled={sectionDisabled || !credential.targetApplicantCode}
                          isIconOnly
                          size="sm"
                          variant="danger"
                          onPress={() => onClearCredential(credential.targetApplicantCode)}
                        >
                          <Trash2 aria-hidden="true" size={16} />
                        </Button>
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
