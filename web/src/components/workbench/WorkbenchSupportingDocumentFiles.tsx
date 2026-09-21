import { Button } from "@heroui/react";
import { FileText } from "lucide-react";
import { formatMoney } from "../../features/money";
import type { WorkbenchExpenseItem } from "../../features/workbench/types";

export default function WorkbenchSupportingDocumentFiles({
  documents, totalAmount, oaAmount, hasInvoice = false, canManage, onManage,
}: {
  documents: NonNullable<WorkbenchExpenseItem["supportingDocuments"]>;
  totalAmount?: string | null;
  oaAmount?: string;
  hasInvoice?: boolean;
  canManage: boolean;
  onManage: () => void;
}) {
  const knownAmount = totalAmount !== null && totalAmount !== undefined;
  const delta = knownAmount && oaAmount && /^-?\d+(?:\.\d+)?$/.test(oaAmount.replace(/,/g, ""))
    ? supportingDocumentDifference(oaAmount, totalAmount)
    : null;
  return (
    <div className="workbench-supporting-files" role="cell">
      <ul aria-label="补充凭证文件">
        {documents.map((document) => (
          <li key={document.id}>
            <FileText aria-hidden="true" size={16} />
            <a href={document.contentUrl} target="_blank" rel="noopener noreferrer" title={document.fileName}>
              {document.fileName}
            </a>
          </li>
        ))}
      </ul>
      <div className="workbench-supporting-files__amount">
        <strong>凭证金额 {knownAmount ? formatMoney(totalAmount) : "待填写"}</strong>
        {hasInvoice ? <span>与同项发票合并核对</span>
          : <span>差额（OA − 凭证）{delta ?? "待核对"}</span>}
      </div>
      {canManage ? <Button size="sm" variant="ghost" onPress={onManage}>管理凭证</Button> : null}
    </div>
  );
}


function supportingDocumentDifference(oaAmount: string, documentAmount: string) {
  const cents = BigInt(formatMoney(oaAmount).replace(".", "")) - BigInt(formatMoney(documentAmount).replace(".", ""));
  const absolute = cents < 0n ? -cents : cents;
  return `${cents < 0n ? "-" : ""}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, "0")}`;
}
