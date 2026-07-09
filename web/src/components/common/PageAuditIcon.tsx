import { Button, Spinner, Tooltip } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";

import type { PageAuditPayload } from "../../features/appHealth/types";

type PageAuditIconProps = {
  ariaLabel: string;
  label: string;
  readModelStatus?: string;
  runAudit: (signal?: AbortSignal) => Promise<PageAuditPayload>;
};

function normalizeStatus(status: string | undefined) {
  return (status ?? "").trim().toLowerCase();
}

function isFreshStatus(status: string | undefined) {
  const normalized = normalizeStatus(status);
  return !normalized || normalized === "fresh" || normalized === "live_query";
}

function auditMessage(payload: PageAuditPayload | null, readModelStatus: string | undefined) {
  if (!payload) {
    return null;
  }
  const summary = payload.summary;
  const blocking = summary?.blocking_issue_count ?? 0;
  const issues = summary?.issue_count ?? 0;
  const passed = payload.overall_status === "pass" && blocking === 0 && issues === 0;
  const fresh = isFreshStatus(readModelStatus);
  if (passed && fresh) {
    return { tone: "success", text: "Audit 成功 · 全部数据正确 · 全部配对关系正确 · Fresh" };
  }
  if (passed) {
    return { tone: "warning", text: "Audit 成功 · 全部数据正确 · 全部配对关系正确 · Not fresh" };
  }
  return { tone: "danger", text: `Audit 未通过 · blocking ${blocking} · issues ${issues}` };
}

export default function PageAuditIcon({ ariaLabel, label, readModelStatus, runAudit }: PageAuditIconProps) {
  const [payload, setPayload] = useState<PageAuditPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleRun = useCallback(async () => {
    if (isLoading) {
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    try {
      setPayload(await runAudit(controller.signal));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Audit failed");
      setPayload(null);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, runAudit]);

  const message = auditMessage(payload, readModelStatus);

  return (
    <span className="page-audit-control">
      <Tooltip delay={250}>
        <Tooltip.Trigger>
          <Button
            aria-label={ariaLabel}
            className="page-audit-icon-button"
            isDisabled={isLoading}
            isIconOnly
            onPress={handleRun}
            size="sm"
            type="button"
            variant="tertiary"
          >
            {isLoading ? <Spinner color="current" size="sm" /> : <RefreshCw aria-hidden="true" size={15} strokeWidth={2.2} />}
          </Button>
        </Tooltip.Trigger>
        <Tooltip.Content>{`Audit ${label}`}</Tooltip.Content>
      </Tooltip>
      {message ? (
        <span className="page-audit-status" data-tone={message.tone} aria-live="polite">
          {message.text}
        </span>
      ) : null}
      {error ? (
        <span className="page-audit-status" data-tone="danger" role="alert">
          Audit 失败
        </span>
      ) : null}
    </span>
  );
}
