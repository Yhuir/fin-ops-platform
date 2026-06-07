import AppDialog from "../common/AppDialog";
import type { DataResetActionConfig } from "./types";

type SettingsDataResetDialogsProps = {
  config: DataResetActionConfig;
  isBusy: boolean;
  password: string;
  step: "confirm" | "password";
  onCancel: () => void;
  onContinue: () => void;
  onPasswordChange: (value: string) => void;
  onSubmit: () => void;
};

export default function SettingsDataResetDialogs({
  config,
  isBusy,
  password,
  step,
  onCancel,
  onContinue,
  onPasswordChange,
  onSubmit,
}: SettingsDataResetDialogsProps) {
  if (step === "confirm") {
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
            <button className="settings-danger-button" type="button" onClick={onContinue}>
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
        </div>
      </AppDialog>
    );
  }

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
            disabled={isBusy || !password}
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
            autoComplete="current-password"
            autoFocus
            disabled={isBusy}
            type="password"
            value={password}
            onChange={(event) => onPasswordChange(event.currentTarget.value)}
          />
        </label>
      </div>
    </AppDialog>
  );
}
