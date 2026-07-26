import { useCallback } from "react";

import { fetchPageAudit } from "../../features/appHealth/api";
import type { PageAuditIssue, PageAuditPayload } from "../../features/appHealth/types";
import PageAuditIcon from "../common/PageAuditIcon";

export default function OaPendingPaymentAuditIcon() {
  const runAudit = useCallback(
    (signal?: AbortSignal) => fetchPageAudit("oa-pending-payments", signal),
    [],
  );

  return (
    <PageAuditIcon
      ariaLabel="Audit OA 待付款核对"
      label="OA 待付款核对"
      runAudit={runAudit}
      formatMessage={formatOaPendingPaymentAuditMessage}
      formatError={() => "Audit 无法完成 · 请查看诊断"}
    />
  );
}

export function formatOaPendingPaymentAuditMessage(payload: PageAuditPayload) {
  const integrityPassed = payload.audit_status?.integrity === "pass";
  const auditFresh = payload.audit_status?.freshness === "fresh";
  const queueDrained = payload.audit_status?.queue === "drained";
  const proofReady = payload.audit_contract?.proof_availability === "ready";
  const contractVersioned = Boolean(payload.audit_contract?.contract_revision);
  const snapshotConsistent = payload.audit_contract?.database_snapshot === true
    && payload.audit_contract?.snapshot_consistency === "repeatable_read_read_only";

  if (!auditFresh || !queueDrained) {
    return { tone: "warning" as const, text: "Audit 校验中 · 新数据正在生成" };
  }
  if (!proofReady || !contractVersioned || !snapshotConsistent) {
    return { tone: "danger" as const, text: "Audit 无法完成 · 请查看诊断" };
  }
  if (payload.overall_status === "pass" && integrityPassed) {
    return { tone: "success" as const, text: "Audit 通过 · App 内部数据一致" };
  }

  const issueCount = auditIssueCount(payload);
  const countText = payload.summary?.issue_samples_truncated ? `至少 ${issueCount}` : String(issueCount);
  const samples = auditIssueSamples(payload.issues ?? []);
  return {
    tone: "danger" as const,
    text: `Audit 未通过 · 发现 ${countText} 个一致性问题${samples.length > 0 ? ` · 示例：${samples.join("；")}` : ""}`,
  };
}

function auditIssueCount(payload: PageAuditPayload) {
  const counts = [
    payload.summary?.blocking_issue_sample_count,
    payload.summary?.issue_sample_count,
    payload.issues?.length,
  ];
  return counts.find((value) => typeof value === "number" && Number.isFinite(value) && value > 0) ?? 0;
}

function auditIssueSamples(issues: PageAuditIssue[]) {
  const samples: string[] = [];
  const seen = new Set<string>();
  for (const issue of issues) {
    const code = normalize(issue.code) || "unknown";
    const scope = normalize(issue.scope_key);
    const subject = normalize(issue.subject_id);
    const key = `${code}|${scope}|${subject}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    const location = [scope ? `范围 ${scope}` : "", subject ? `对象 ${subject}` : ""].filter(Boolean).join("，");
    samples.push(`${auditIssueLabel(code)}${location ? `（${location}）` : ""} [${code}]`);
    if (samples.length === 3) {
      break;
    }
  }
  return samples;
}

function auditIssueLabel(code: string) {
  if (code.includes("source_version") || code.includes("fresh")) {
    return "来源版本不一致";
  }
  if (code.includes("missing")) {
    return "数据缺失";
  }
  if (code.includes("orphan")) {
    return "存在孤立数据";
  }
  if (code.includes("duplicate")) {
    return "存在重复数据";
  }
  if (code.includes("relation") || code.includes("edge")) {
    return "关联关系不一致";
  }
  if (code.includes("display") || code.includes("field")) {
    return "关键字段不一致";
  }
  return "数据一致性异常";
}

function normalize(value: unknown) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}
