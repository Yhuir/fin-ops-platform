import { useCallback } from "react";

import { fetchPageBusinessAudit } from "../../features/appHealth/api";
import type { PageAuditDomainKey } from "../../features/appHealth/types";
import PageAuditIcon from "./PageAuditIcon";

type PageBusinessAuditIconProps = {
  ariaLabel: string;
  label: string;
  domainKey: PageAuditDomainKey;
  readModelStatus?: string;
};

const BUSINESS_AUDIT_SUCCESS_TEXT = "Audit 通过 · 已登记 App 内部全量合同正确 · Fresh";
const BUSINESS_AUDIT_NOT_FRESH_TEXT = "Audit 完整性通过 · 已登记 App 内部合同 · Not fresh";

export default function PageBusinessAuditIcon({
  ariaLabel,
  label,
  domainKey,
  readModelStatus,
}: PageBusinessAuditIconProps) {
  const runAudit = useCallback((signal?: AbortSignal) => fetchPageBusinessAudit(domainKey, signal), [domainKey]);

  return (
    <PageAuditIcon
      ariaLabel={ariaLabel}
      label={label}
      readModelStatus={readModelStatus}
      runAudit={runAudit}
      successText={BUSINESS_AUDIT_SUCCESS_TEXT}
      notFreshText={BUSINESS_AUDIT_NOT_FRESH_TEXT}
    />
  );
}
