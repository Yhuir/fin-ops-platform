import { apiRequestJson } from "../apiClient";

export type OaApplicantCredential = {
  targetApplicantCode: string;
  targetApplicantName: string;
  oaUsername: string;
  credentialStatus: string;
  hasCredential: boolean;
  enabled: boolean;
  oaUserId: string | null;
  remark: string;
  verifiedAt: string | null;
  version: number;
};
export type OaApplicantUser = { userId: string; username: string; displayName: string; active: boolean };
export type OaApplicantCredentialDraft = { oaUserId: string; password: string; remark: string };
const endpoint = "/api/workbench/settings/oa-applicant-credentials";
export const applicantLabel = (name: string, remark?: string) => remark ? `${name}（${remark}）` : name;

export async function loadOaApplicantCredentials(signal: AbortSignal) {
  return apiRequestJson<{ credentials: OaApplicantCredential[] }>(endpoint, { signal });
}
export async function loadOaApplicantUsers(signal: AbortSignal) {
  return apiRequestJson<{ users: OaApplicantUser[] }>(`${endpoint}/users`, { signal });
}
export async function saveOaApplicantCredential(draft: OaApplicantCredentialDraft, existing: OaApplicantCredential | null) {
  return apiRequestJson<{ credential: OaApplicantCredential }>(existing ? `${endpoint}/${encodeURIComponent(existing.targetApplicantCode)}` : endpoint, {
    method: existing ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(existing ? {
      oaUserId: draft.oaUserId, remark: draft.remark, expectedVersion: existing.version,
      ...(draft.password === "" ? {} : { password: draft.password }),
    } : draft),
  });
}
export async function deleteOaApplicantCredential(credential: OaApplicantCredential) {
  return apiRequestJson<{ deleted: true; targetApplicantCode: string }>(`${endpoint}/${encodeURIComponent(credential.targetApplicantCode)}`, {
    method: "DELETE", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expectedVersion: credential.version }),
  });
}
