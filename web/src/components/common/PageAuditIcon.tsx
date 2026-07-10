import { Button, Spinner, Tooltip } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";

import type { PageAuditPayload } from "../../features/appHealth/types";

type PageAuditIconProps = {
  ariaLabel: string;
  label: string;
  readModelStatus?: string;
  runAudit: (signal?: AbortSignal) => Promise<PageAuditPayload>;
  successText?: string;
  notFreshText?: string;
};

function normalizeStatus(status: string | undefined) {
  return (status ?? "").trim().toLowerCase();
}

function isFreshStatus(status: string | undefined) {
  return normalizeStatus(status) === "fresh";
}

function auditMessage(
  payload: PageAuditPayload | null,
  readModelStatus: string | undefined,
  successText: string,
  notFreshText: string,
) {
  if (!payload) {
    return null;
  }
  const summary = payload.summary;
  const blockingSamples = summary?.blocking_issue_sample_count ?? 0;
  const issueSamples = summary?.issue_sample_count ?? 0;
  const integrityPassed = payload.audit_status?.integrity === "pass";
  const auditFresh = payload.audit_status?.freshness === "fresh";
  const pageFresh = isFreshStatus(readModelStatus);
  if (payload.overall_status === "pass" && integrityPassed && auditFresh && pageFresh && blockingSamples === 0) {
    return { tone: "success", text: successText };
  }
  if (integrityPassed && blockingSamples === 0) {
    const freshness = auditFresh && pageFresh ? "fresh" : "not_fresh";
    return { tone: "warning", text: `${notFreshText} · freshness ${freshness}` };
  }
  const truncated = summary?.issue_samples_truncated ? "+" : "";
  return {
    tone: "danger",
    text: `Audit 未通过 · integrity issues_found · blocking samples ${blockingSamples}${truncated} · issue samples ${issueSamples}${truncated}`,
  };
}

export default function PageAuditIcon({
  ariaLabel,
  label,
  readModelStatus,
  runAudit,
  successText = "Audit 成功 · 全部数据正确 · 全部配对关系正确 · Fresh",
  notFreshText = "Audit 成功 · 全部数据正确 · 全部配对关系正确 · Not fresh",
}: PageAuditIconProps) {
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

  const message = auditMessage(payload, readModelStatus, successText, notFreshText);

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
