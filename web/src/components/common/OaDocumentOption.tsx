export type OaNavigationSummary = {
  applicantName: string | null;
  amount: string | null;
  applicationDate: string | null;
  workflowNo: string | null;
};

export default function OaDocumentOption({ summary, index }: { summary: OaNavigationSummary; index: number }) {
  return <span className="oa-document-option">
    <span className="oa-document-option__heading">
      <span className="entity-detail-tab__number">{index}</span>
      <span>{summary.applicantName ?? '申请人未提供'}</span>
      <span className="oa-document-option__amount">{summary.amount ?? '金额未提供'}</span>
    </span>
    <span className="oa-document-option__meta">
      <span>{summary.applicationDate ?? '申请日期未提供'}</span>
      <span>OA单号 {summary.workflowNo ?? '未提供'}</span>
    </span>
  </span>;
}
