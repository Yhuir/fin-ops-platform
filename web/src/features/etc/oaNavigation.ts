const OA_DRAFT_CONDITION_FIELD = "cause";
const OA_DRAFT_CONDITION = "regex";
const OA_AUTO_EDIT_QUERY_KEY = "finOpsEtcAutoEdit";

type OaWindowLike = Pick<Window, "closed" | "document">;

function appendHashQueryParam(hash: string, key: string, value: string) {
  const [pathPart, queryPart = ""] = hash.split("?", 2);
  const params = new URLSearchParams(queryPart);
  params.set(key, value);
  return `${pathPart}?${params.toString()}`;
}

export function buildEtcOaDraftReviewUrl(oaDraftUrl: string, etcBatchId: string) {
  if (!etcBatchId.trim()) {
    return oaDraftUrl;
  }
  const condition = JSON.stringify([
    {
      field: OA_DRAFT_CONDITION_FIELD,
      condition: OA_DRAFT_CONDITION,
      value: etcBatchId,
    },
  ]);
  try {
    const parsed = new URL(oaDraftUrl, window.location.origin);
    parsed.hash = appendHashQueryParam(parsed.hash || "#/normal/forms/form/2", "conditions", condition);
    parsed.hash = appendHashQueryParam(parsed.hash, OA_AUTO_EDIT_QUERY_KEY, "1");
    return parsed.toString();
  } catch {
    return oaDraftUrl;
  }
}

function textOf(element: Element | null | undefined) {
  return element?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

function findEditButton(row: Element) {
  return Array.from(row.querySelectorAll("button, .el-button")).find((element) =>
    textOf(element).includes("修改"),
  ) as HTMLElement | undefined;
}

export function tryOpenEtcOaDraftEditDialog(oaWindow: OaWindowLike | null | undefined, etcBatchId: string) {
  if (!oaWindow || oaWindow.closed || !etcBatchId.trim()) {
    return false;
  }
  try {
    const rows = Array.from(oaWindow.document.querySelectorAll("tr, .el-table__row"));
    const matchedRow = rows.find((row) => textOf(row).includes(etcBatchId));
    const editButton = matchedRow ? findEditButton(matchedRow) : undefined;
    if (!editButton) {
      return false;
    }
    editButton.click();
    return true;
  } catch {
    return false;
  }
}

export function startEtcOaDraftAutoEdit(
  oaWindow: OaWindowLike | null | undefined,
  etcBatchId: string,
  options: { intervalMs?: number; timeoutMs?: number } = {},
) {
  const intervalMs = options.intervalMs ?? 750;
  const timeoutMs = options.timeoutMs ?? 30000;
  const startedAt = Date.now();
  const timer = window.setInterval(() => {
    if (tryOpenEtcOaDraftEditDialog(oaWindow, etcBatchId) || Date.now() - startedAt >= timeoutMs) {
      window.clearInterval(timer);
    }
  }, intervalMs);
  return () => window.clearInterval(timer);
}
