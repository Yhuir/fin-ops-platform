import { Alert, ProgressBar, Spinner } from "@heroui/react";
import type { ReactNode } from "react";

type StatePanelTone = "loading" | "empty" | "error" | "info" | "success" | "warning";

type StatePanelProps = {
  tone: StatePanelTone;
  title?: string;
  children?: ReactNode;
  compact?: boolean;
};

function statusFromTone(tone: StatePanelTone) {
  if (tone === "error") {
    return "danger";
  }
  if (tone === "success" || tone === "warning") {
    return tone;
  }
  if (tone === "loading" || tone === "info") {
    return "accent";
  }
  return "default";
}

function classNames(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

export default function StatePanel({ tone, title, children, compact = false }: StatePanelProps) {
  const className = classNames(
    "finance-state-panel",
    `finance-state-panel--${tone}`,
    compact && "finance-state-panel--compact",
  );

  if (tone === "loading") {
    return (
      <Alert className={className} role="status" status="accent">
        <Alert.Indicator>
          <Spinner aria-label="加载中" color="accent" size="sm" />
        </Alert.Indicator>
        <Alert.Content className="finance-state-panel__content">
          {title ? <Alert.Title className="finance-state-panel__title">{title}</Alert.Title> : null}
          {children ? <div className="finance-state-panel__description">{children}</div> : null}
          {!compact ? (
            <ProgressBar
              aria-label="加载进度"
              className="finance-state-panel__progress"
              color="accent"
              isIndeterminate
              size="sm"
            >
              <ProgressBar.Track>
                <ProgressBar.Fill />
              </ProgressBar.Track>
            </ProgressBar>
          ) : null}
        </Alert.Content>
      </Alert>
    );
  }

  return (
    <Alert className={className} role={tone === "error" ? "alert" : "status"} status={statusFromTone(tone)}>
      <Alert.Indicator />
      <Alert.Content className="finance-state-panel__content">
        {title ? <Alert.Title className="finance-state-panel__title">{title}</Alert.Title> : null}
        {children ? <div className="finance-state-panel__description">{children}</div> : null}
      </Alert.Content>
    </Alert>
  );
}
