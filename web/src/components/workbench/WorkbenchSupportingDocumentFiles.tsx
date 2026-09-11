import { Button } from "@heroui/react";
import { FileText } from "lucide-react";
import type { WorkbenchExpenseItem } from "../../features/workbench/types";

export default function WorkbenchSupportingDocumentFiles({
  documents, canManage, onManage,
}: {
  documents: NonNullable<WorkbenchExpenseItem["supportingDocuments"]>;
  canManage: boolean;
  onManage: () => void;
}) {
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
      {canManage ? <Button size="sm" variant="ghost" onPress={onManage}>管理凭证</Button> : null}
    </div>
  );
}
