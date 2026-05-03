const OA_FORM_ID = "2";
const OA_FORM_ROUTE = "#/normal/forms/form/2";

export function buildEtcOaDraftReviewUrl(oaDraftUrl: string) {
  try {
    const parsed = new URL(oaDraftUrl, window.location.origin);
    const [hashPath = OA_FORM_ROUTE, hashQuery = ""] = (parsed.hash || OA_FORM_ROUTE).split("?", 2);
    const params = new URLSearchParams(hashQuery);
    params.set("formId", params.get("formId") || OA_FORM_ID);
    params.delete("id");
    params.delete("conditions");
    params.delete("finOpsEtcAutoEdit");
    parsed.hash = `${hashPath || OA_FORM_ROUTE}?${params.toString()}`;
    return parsed.toString();
  } catch {
    return oaDraftUrl;
  }
}
