import AppDialog from "../common/AppDialog";
import type { WorkbenchSettingsDataResetPreview } from "../../features/workbench/types";
import type { DataResetActionConfig } from "./types";

type SettingsDataResetDialogsProps = {
  config: DataResetActionConfig;
  isBusy: boolean;
  password: string;
  preview: WorkbenchSettingsDataResetPreview;
  reason: string;
  step: "confirm" | "password";
  onCancel: () => void;
  onContinue: () => void;
  onPasswordChange: (value: string) => void;
  onReasonChange: (value: string) => void;
  onSubmit: () => void;
};

export default function SettingsDataResetDialogs({
  config,
  isBusy,
  password,
  preview,
  reason,
  step,
  onCancel,
  onContinue,
  onPasswordChange,
  onReasonChange,
  onSubmit,
}: SettingsDataResetDialogsProps) {
  if (step === "confirm") {
    const affectedRows = Object.values(preview.impactCounts).reduce((total, count) => total + count, 0);
    return (
      <AppDialog
        open
        maxWidth="sm"
        title="确认数据重置"
        onClose={onCancel}
        actions={(
          <>
            <button className="settings-secondary-button" type="button" onClick={onCancel}>
              取消
            </button>
            <button
              className="settings-danger-button"
              disabled={!preview.recoveryReady}
              type="button"
              onClick={onContinue}
            >
              继续
            </button>
          </>
        )}
      >
        <div className="settings-dialog-content">
          <p>{config.description}</p>
          <ul>
            {config.impact.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>预计影响 {affectedRows} 条记录。</p>
          <p>{preview.recoveryReady ? "恢复点已验证。" : "恢复点未就绪，请先由运维创建并验证恢复点。"}</p>
        </div>
      </AppDialog>
    );
  }

  const trimmedReasonLength = reason.trim().length;
  const reasonInvalid = reason.length > 0 && trimmedReasonLength < 5;

  return (
    <AppDialog
      open
      disableEscapeClose={isBusy}
      maxWidth="sm"
      title="OA 密码复核"
      onClose={onCancel}
      actions={(
        <>
          <button className="settings-secondary-button" disabled={isBusy} type="button" onClick={onCancel}>
            取消
          </button>
          <button
            className="settings-danger-button"
            disabled={isBusy || !password || reason.trim().length < 5 || !preview.recoveryReceiptId}
            type="button"
            onClick={onSubmit}
          >
            {isBusy ? "清理中..." : "确认清理"}
          </button>
        </>
      )}
    >
      <div className="settings-dialog-content">
        <p>请输入当前 OA 用户密码以确认本次高风险操作。</p>
        <label className="settings-field settings-field--wide">
          <span>当前 OA 用户密码</span>
          <input
            aria-required="true"
            autoComplete="current-password"
            autoFocus
            disabled={isBusy}
            required
            type="password"
            value={password}
            onChange={(event) => onPasswordChange(event.currentTarget.value)}
          />
        </label>
        <label className="settings-field settings-field--wide">
          <span>操作原因（必填）</span>
          <textarea
            aria-label="操作原因（必填）"
            aria-describedby="settings-data-reset-reason-help"
            aria-invalid={reasonInvalid || undefined}
            aria-required="true"
            disabled={isBusy}
            maxLength={500}
            minLength={5}
            required
            rows={3}
            value={reason}
            onChange={(event) => onReasonChange(event.currentTarget.value)}
          />
          <small
            className={reasonInvalid ? "settings-field-help settings-field-help--error" : "settings-field-help"}
            id="settings-data-reset-reason-help"
          >
            {reasonInvalid ? `还需输入 ${5 - trimmedReasonLength} 个字。` : "至少输入 5 个字。"}
          </small>
        </label>
      </div>
    </AppDialog>
  );
}
