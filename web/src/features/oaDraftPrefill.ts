import { apiRequestJson } from "./apiClient";

export type OaDraftPrefillFamily = "etc" | "input-invoice-usage";

export type OaDraftPrefillConfiguration = {
  application_type: string;
  payment_method: string;
  invoice_kind: string;
  project_id: string;
  project_name: string;
  payee: string;
  bank: string;
  bank_account: string;
  reason_template: string;
};

export type OaDraftPrefillPayload = {
  family: "etc" | "input_invoice_usage";
  version: number;
  configuration: OaDraftPrefillConfiguration;
  dynamic_fields: {
    applicant: string;
    application_date: string;
    amount: string;
    payee: string;
  };
  options: {
    application_types: Array<{ value: string; label: string }>;
    payment_methods: Array<{ value: string; label: string }>;
    invoice_kinds: Array<{ value: string; label: string }>;
    projects: Array<{ value: string; label: string }>;
  };
  can_save: boolean;
};

export function fetchOaDraftPrefill(family: OaDraftPrefillFamily) {
  return apiRequestJson<OaDraftPrefillPayload>(`/api/workbench/settings/oa-draft-prefill/${family}`, {
    method: "GET",
  });
}

export function saveOaDraftPrefill(
  family: OaDraftPrefillFamily,
  expectedVersion: number,
  configuration: OaDraftPrefillConfiguration,
) {
  return apiRequestJson<OaDraftPrefillPayload>(`/api/workbench/settings/oa-draft-prefill/${family}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_version: expectedVersion, configuration }),
  });
}
