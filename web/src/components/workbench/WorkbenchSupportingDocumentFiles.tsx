import { Button } from "@heroui/react";
import { FileText } from "lucide-react";
import { formatMoney } from "../../features/money";
import type { WorkbenchExpenseItem } from "../../features/workbench/types";

export default function WorkbenchSupportingDocumentFiles({
  documents, totalAmount, canManage, onManage,
}: {
  documents: NonNullable<WorkbenchExpenseItem["supportingDocuments"]>;
  totalAmount?: string | null;
  canManage: boolean;
  onManage: () => void;
}) {
  const knownAmount = totalAmount !== null && totalAmount !== undefined;
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
      </div>
      {canManage ? <Button size="sm" variant="ghost" onPress={onManage}>管理凭证</Button> : null}
    </div>
  );
}
